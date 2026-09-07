"""Tests for the built-in sound and the ramp maths."""

from __future__ import annotations

import pytest

from custom_components.voice_alarms.audio import (
    GROUP_SPACING_SECONDS,
    GROUPS,
    LOOP_SECONDS,
    NOTE_FREQUENCIES,
    NOTE_SECONDS,
    NOTE_SPACING_SECONDS,
    RampSpec,
    build_default_loop,
    render_note,
    wav_header,
)
from custom_components.voice_alarms.const import SAMPLE_RATE


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
