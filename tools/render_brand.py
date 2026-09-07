"""Render the integration's brand images from ``tools/brand_icon.svg``.

Home Assistant 2026.3+ serves the files in ``custom_components/<domain>/brand/`` itself
(``/api/brands/integration/voice_alarms/icon.png``), preferring them over the brands CDN,
so no pull request to home-assistant/brands is needed. The PNGs are committed; re-run
this after editing the SVG.

Usage: ``python tools/render_brand.py``   (needs ``pip install resvg-py``)
"""

from __future__ import annotations

from pathlib import Path

import resvg_py

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools" / "brand_icon.svg"
OUT_DIR = ROOT / "custom_components" / "voice_alarms" / "brand"

# Sizes required by Home Assistant: icon.png 256x256, icon@2x.png 512x512.
IMAGES = {"icon.png": 256, "icon@2x.png": 512}


def main() -> None:
    svg = SOURCE.read_text(encoding="utf-8")
    OUT_DIR.mkdir(exist_ok=True)
    for name, size in IMAGES.items():
        png = bytes(resvg_py.svg_to_bytes(svg_string=svg, width=size, height=size))
        (OUT_DIR / name).write_bytes(png)
        print(f"{OUT_DIR / name}: {size}x{size}, {len(png)} bytes")


if __name__ == "__main__":
    main()
