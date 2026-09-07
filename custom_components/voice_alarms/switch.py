"""One switch per alarm to enable/disable it."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import get_manager
from .const import SIGNAL_ALARMS_UPDATED
from .entity import target_device_info
from .manager import AlarmManager
from .models import Alarm

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create a switch for every alarm, following additions and removals."""
    manager = get_manager(hass)
    known: set[str] = set()

    @callback
    def sync_alarms() -> None:
        new = [a for a in manager.alarms.values() if a.id not in known]
        for alarm in new:
            known.add(alarm.id)
        if new:
            async_add_entities(AlarmSwitch(manager, a, known) for a in new)

    sync_alarms()
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_ALARMS_UPDATED, sync_alarms))


class AlarmSwitch(SwitchEntity):
    """Enable / disable one alarm."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: AlarmManager, alarm: Alarm, known: set[str]) -> None:
        self.manager = manager
        self.alarm_id = alarm.id
        self._known = known
        self._attr_unique_id = f"alarm_{alarm.id}"
        target = manager.target(alarm.target)
        if target is not None:
            self._attr_device_info = target_device_info(target)

    @property
    def _alarm(self) -> Alarm | None:
        return self.manager.get_alarm(self.alarm_id)

    @property
    def name(self) -> str | None:
        """Alarm label."""
        alarm = self._alarm
        return alarm.label if alarm else None

    @property
    def icon(self) -> str:
        """Icon by kind."""
        alarm = self._alarm
        if alarm and alarm.is_reminder:
            return "mdi:bell-ring-outline" if alarm.enabled else "mdi:bell-off-outline"
        return "mdi:alarm" if (alarm and alarm.enabled) else "mdi:alarm-off"

    @property
    def available(self) -> bool:
        """Unavailable once the alarm is gone."""
        return self._alarm is not None

    @property
    def is_on(self) -> bool:
        """Enabled?"""
        alarm = self._alarm
        return bool(alarm and alarm.enabled)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """All alarm fields."""
        alarm = self._alarm
        return alarm.public_dict() if alarm else {}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable."""
        await self.manager.async_update_alarm(self.alarm_id, enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable."""
        await self.manager.async_update_alarm(self.alarm_id, enabled=False)

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_ALARMS_UPDATED, self._updated)
        )

    @callback
    def _updated(self) -> None:
        if self._alarm is None:
            self.hass.async_create_task(self._async_remove_self())
            return
        self.async_write_ha_state()

    async def _async_remove_self(self) -> None:
        self._known.discard(self.alarm_id)
        registry = er.async_get(self.hass)
        entity_id = self.entity_id
        await self.async_remove(force_remove=True)
        if entity_id and registry.async_get(entity_id):
            registry.async_remove(entity_id)
