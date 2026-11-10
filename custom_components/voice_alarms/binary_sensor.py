"""Ringing binary sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import get_manager
from .entity import VoiceAlarmsTargetEntity, async_track_targets


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up one 'ringing' sensor per satellite."""
    async_track_targets(hass, entry, get_manager(hass), async_add_entities, (RingingBinarySensor,))


class RingingBinarySensor(VoiceAlarmsTargetEntity, BinarySensorEntity):
    """On while an alarm or reminder is active on the satellite."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_translation_key = "ringing"

    _unique_suffix = "_ringing"

    @property
    def is_on(self) -> bool:
        """True while ringing/paused."""
        return self.manager.session_for_target(self.target.entity_id) is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Session details."""
        session = self.manager.session_for_target(self.target.entity_id)
        if session is None:
            return {"satellite": self.target.entity_id}
        return {"satellite": self.target.entity_id, **session.to_dict()}
