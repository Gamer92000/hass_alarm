"""Base entities for Voice Alarms."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_ALARMS_UPDATED, SIGNAL_RINGING_UPDATED
from .manager import AlarmManager
from .targets import Target


def target_device_info(target: Target) -> DeviceInfo:
    """Device that groups all entities belonging to one satellite."""
    return DeviceInfo(
        identifiers={(DOMAIN, target.entity_id)},
        name=f"Voice Alarms {target.name}",
        manufacturer="Voice Alarms",
        model="Satellite alarms",
        entry_type=DeviceEntryType.SERVICE,
    )


class VoiceAlarmsTargetEntity(Entity):
    """Entity bound to one satellite target."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: AlarmManager, target: Target) -> None:
        self.manager = manager
        self.target = target
        self._attr_device_info = target_device_info(target)

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        for signal in (SIGNAL_ALARMS_UPDATED, SIGNAL_RINGING_UPDATED):
            self.async_on_remove(async_dispatcher_connect(self.hass, signal, self._updated))

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()
