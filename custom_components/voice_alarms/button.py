"""Dismiss / test buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import get_manager
from .const import DEFAULT_TEST_DURATION, SIGNAL_TARGETS_UPDATED
from .entity import VoiceAlarmsTargetEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up dismiss and test buttons per satellite."""
    manager = get_manager(hass)
    known: set[str] = set()

    @callback
    def sync_targets() -> None:
        new = [t for t in manager.targets() if t.entity_id not in known]
        for target in new:
            known.add(target.entity_id)
        if new:
            entities: list[ButtonEntity] = []
            for target in new:
                entities.append(DismissButton(manager, target))
                entities.append(TestAlarmButton(manager, target))
            async_add_entities(entities)

    sync_targets()
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_TARGETS_UPDATED, sync_targets))


class DismissButton(VoiceAlarmsTargetEntity, ButtonEntity):
    """Stop the alarm ringing on this satellite."""

    _attr_translation_key = "dismiss"

    def __init__(self, manager, target) -> None:
        super().__init__(manager, target)
        self._attr_unique_id = f"{target.entity_id}_dismiss"

    async def async_press(self) -> None:
        """Dismiss."""
        await self.manager.async_dismiss(self.target.entity_id)


class TestAlarmButton(VoiceAlarmsTargetEntity, ButtonEntity):
    """Ring the alarm sound briefly to test the satellite."""

    _attr_translation_key = "test"
    _attr_entity_registry_enabled_default = True

    def __init__(self, manager, target) -> None:
        super().__init__(manager, target)
        self._attr_unique_id = f"{target.entity_id}_test"

    async def async_press(self) -> None:
        """Ring for a few seconds."""
        await self.manager.async_ring(
            self.target, label="Test", duration=DEFAULT_TEST_DURATION, origin="test"
        )
