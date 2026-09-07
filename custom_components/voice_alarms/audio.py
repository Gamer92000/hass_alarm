"""Audio generation and streaming for Voice Alarms.

Two sources exist:

* The built-in sound, a synthesised bell arpeggio loop rendered in pure
  Python (no numpy / audioop dependency).
* A custom sound (URL, ``media-source://`` id or local file) which is looped
  and gain-ramped by ffmpeg.

Both produce a FLAC stream whose loudness ramps up over the first
``ramp_seconds`` of the alarm. FLAC rather than WAV because satellites do not
necessarily decode WAV at all: the stock Home Assistant Voice PE firmware only
ships FLAC and MP3 decoders and rejects an ``audio/wav`` stream before playing
anything. The built-in sound is wrapped into uncompressed FLAC frames right
here (``FlacWriter``); custom sounds are encoded by ffmpeg. The stream is paced
to real time so that the satellite never buffers more than a couple of
seconds, which keeps dismissal snappy.
"""

from __future__ import annotations

import asyncio
import logging
import math
import struct
import sys
import time as time_mod
from array import array
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from .const import FLAC_BLOCK_SIZE, SAMPLE_RATE, STREAM_CHUNK_SECONDS, STREAM_LEAD_SECONDS

_LOGGER = logging.getLogger(__name__)

LOOP_SECONDS = 4.0
NOTE_SECONDS = 1.1
NOTE_RELEASE_SECONDS = 0.08
NOTE_SPACING_SECONDS = 0.16
GROUP_SPACING_SECONDS = 1.05
GROUPS = 3
NOTE_FREQUENCIES = (523.25, 659.25, 783.99, 1046.50)  # C5 E5 G5 C6
NOTES_PER_GROUP = len(NOTE_FREQUENCIES)
# (frequency multiple, amplitude, decay rate 1/s)
NOTE_PARTIALS = (
    (1.0, 1.0, 3.0),  # fundamental: long clean ring
    (2.0, 0.50, 6.0),
    (3.0, 0.28, 10.0),
    (4.16, 0.16, 16.0),  # slightly inharmonic shimmer, bell character
    (5.6, 0.07, 30.0),  # strike transient
)


def render_note(freq: float, rate: int = SAMPLE_RATE) -> list[float]:
    """Render one bell note (float samples, peak about 1.0) ending in silence."""
    note_len = int(NOTE_SECONDS * rate)
    release_start = NOTE_SECONDS - NOTE_RELEASE_SECONDS
    usable = [p for p in NOTE_PARTIALS if freq * p[0] < rate * 0.45]
    two_pi_f = 2.0 * math.pi * freq
    samples = [0.0] * note_len
    for k in range(note_len):
        t = k / rate
        attack = min(1.0, t / 0.002)
        # Raised-cosine release so the buffer ends at exactly zero instead of
        # cutting the (still oscillating) decay tail, which clicks.
        if t >= release_start:
            release = 0.5 * (1.0 + math.cos(math.pi * (t - release_start) / NOTE_RELEASE_SECONDS))
        else:
            release = 1.0
        value = 0.0
        for mult, amp, decay in usable:
            value += amp * math.exp(-decay * t) * math.sin(two_pi_f * mult * t)
        samples[k] = attack * release * value
    return samples


@dataclass(slots=True)
class RampSpec:
    """Describe the volume ramp."""

    start: float  # gain at t=0 (0..1)
    seconds: float  # seconds until full gain

    def gain(self, t: float) -> float:
        """Return gain (0..1) at ``t`` seconds after the alarm started."""
        if self.seconds <= 0 or t >= self.seconds:
            return 1.0
        if t <= 0:
            return self.start
        return self.start + (1.0 - self.start) * (t / self.seconds)

    def ffmpeg_expr(self, offset: float) -> str:
        """Return an ffmpeg volume expression for this ramp."""
        if self.seconds <= 0:
            return "1"
        start = f"{self.start:.4f}"
        return f"min(1\\,{start}+(1-{start})*(t+{offset:.3f})/{self.seconds:.3f})"


