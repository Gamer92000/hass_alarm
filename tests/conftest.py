"""Test fixtures for Voice Alarms."""

from __future__ import annotations

import sys
import types
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest

if sys.platform == "win32":
    # pytest-socket's guard breaks the proactor event loop's internal socket
    # pair on Windows; keep sockets enabled there (DNS is still blocked).
    import pytest_socket

    pytest_socket.disable_socket = lambda allow_unix_socket=False: None

# assist_pipeline imports two native modules that have no wheels for every
# platform; they are irrelevant for these tests, so provide stand-ins.
for _name, _attrs in (
    ("pymicro_vad", {"MicroVad": type("MicroVad", (), {})}),
    ("pyspeex_noise", {"AudioProcessor": type("AudioProcessor", (), {})}),
):
    if _name not in sys.modules:
        try:
            __import__(_name)
        except ImportError:
            module = types.ModuleType(_name)
            for key, value in _attrs.items():
                setattr(module, key, value)
            sys.modules[_name] = module

from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.voice_alarms.const import DOMAIN  # noqa: E402
from homeassistant.components.assist_satellite import DOMAIN as SAT_DOMAIN  # noqa: E402
from homeassistant.core import HomeAssistant, ServiceCall  # noqa: E402
from homeassistant.helpers import (  # noqa: E402
    area_registry as ar,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.setup import async_setup_component  # noqa: E402

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations."""


@pytest.fixture(autouse=True)
def mock_ffmpeg_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend ffmpeg is not installed so the built-in sound path is used."""
    monkeypatch.setattr("custom_components.voice_alarms.manager.shutil.which", lambda _b: None)


@pytest.fixture
def satellites(hass: HomeAssistant) -> dict[str, dict[str, str]]:
    """Two fake assist satellites with devices, areas and media players."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    area_reg = ar.async_get(hass)
    other = MockConfigEntry(domain="esphome", title="esphome")
    other.add_to_hass(hass)
    result: dict[str, dict[str, str]] = {}
    for key, area_name in (("kitchen", "Kitchen"), ("bedroom", "Bedroom")):
        area = area_reg.async_get_or_create(area_name)
        device = dev_reg.async_get_or_create(
            config_entry_id=other.entry_id,
            identifiers={("esphome", key)},
            name=f"Voice PE {key.title()}",
        )
        dev_reg.async_update_device(device.id, area_id=area.id)
        sat = ent_reg.async_get_or_create(
            SAT_DOMAIN,
            "esphome",
            f"{key}-sat",
            suggested_object_id=f"voice_pe_{key}_assist_satellite",
            device_id=device.id,
            config_entry=other,
        )
        player = ent_reg.async_get_or_create(
            "media_player",
            "esphome",
            f"{key}-mp",
            suggested_object_id=f"voice_pe_{key}",
            device_id=device.id,
            config_entry=other,
        )
        hass.states.async_set(
            sat.entity_id, "idle", {"friendly_name": f"Voice PE {key.title()} Assist satellite"}
        )
        hass.states.async_set(
            player.entity_id, "idle", {"supported_features": 4, "volume_level": 0.4}
        )
        result[key] = {
            "satellite": sat.entity_id,
            "media_player": player.entity_id,
            "device_id": device.id,
        }
    return result


@pytest.fixture
def announce_calls(hass: HomeAssistant) -> list[ServiceCall]:
    """Replace assist_satellite.announce with a recorder that returns immediately."""
    calls: list[ServiceCall] = []

    async def handler(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register(SAT_DOMAIN, "announce", handler)
    return calls


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, satellites: dict[str, dict[str, str]], announce_calls: list[ServiceCall]
) -> AsyncGenerator[MockConfigEntry]:
    """Set up the integration with default options."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Voice Alarms", data={}, options={}, unique_id=DOMAIN
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    # The real announce service was registered by assist_satellite during setup;
    # make sure our recorder wins.
    hass.services.async_register(SAT_DOMAIN, "announce", _make_recorder(announce_calls))
    yield entry


def _make_recorder(calls: list[ServiceCall]):
    async def handler(call: ServiceCall) -> None:
        calls.append(call)

    return handler


@pytest.fixture
def manager(hass: HomeAssistant, setup_integration: MockConfigEntry):
    """The alarm manager."""
    from custom_components.voice_alarms import get_manager  # noqa: PLC0415

    return get_manager(hass)


@pytest.fixture
def mock_announce_block(hass: HomeAssistant) -> AsyncMock:
    """Announce handler that can be made to block (simulating playback)."""
    return AsyncMock()


def slot(value: Any) -> dict[str, Any]:
    """Build an intent slot."""
    return {"value": value}
