"""Audio generation and streaming for Voice Alarms.

Two sources exist:

* The built-in sound, a synthesised bell arpeggio loop rendered in pure
  Python (no numpy / audioop dependency).
* A custom sound (URL, ``media-source://`` id or local file) which is looped
  and gain-ramped by ffmpeg.

Both produce a WAV stream whose loudness ramps up over the first
``ramp_seconds`` of the alarm. The stream is paced to real time so that the
satellite never buffers more than a couple of seconds, which keeps dismissal
snappy.
"""

from __future__ import annotations

import asyncio
import logging
import math
import struct
import time as time_mod
from array import array
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from .const import SAMPLE_RATE, STREAM_CHUNK_SECONDS, STREAM_LEAD_SECONDS

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
    """Stream the built-in loop as WAV for ``duration`` seconds.

    ``offset`` is how many seconds of the alarm already elapsed before this
    stream started; it keeps the ramp continuous across segments.
    """
    total_samples = int(duration * rate)
    yield wav_header(total_samples, rate)

    chunk = int(STREAM_CHUNK_SECONDS * rate)
    loop_len = len(loop)
    loop_pos = int(offset * rate) % loop_len
    produced = 0
    pacer = Pacer()

    while produced < total_samples and not stop.is_set():
        count = min(chunk, total_samples - produced)
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
        if g0 >= 1.0 and g1 >= 1.0:
            data = raw.tobytes()
        else:
            step = (g1 - g0) / count
            data = array("h", [int(s * (g0 + step * i)) for i, s in enumerate(raw)]).tobytes()
        produced += count
        await pacer.wait_for(produced / rate)
        yield data


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
    """Loop ``source`` through ffmpeg with a gain ramp, streaming WAV bytes."""
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
        "-f",
        "wav",
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