def wav_header(num_samples: int, rate: int = SAMPLE_RATE, channels: int = 1) -> bytes:
    """Build a 16-bit PCM WAV header."""
    data_bytes = num_samples * channels * 2
    return b"".join(
        (
            b"RIFF",
            struct.pack("<I", 36 + data_bytes),
            b"WAVE",
            b"fmt ",
            struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * channels * 2, channels * 2, 16),
            b"data",
            struct.pack("<I", data_bytes),
        )
    )


# -------------------------------------------------------------------- FLAC
#
# A FLAC stream is the ``fLaC`` marker, a STREAMINFO metadata block and then
# frames. Every frame carries a small header (CRC-8 protected), one subframe
# per channel and a CRC-16 over the whole frame. Using VERBATIM subframes
# (raw samples, no prediction) needs no maths, costs the same bandwidth as
# WAV and is something every FLAC decoder must support.

FLAC_SAMPLE_BITS = 16
_FLAC_BLOCK_SIZE_CODES = {
    192: 0x1,
    576: 0x2,
    1152: 0x3,
    2304: 0x4,
    4608: 0x5,
    256: 0x8,
    512: 0x9,
    1024: 0xA,
    2048: 0xB,
    4096: 0xC,
    8192: 0xD,
    16384: 0xE,
    32768: 0xF,
}
_FLAC_SAMPLE_RATE_CODES = {
    88200: 0x1,
    176400: 0x2,
    192000: 0x3,
    8000: 0x4,
    16000: 0x5,
    22050: 0x6,
    24000: 0x7,
    32000: 0x8,
    44100: 0x9,
    48000: 0xA,
    96000: 0xB,
}


def _crc_table(poly: int, width: int) -> list[int]:
    top = 1 << (width - 1)
    mask = (1 << width) - 1
    table = []
    for byte in range(256):
        crc = byte << (width - 8)
        for _ in range(8):
            crc = ((crc << 1) ^ poly) if crc & top else (crc << 1)
        table.append(crc & mask)
    return table


_CRC8_TABLE = _crc_table(0x07, 8)
_CRC16_TABLE = _crc_table(0x8005, 16)


def flac_crc8(data: bytes | bytearray) -> int:
    """CRC-8 (polynomial 0x07, no init/xor) as used for FLAC frame headers."""
    crc = 0
    table = _CRC8_TABLE
    for byte in data:
        crc = table[crc ^ byte]
    return crc


def flac_crc16(data: bytes | bytearray) -> int:
    """CRC-16 (polynomial 0x8005, no init/xor) as used for FLAC frames."""
    crc = 0
    table = _CRC16_TABLE
    for byte in data:
        crc = ((crc << 8) & 0xFFFF) ^ table[(crc >> 8) ^ byte]
    return crc


def flac_utf8_number(value: int) -> bytes:
    """Encode a frame number the way FLAC frame headers do (UTF-8 style, up to 36 bits)."""
    if value < 0:
        raise ValueError("frame number must not be negative")
    if value < 0x80:
        return bytes((value,))
    for extra in range(1, 7):
        if value < 1 << (6 + 5 * extra):
            break
    else:
        raise ValueError("frame number too large")
    lead = ((0xFF << (7 - extra)) & 0xFF) | (value >> (6 * extra))
    tail = [0x80 | ((value >> (6 * i)) & 0x3F) for i in range(extra - 1, -1, -1)]
    return bytes([lead, *tail])


