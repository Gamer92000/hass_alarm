"""Render the built-in alarm sound to a WAV file so it can be auditioned.

Usage: python tools/render_default_sound.py [output.wav] [--ramp]

With --ramp the file contains 40 seconds of the looped sound with the default
volume ramp applied, exactly as a satellite would hear the start of an alarm.
Only needs the ``homeassistant`` package importable (for one constant); the
integration itself is not loaded.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "voice_alarms"


def _load_audio_module() -> types.ModuleType:
    """Import audio.py (and its const.py) without running the package __init__."""
    package = types.ModuleType("_voice_alarms_audio")
    package.__path__ = [str(PKG_DIR)]
    sys.modules[package.__name__] = package
    for name in ("const", "audio"):
        spec = importlib.util.spec_from_file_location(
            f"{package.__name__}.{name}", PKG_DIR / f"{name}.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return sys.modules[f"{package.__name__}.audio"]


async def _ramped(audio: types.ModuleType) -> bytes:
    audio.STREAM_LEAD_SECONDS = 10_000  # no real-time pacing for the export
    loop = audio.build_default_loop()
    chunks = [
        chunk
        async for chunk in audio.stream_builtin(
            loop, duration=40, offset=0, ramp=audio.RampSpec(0.1, 30), stop=asyncio.Event()
        )
    ]
    return b"".join(chunks)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0]) if args else Path("voice_alarm_default.wav")
    audio = _load_audio_module()
    if "--ramp" in sys.argv:
        data = asyncio.run(_ramped(audio))
    else:
        data = audio.default_sound_wav(audio.build_default_loop())
    out.write_bytes(data)
    print(f"wrote {out} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
