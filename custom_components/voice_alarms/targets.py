"""Voice satellite targets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from homeassistant.components.assist_satellite import DOMAIN as ASSIST_SATELLITE_DOMAIN
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)

_STRIP_WORDS = re.compile(
    r"\b(assist|satellite|voice|assistant|the|on|in|at|speaker|device)\b", re.IGNORECASE
)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


@dataclass(slots=True)
class Target:
    """A voice satellite that alarms can ring on."""

    entity_id: str
    name: str
    device_id: str | None = None
    area_name: str | None = None
    media_player: str | None = None
    aliases: set[str] = field(default_factory=set)

    @property
    def display(self) -> str:
        """Name plus area for speech."""
        if self.area_name and _norm(self.area_name) not in _norm(self.name):
            return f"{self.name} ({self.area_name})"
        return self.name

    def to_dict(self) -> dict[str, str | None]:
        """Serialise for the frontend."""
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "display": self.display,
            "area": self.area_name,
            "media_player": self.media_player,
            "device_id": self.device_id,
        }


@callback
def get_targets(hass: HomeAssistant) -> list[Target]:
    """Return all assist satellites known to Home Assistant."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)
    targets: list[Target] = []
    for entry in ent_reg.entities.values():
        if entry.domain != ASSIST_SATELLITE_DOMAIN or entry.disabled_by:
            continue
        targets.append(_build_target(hass, entry, ent_reg, dev_reg, area_reg))
    targets.sort(key=lambda t: t.name.lower())
    return targets


@callback
def get_target(hass: HomeAssistant, entity_id: str) -> Target | None:
    """Return a single target by entity id."""
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(entity_id)
    if entry is None or entry.domain != ASSIST_SATELLITE_DOMAIN:
        return None
    return _build_target(hass, entry, ent_reg, dr.async_get(hass), ar.async_get(hass))


@callback
def get_target_for_device(hass: HomeAssistant, device_id: str | None) -> Target | None:
    """Return the satellite that belongs to ``device_id`` (the speaking device)."""
    if not device_id:
        return None
    ent_reg = er.async_get(hass)
    for entry in er.async_entries_for_device(ent_reg, device_id, include_disabled_entities=False):
        if entry.domain == ASSIST_SATELLITE_DOMAIN:
            return _build_target(hass, entry, ent_reg, dr.async_get(hass), ar.async_get(hass))
    return None


def _build_target(
    hass: HomeAssistant,
    entry: er.RegistryEntry,
    ent_reg: er.EntityRegistry,
    dev_reg: dr.DeviceRegistry,
    area_reg: ar.AreaRegistry,
) -> Target:
    device = dev_reg.async_get(entry.device_id) if entry.device_id else None
    state = hass.states.get(entry.entity_id)
    friendly = state.attributes.get("friendly_name") if state else None

    name: str | None = None
    if device:
        name = device.name_by_user or device.name
    if not name:
        name = entry.name or entry.original_name or friendly
    if not name:
        name = entry.entity_id.split(".", 1)[1].replace("_", " ").title()

    area_id = entry.area_id or (device.area_id if device else None)
    area = area_reg.async_get_area(area_id) if area_id else None
    area_name = area.name if area else None

    media_player: str | None = None
    if entry.device_id:
        for other in er.async_entries_for_device(ent_reg, entry.device_id):
            if other.domain == MEDIA_PLAYER_DOMAIN:
                media_player = other.entity_id
                break

    aliases: set[str] = set()
    for candidate in (
        name,
        friendly,
        entry.name,
        entry.original_name,
        area_name,
        entry.entity_id,
        entry.entity_id.split(".", 1)[1],
        *(entry.aliases or ()),
    ):
        if candidate:
            normalised = _norm(str(candidate))
            if normalised:
                aliases.add(normalised)
                stripped = _norm(_STRIP_WORDS.sub(" ", normalised))
                if stripped:
                    aliases.add(stripped)
    if area:
        aliases.update(_norm(a) for a in area.aliases if a)

    return Target(
        entity_id=entry.entity_id,
        name=name,
        device_id=entry.device_id,
        area_name=area_name,
        media_player=media_player,
        aliases=aliases,
    )


@callback
def match_targets(targets: list[Target], query: str) -> list[Target]:
    """Return the best matching targets for a spoken/typed name.

    Exact alias matches win over substring matches which win over word
    overlap. All targets sharing the best score are returned so that the
    caller can report ambiguity.
    """
    q = _norm(query)
    if not q:
        return []
    if "." in query and any(t.entity_id == query.strip() for t in targets):
        return [t for t in targets if t.entity_id == query.strip()]
    q_stripped = _norm(_STRIP_WORDS.sub(" ", q)) or q
    q_words = set(q_stripped.split())

    scored: list[tuple[int, Target]] = []
    for target in targets:
        score = 0
        for alias in target.aliases:
            if alias in (q, q_stripped):
                score = max(score, 100)
            elif q_stripped and (q_stripped in alias or alias in q_stripped):
                score = max(score, 60)
            else:
                overlap = len(q_words & set(alias.split()))
                if overlap:
                    score = max(score, 20 + overlap * 10)
        if score:
            scored.append((score, target))
    if not scored:
        return []
    best = max(score for score, _ in scored)
    return [target for score, target in scored if score == best]