class FlacWriter:
    """Write a 16-bit FLAC stream frame by frame without compressing."""

    def __init__(
        self,
        *,
        rate: int = SAMPLE_RATE,
        channels: int = 1,
        total_samples: int = 0,
        block_size: int = FLAC_BLOCK_SIZE,
    ) -> None:
        if not 1 <= channels <= 8:
            raise ValueError("FLAC supports 1 to 8 channels")
        if not 16 <= block_size <= 65535:
            raise ValueError("FLAC block size must be 16..65535")
        if not 0 < rate < 1 << 20:
            raise ValueError("unsupported sample rate")
        self.rate = rate
        self.channels = channels
        self.total_samples = total_samples  # 0 means unknown
        self.block_size = block_size
        self._frame_number = 0

    def header(self) -> bytes:
        """Return the ``fLaC`` marker followed by the STREAMINFO block."""
        packed = (
            (self.rate << 44)
            | ((self.channels - 1) << 41)
            | ((FLAC_SAMPLE_BITS - 1) << 36)
            | (self.total_samples & ((1 << 36) - 1))
        )
        streaminfo = (
            struct.pack(">HH", self.block_size, self.block_size)
            + bytes(6)  # min / max frame size unknown
            + packed.to_bytes(8, "big")
            + bytes(16)  # MD5 of the decoded audio unknown
        )
        # 0x80: this is the last metadata block; block type 0 = STREAMINFO
        return b"fLaC" + b"\x80" + len(streaminfo).to_bytes(3, "big") + streaminfo

    def frame(self, samples: array) -> bytes:
        """Encode one block of interleaved 16-bit samples as a VERBATIM frame.

        Every block but the last must hold exactly ``block_size`` samples per
        channel; the last one may be shorter.
        """
        count = len(samples) // self.channels
        if not 1 <= count <= self.block_size or len(samples) != count * self.channels:
            raise ValueError("bad block length")
        header = bytearray((0xFF, 0xF8))  # sync code, fixed block size strategy
        code = _FLAC_BLOCK_SIZE_CODES.get(count)
        extra = b""
        if code is None:
            if count <= 256:
                code, extra = 0x6, bytes((count - 1,))
            else:
                code, extra = 0x7, struct.pack(">H", count - 1)
        header.append((code << 4) | _FLAC_SAMPLE_RATE_CODES.get(self.rate, 0))
        header.append(((self.channels - 1) << 4) | (0b100 << 1))  # independent channels, 16 bit
        header += flac_utf8_number(self._frame_number) + extra
        header.append(flac_crc8(header))
        self._frame_number += 1

        parts = [bytes(header)]
        for channel in range(self.channels):
            block = samples[channel :: self.channels] if self.channels > 1 else samples
            block = array("h", block.tobytes())
            if sys.byteorder == "little":
                block.byteswap()
            # subframe header: VERBATIM, no wasted bits; then the raw samples
            parts.append(b"\x02" + block.tobytes())
        frame = b"".join(parts)
        return frame + struct.pack(">H", flac_crc16(frame))


def build_default_loop(rate: int = SAMPLE_RATE) -> array:
    """Render the built-in alarm sound: a 4 second bell arpeggio loop.

    Three ascending four-note bell arpeggios (C5 E5 G5 C6) with a short rest.
    The bright, quickly decaying upper partials keep the notes distinct while
    the fundamental rings on.
    """
    rendered = {freq: render_note(freq, rate) for freq in NOTE_FREQUENCIES}
    note_len = int(NOTE_SECONDS * rate)

    total = int(LOOP_SECONDS * rate)
    buf = [0.0] * total
    for group in range(GROUPS):
        base = group * GROUP_SPACING_SECONDS
        for idx, freq in enumerate(NOTE_FREQUENCIES):
            start = int((base + idx * NOTE_SPACING_SECONDS) * rate)
            note = rendered[freq]
            end = min(total, start + note_len)
            for k in range(start, end):
                buf[k] += note[k - start]

    peak = max(abs(x) for x in buf) or 1.0
    scale = 0.85 * 32767 / peak
    return array("h", (int(max(-32767.0, min(32767.0, x * scale))) for x in buf))


