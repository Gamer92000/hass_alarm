"""Next alarm sensors."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import get_manager
from .const import SIGNAL_TARGETS_UPDATED
from .entity import VoiceAlarmsTargetEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up one 'next alarm' sensor per satellite."""
    manager = get_manager(hass)
    known: set[str] = set()

    @callback
    def sync_targets() -> None:
        new = [t for t in manager.targets() if t.entity_id not in known]
        for target in new:
            known.add(target.entity_id)
        if new:
            async_add_entities(NextAlarmSensor(manager, t) for t in new)

    sync_targets()
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_TARGETS_UPDATED, sync_targets))


class NextAlarmSensor(VoiceAlarmsTargetEntity, SensorEntity):
    """Timestamp of the next alarm on a satellite."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "next_alarm"

    def __init__(self, manager, target) -> None:
        super().__init__(manager, target)
        self._attr_unique_id = f"{target.entity_id}_next_alarm"

    @property
    def native_value(self) -> datetime | None:
        """Next occurrence."""
        nxt = self.manager.next_for_target(self.target.entity_id)
        return nxt[1] if nxt else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Details about the next alarm and all alarms on this satellite."""
        nxt = self.manager.next_for_target(self.target.entity_id)
        alarms = self.manager.alarms_for_target(self.target.entity_id)
        return {
            "satellite": self.target.entity_id,
            "alarm_id": nxt[0].id if nxt else None,
            "alarm_name": nxt[0].label if nxt else None,
            "alarm_kind": nxt[0].kind if nxt else None,
            "alarm_count": len(alarms),
            "alarms": [a.public_dict() for a in alarms],
        }
