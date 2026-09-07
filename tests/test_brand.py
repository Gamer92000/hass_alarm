"""Tests for the brand images Home Assistant serves for the integration."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.voice_alarms.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

BRAND_DIR = Path(__file__).resolve().parent.parent / "custom_components" / DOMAIN / "brand"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_size(data: bytes) -> tuple[int, int]:
    """Return (width, height) from a PNG's IHDR chunk."""
    assert data.startswith(PNG_SIGNATURE)
    assert data[12:16] == b"IHDR"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


@pytest.mark.parametrize(("name", "size"), [("icon.png", 256), ("icon@2x.png", 512)])
def test_brand_files(name: str, size: int) -> None:
    """The committed brand images have the sizes Home Assistant expects."""
    assert _png_size((BRAND_DIR / name).read_bytes()) == (size, size)


@pytest.mark.parametrize(
    ("image", "size"),
    [("icon.png", 256), ("icon@2x.png", 512), ("logo.png", 256), ("dark_icon@2x.png", 512)],
)
async def test_brand_served_locally(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, image: str, size: int
) -> None:
    """Home Assistant serves the integration's own images instead of the CDN placeholder."""
    assert await async_setup_component(hass, "brands", {})
    client = await hass_client()
    # placeholder=no makes a missing local file a 404 instead of a CDN fetch.
    resp = await client.get(f"/api/brands/integration/{DOMAIN}/{image}?placeholder=no")
    assert resp.status == 200
    assert resp.content_type == "image/png"
    assert _png_size(await resp.read()) == (size, size)
