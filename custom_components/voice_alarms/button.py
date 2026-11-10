"""Dismiss / test buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import get_manager
from .const import DEFAULT_TEST_DURATION
from .entity import VoiceAlarmsTargetEntity, async_track_targets


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up dismiss and test buttons per satellite."""
    async_track_targets(
        hass,
        entry,
        get_manager(hass),
        async_add_entities,
        (
            DismissButton,
            TestAlarmButton,
        ),
    )


class DismissButton(VoiceAlarmsTargetEntity, ButtonEntity):
    """Stop the alarm ringing on this satellite."""

    _attr_translation_key = "dismiss"

    _unique_suffix = "_dismiss"

    async def async_press(self) -> None:
        """Dismiss."""
        await self.manager.async_dismiss(self.target.entity_id)


class TestAlarmButton(VoiceAlarmsTargetEntity, ButtonEntity):
    """Ring the alarm sound briefly to test the satellite."""

    _attr_translation_key = "test"
    _attr_entity_registry_enabled_default = True

    _unique_suffix = "_test"

    async def async_press(self) -> None:
        """Ring for a few seconds."""
        await self.manager.async_ring(
            self.target, label="Test", duration=DEFAULT_TEST_DURATION, origin="test"
        )
