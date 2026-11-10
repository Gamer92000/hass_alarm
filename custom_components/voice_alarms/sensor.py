"""Next alarm sensors."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import get_manager
from .entity import VoiceAlarmsTargetEntity, async_track_targets


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up one 'next alarm' sensor per satellite."""
    async_track_targets(hass, entry, get_manager(hass), async_add_entities, (NextAlarmSensor,))


class NextAlarmSensor(VoiceAlarmsTargetEntity, SensorEntity):
    """Timestamp of the next alarm on a satellite."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "next_alarm"
    # The full alarm list is for automations and the frontend, not for history.
    _unrecorded_attributes = frozenset({"alarms"})

    _unique_suffix = "_next_alarm"

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