def default_sound_wav(loop: array) -> bytes:
    """Return the built-in loop as a complete WAV file (one iteration)."""
    return wav_header(len(loop)) + loop.tobytes()


class Pacer:
    """Sleep so that produced audio stays at most ``lead`` seconds ahead."""

    def __init__(self, lead: float = STREAM_LEAD_SECONDS) -> None:
        self._lead = lead
        self._started = time_mod.monotonic()

    async def wait_for(self, audio_position: float) -> None:
        """Block until wall clock allows ``audio_position`` to be sent."""
        ahead = audio_position - (time_mod.monotonic() - self._started) - self._lead
        if ahead > 0:
            await asyncio.sleep(ahead)


async def stream_builtin(
    loop: array,
    *,
    duration: float,
    offset: float,
    ramp: RampSpec,
    stop: asyncio.Event,
    rate: int = SAMPLE_RATE,
) -> AsyncIterator[bytes]:
    """Stream the built-in loop as FLAC for ``duration`` seconds.

    ``offset`` is how many seconds of the alarm already elapsed before this
    stream started; it keeps the ramp continuous across segments.
    """
    total_samples = int(duration * rate)
    writer = FlacWriter(rate=rate, channels=1, total_samples=total_samples)
    yield writer.header()

    block = writer.block_size
    blocks_per_chunk = max(1, round(STREAM_CHUNK_SECONDS * rate / block))
    loop_len = len(loop)
    loop_pos = int(offset * rate) % loop_len
    produced = 0
    pacer = Pacer()

    while produced < total_samples and not stop.is_set():
        frames = []
        for _ in range(blocks_per_chunk):
            count = min(block, total_samples - produced)
            if count <= 0:
                break
            t0 = offset + produced / rate
            t1 = offset + (produced + count) / rate
            g0 = ramp.gain(t0)
            g1 = ramp.gain(t1)
            # Gather samples (wrapping around the loop)
            if loop_pos + count <= loop_len:
                raw = loop[loop_pos : loop_pos + count]
            else:
                raw = loop[loop_pos:] + loop[: (loop_pos + count) - loop_len]
            loop_pos = (loop_pos + count) % loop_len
            if g0 < 1.0 or g1 < 1.0:
                step = (g1 - g0) / count
                raw = array("h", [int(s * (g0 + step * i)) for i, s in enumerate(raw)])
            frames.append(writer.frame(raw))
            produced += count
        await pacer.wait_for(produced / rate)
        yield b"".join(frames)


async def stream_ffmpeg(
    binary: str,
    source: str,
    *,
    duration: float,
    offset: float,
    ramp: RampSpec,
    stop: asyncio.Event,
    rate: int = SAMPLE_RATE,
    on_started: Callable[[], None] | None = None,
) -> AsyncIterator[bytes]:
    """Loop ``source`` through ffmpeg with a gain ramp, streaming FLAC bytes."""
    cmd = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-re",
        "-stream_loop",
        "-1",
        "-i",
        source,
        "-t",
        f"{duration:.3f}",
        "-af",
        f"volume=volume='{ramp.ffmpeg_expr(offset)}':eval=frame",
        "-ac",
        "1",
        "-ar",
        str(rate),
        "-sample_fmt",
        "s16",
        "-f",
        "flac",
        "-flush_packets",
        "1",
        "pipe:1",
    ]
    _LOGGER.debug("Starting ffmpeg: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None
    got_data = False
    try:
        while not stop.is_set():
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            if not got_data:
                got_data = True
                if on_started:
                    on_started()
            yield chunk
    finally:
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        try:
            stderr = await asyncio.wait_for(proc.stderr.read(), 2)
        except (TimeoutError, ValueError):
            stderr = b""
        await proc.wait()
        if stderr.strip():
            _LOGGER.warning("ffmpeg reported: %s", stderr.decode(errors="replace").strip())
    if not got_data:
        raise RuntimeError("ffmpeg produced no audio")
