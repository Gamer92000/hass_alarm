"""Voice Alarms: alarms and reminders for Home Assistant voice satellites."""

from __future__ import annotations

import logging
from array import array
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
from homeassistant.util.hass_dict import HassKey

from .audio import build_default_loop, default_sound_wav
from .const import DOMAIN, PANEL_STATIC_URL, PANEL_URL_PATH, PLATFORMS
from .http import (
    DATA_DEFAULT_WAV,
    DATA_STREAMS,
    StreamRegistry,
    VoiceAlarmDefaultSoundView,
    VoiceAlarmStreamView,
)
from .intents import async_register_intents, async_unregister_intents
from .manager import AlarmManager
from .services import async_register_services, async_unregister_services
from .websocket import async_register_websocket

_LOGGER = logging.getLogger(__name__)

DATA_MANAGER: HassKey[AlarmManager] = HassKey(f"{DOMAIN}_manager")
DATA_LOOP: HassKey[array] = HassKey(f"{DOMAIN}_loop")
DATA_SHARED_READY: HassKey[bool] = HassKey(f"{DOMAIN}_shared_ready")

type VoiceAlarmsConfigEntry = ConfigEntry


@callback
def get_manager(hass: HomeAssistant) -> AlarmManager:
    """Return the running manager."""
    return hass.data[DATA_MANAGER]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Nothing to do for YAML."""
    return True


async def _async_setup_shared(hass: HomeAssistant) -> None:
    """Register things that must only be registered once per HA run."""
    if hass.data.get(DATA_SHARED_READY):
        return
    registry = StreamRegistry()
    hass.data[DATA_STREAMS] = registry
    hass.http.register_view(VoiceAlarmStreamView(registry))
    hass.http.register_view(VoiceAlarmDefaultSoundView(hass))

    loop = await hass.async_add_executor_job(build_default_loop)
    hass.data[DATA_LOOP] = loop
    hass.data[DATA_DEFAULT_WAV] = default_sound_wav(loop)

    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_STATIC_URL, str(frontend_dir), cache_headers=False)]
    )
    async_register_websocket(hass, lambda: hass.data.get(DATA_MANAGER))
    hass.data[DATA_SHARED_READY] = True


async def async_setup_entry(hass: HomeAssistant, entry: VoiceAlarmsConfigEntry) -> bool:
    """Set up Voice Alarms from a config entry."""
    await _async_setup_shared(hass)

    manager = AlarmManager(hass, entry, hass.data[DATA_STREAMS], hass.data[DATA_LOOP])
    await manager.async_load()
    hass.data[DATA_MANAGER] = manager

    async_register_intents(hass, manager)
    async_register_services(hass, manager)

    integration = await async_get_integration(hass, DOMAIN)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name="voice-alarms-panel",
        sidebar_title="Voice Alarms",
        sidebar_icon="mdi:alarm",
        module_url=f"{PANEL_STATIC_URL}/panel.js?v={integration.version}",
        require_admin=False,
        config={"domain": DOMAIN},
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await manager.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VoiceAlarmsConfigEntry) -> bool:
    """Unload."""
    manager = hass.data.get(DATA_MANAGER)
    if manager is not None:
        await manager.async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    async_unregister_intents(hass)
    async_unregister_services(hass)
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    hass.data.pop(DATA_MANAGER, None)
    return unloaded
