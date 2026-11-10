"""Base entities for Voice Alarms."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_ALARMS_UPDATED, SIGNAL_RINGING_UPDATED, SIGNAL_TARGETS_UPDATED
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
    # Unique id suffix after the satellite entity id; see TARGET_ENTITY_SUFFIXES.
    _unique_suffix: str

    def __init__(self, manager: AlarmManager, target: Target) -> None:
        self.manager = manager
        self.target = target
        self._attr_device_info = target_device_info(target)
        self._attr_unique_id = f"{target.entity_id}{self._unique_suffix}"
        self._known: set[str] | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        # Also when Home Assistant re-adds the entity after an entity id change.
        if self._known is not None and self.unique_id is not None:
            self._known.add(self.unique_id)
        for signal in (SIGNAL_ALARMS_UPDATED, SIGNAL_RINGING_UPDATED):
            self.async_on_remove(async_dispatcher_connect(self.hass, signal, self._updated))

    async def async_will_remove_from_hass(self) -> None:
        """Forget the entity, so that it is created again if its satellite returns."""
        if self._known is not None and self.unique_id is not None:
            self._known.discard(self.unique_id)

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()


type TargetEntityFactory = Callable[[AlarmManager, Target], VoiceAlarmsTargetEntity]


@callback
def async_track_targets(
    hass: HomeAssistant,
    entry: ConfigEntry,
    manager: AlarmManager,
    async_add_entities: AddEntitiesCallback,
    factories: tuple[TargetEntityFactory, ...],
) -> None:
    """Add the entities ``factories`` make for every satellite, now and when one appears.

    Entities are known by unique id and forgotten when removed (e.g. with
    their deleted satellite), so a satellite that comes back gets them again.
    """
    known: set[str] = set()

    @callback
    def sync_targets() -> None:
        new: list[VoiceAlarmsTargetEntity] = []
        for target in manager.targets():
            for factory in factories:
                entity = factory(manager, target)
                if entity.unique_id is None or entity.unique_id in known:
                    continue
                known.add(entity.unique_id)
                entity._known = known  # noqa: SLF001
                new.append(entity)
        if new:
            async_add_entities(new)

    sync_targets()
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_TARGETS_UPDATED, sync_targets))
