"""Ringing binary sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up one 'ringing' sensor per satellite."""
    manager = get_manager(hass)
    known: set[str] = set()

    @callback
    def sync_targets() -> None:
        new = [t for t in manager.targets() if t.entity_id not in known]
        for target in new:
            known.add(target.entity_id)
        if new:
            async_add_entities(RingingBinarySensor(manager, t) for t in new)

    sync_targets()
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_TARGETS_UPDATED, sync_targets))


class RingingBinarySensor(VoiceAlarmsTargetEntity, BinarySensorEntity):
    """On while an alarm or reminder is active on the satellite."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_translation_key = "ringing"

    def __init__(self, manager, target) -> None:
        super().__init__(manager, target)
        self._attr_unique_id = f"{target.entity_id}_ringing"

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
