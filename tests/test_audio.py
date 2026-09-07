"""Tests for the built-in sound, the ramp maths and the FLAC writer."""

from __future__ import annotations

import asyncio
from array import array
from types import SimpleNamespace

import pytest

from custom_components.voice_alarms import audio
from custom_components.voice_alarms.audio import (
    GROUP_SPACING_SECONDS,
    GROUPS,
    LOOP_SECONDS,
    NOTE_FREQUENCIES,
    NOTE_SECONDS,
    NOTE_SPACING_SECONDS,
    FlacWriter,
    RampSpec,
    build_default_loop,
    flac_crc8,
    flac_crc16,
    flac_utf8_number,
    render_note,
    stream_builtin,
    stream_ffmpeg,
    wav_header,
)
from custom_components.voice_alarms.const import FLAC_BLOCK_SIZE, SAMPLE_RATE
from tests.flac_util import parse_flac


@pytest.mark.parametrize("freq", NOTE_FREQUENCIES)
def test_note_starts_and_ends_in_silence(freq) -> None:
    """A note must fade to zero before its buffer ends, otherwise it clicks."""
    note = render_note(freq)
    assert len(note) == int(NOTE_SECONDS * SAMPLE_RATE)
    assert note[0] == 0.0
    assert max(abs(s) for s in note[-8:]) < 1e-4
    assert max(abs(s) for s in note) > 0.5
    # smooth release: no sample-to-sample jump larger than the waveform slope allows
    tail = note[-int(0.1 * SAMPLE_RATE) :]
    assert max(abs(b - a) for a, b in zip(tail, tail[1:], strict=False)) < 0.02


def test_loop_layout() -> None:
    loop = build_default_loop()
    assert len(loop) == int(LOOP_SECONDS * SAMPLE_RATE)
    last_start = (GROUPS - 1) * GROUP_SPACING_SECONDS + (
        len(NOTE_FREQUENCIES) - 1
    ) * NOTE_SPACING_SECONDS
    last_end = int((last_start + NOTE_SECONDS) * SAMPLE_RATE)
    # the loop ends with silence after the last note, so repeating it is seamless
    assert loop[0] == 0
    assert max(abs(s) for s in loop[last_end:]) == 0
    assert max(abs(s) for s in loop[last_end - 3 : last_end]) <= 2
    # and the sound is loud
    assert max(abs(s) for s in loop) > 0.8 * 32767


def test_wav_header() -> None:
    header = wav_header(10, 44100)
    assert len(header) == 44
    assert header[:4] == b"RIFF" and header[8:12] == b"WAVE"


@pytest.mark.parametrize(
    ("t", "expected"),
    [(-1, 0.1), (0, 0.1), (15, 0.55), (30, 1.0), (60, 1.0)],
)
def test_ramp_gain(t, expected) -> None:
    assert RampSpec(0.1, 30).gain(t) == pytest.approx(expected)
    assert RampSpec(0.1, 0).gain(0) == 1.0


# ------------------------------------------------------------------- FLAC


def test_flac_crcs_match_reference_values() -> None:
    # check values of CRC-8/SMBUS and CRC-16/UMTS from the CRC catalogue
    assert flac_crc8(b"123456789") == 0xF4
    assert flac_crc16(b"123456789") == 0xFEE8
    assert flac_crc8(b"") == 0 and flac_crc16(b"") == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, b"\x00"),
        (0x7F, b"\x7f"),
        (0x80, b"\xc2\x80"),
        (0x7FF, b"\xdf\xbf"),
        (0x800, b"\xe0\xa0\x80"),
        (0xFFFF, b"\xef\xbf\xbf"),
        (0x10000, b"\xf0\x90\x80\x80"),
        (0x1FFFFF, b"\xf7\xbf\xbf\xbf"),
        (0x200000, b"\xf8\x88\x80\x80\x80"),
        (0x3FFFFFF, b"\xfb\xbf\xbf\xbf\xbf"),
        (0x4000000, b"\xfc\x84\x80\x80\x80\x80"),
        (0x7FFFFFFF, b"\xfd\xbf\xbf\xbf\xbf\xbf"),
        (0x80000000, b"\xfe\x82\x80\x80\x80\x80\x80"),
    ],
)
def test_flac_utf8_number(value, expected) -> None:
    assert flac_utf8_number(value) == expected


def test_flac_utf8_number_limits() -> None:
    with pytest.raises(ValueError):
        flac_utf8_number(1 << 36)
    with pytest.raises(ValueError):
        flac_utf8_number(-1)


def test_flac_writer_round_trip() -> None:
    """Full, short (16 bit length) and tiny (8 bit length) blocks survive a strict parse."""
    blocks = [
        array("h", [((i * 37) % 65536) - 32768 for i in range(FLAC_BLOCK_SIZE)]),
        array("h", range(-500, 500)),
        array("h", [32767, -32768] * 50),
    ]
    total = sum(len(block) for block in blocks)
    writer = FlacWriter(rate=SAMPLE_RATE, channels=1, total_samples=total)
    data = writer.header() + b"".join(writer.frame(block) for block in blocks)
    stream = parse_flac(data)
    assert (stream.rate, stream.channels, stream.bits) == (SAMPLE_RATE, 1, 16)
    assert stream.block_size == FLAC_BLOCK_SIZE
    assert stream.total_samples == total
    assert stream.frames == 3
    assert stream.samples == blocks[0] + blocks[1] + blocks[2]


def test_flac_writer_stereo_and_unlisted_rate() -> None:
    writer = FlacWriter(rate=22050, channels=2, block_size=64)
    interleaved = array("h", [v for i in range(64) for v in (i, -i)])
    data = writer.header() + writer.frame(interleaved) + writer.frame(interleaved[:20])
    stream = parse_flac(data)
    assert (stream.rate, stream.channels, stream.frames) == (22050, 2, 2)
    assert stream.samples == interleaved + interleaved[:20]
    # a rate without a frame header code is signalled as "see STREAMINFO"
    odd = FlacWriter(rate=12345, channels=1, block_size=16)
    stream = parse_flac(odd.header() + odd.frame(array("h", range(16))))
    assert stream.rate == 12345
    assert list(stream.samples) == list(range(16))


def test_flac_writer_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        FlacWriter(channels=0)
    with pytest.raises(ValueError):
        FlacWriter(block_size=8)
    writer = FlacWriter(channels=2, block_size=16)
    with pytest.raises(ValueError):
        writer.frame(array("h", range(3)))  # not a whole number of sample pairs
    with pytest.raises(ValueError):
        writer.frame(array("h", range(34)))  # 17 per channel > block size
    with pytest.raises(ValueError):
        writer.frame(array("h"))


@pytest.fixture
def no_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def wait_for(self, _position: float) -> None:
        return None

    monkeypatch.setattr(audio.Pacer, "wait_for", wait_for)


async def _collect(loop: array, **kwargs) -> bytes:
    chunks = [chunk async for chunk in stream_builtin(loop, stop=asyncio.Event(), **kwargs)]
    return b"".join(chunks)


async def test_stream_builtin_is_valid_flac(no_pacing) -> None:
    loop = build_default_loop()
    data = await _collect(loop, duration=1.5, offset=0, ramp=RampSpec(1.0, 0))
    stream = parse_flac(data)
    total = int(1.5 * SAMPLE_RATE)
    assert (stream.rate, stream.channels, stream.total_samples) == (SAMPLE_RATE, 1, total)
    assert stream.frames == -(-total // FLAC_BLOCK_SIZE)
    assert stream.samples == loop[:total]  # without a ramp the loop is passed through verbatim


async def test_stream_builtin_ramp_and_offset(no_pacing) -> None:
    loop = build_default_loop()
    ramp = RampSpec(0.1, 30)
    start = parse_flac(await _collect(loop, duration=1, offset=0, ramp=ramp)).samples
    later = parse_flac(
        await _collect(loop, duration=1, offset=LOOP_SECONDS * 10, ramp=ramp)
    ).samples
    # 40 s in: same loop position, ramp finished
    assert later == loop[:SAMPLE_RATE]
    assert max(abs(s) for s in start) < max(abs(s) for s in later)
    # at the start every sample is scaled by the ramp gain at its own time
    window = range(2000, 2100)
    assert any(loop[i] for i in window)
    for i in window:
        assert abs(start[i] - int(loop[i] * ramp.gain(i / SAMPLE_RATE))) <= 1


async def test_stream_builtin_stops(no_pacing) -> None:
    loop = build_default_loop()
    stop = asyncio.Event()
    chunks = []
    async for chunk in stream_builtin(loop, duration=10, offset=0, ramp=RampSpec(1, 0), stop=stop):
        chunks.append(chunk)
        if len(chunks) == 3:
            stop.set()
    assert len(chunks) == 3  # header + two chunks, then the stop was honoured
    stream = parse_flac(b"".join(chunks))
    assert 0 < stream.frames < 10 * SAMPLE_RATE / FLAC_BLOCK_SIZE


async def test_stream_ffmpeg_command(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    async def fake_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        stdout = asyncio.StreamReader()
        stdout.feed_data(b"fLaC-fake")
        stdout.feed_eof()
        stderr = asyncio.StreamReader()
        stderr.feed_eof()

        async def wait() -> int:
            return 0

        return SimpleNamespace(
            stdout=stdout, stderr=stderr, returncode=0, wait=wait, kill=lambda: None
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    chunks = [
        chunk
        async for chunk in stream_ffmpeg(
            "ffmpeg",
            "/tmp/x.mp3",
            duration=12.5,
            offset=3,
            ramp=RampSpec(0.1, 30),
            stop=asyncio.Event(),
        )
    ]
    assert chunks == [b"fLaC-fake"]
    cmd = captured["cmd"]
    assert cmd[0] == "ffmpeg" and cmd[-1] == "pipe:1"
    assert cmd[cmd.index("-i") + 1] == "/tmp/x.mp3"
    assert cmd[cmd.index("-t") + 1] == "12.500"
    assert cmd[cmd.index("-f") + 1] == "flac"
    assert cmd[cmd.index("-sample_fmt") + 1] == "s16"
    assert cmd[cmd.index("-ar") + 1] == str(SAMPLE_RATE)
    assert "min(1\\,0.1000+(1-0.1000)*(t+3.000)/30.000)" in cmd[cmd.index("-af") + 1]
