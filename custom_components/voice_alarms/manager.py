"""Alarm manager: storage, scheduling and ringing orchestration."""

from __future__ import annotations

import asyncio
import logging
import shutil
from array import array
from dataclasses import fields, replace
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.components.assist_satellite import DOMAIN as ASSIST_SATELLITE_DOMAIN
from homeassistant.components.ffmpeg import get_ffmpeg_manager
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, STATE_UNAVAILABLE
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .audio import Curve, RampSpec
from .const import (
    CONF_ALARM_VOLUME,
    CONF_DEFAULT_DURATION,
    CONF_DEFAULT_SOUND,
    CONF_DEVICE_STOP_PAUSE,
    CONF_MISSED_GRACE,
    CONF_RAMP_CURVE,
    CONF_RAMP_SECONDS,
    CONF_RAMP_START,
    CONF_REMINDER_INTERVAL,
    CONF_REMINDER_REPEATS,
    DEFAULT_DEVICE_STOP_PAUSE,
    DEFAULT_DURATION,
    DEFAULT_MISSED_GRACE,
    DEFAULT_RAMP_CURVE,
    DEFAULT_RAMP_SECONDS,
    DEFAULT_RAMP_START,
    DEFAULT_REMINDER_INTERVAL,
    DEFAULT_REMINDER_REPEATS,
    DISMISSED_ON_PURPOSE,
    DOMAIN,
    KIND_ALARM,
    KIND_REMINDER,
    MAX_ALARM_DURATION,
    MAX_SNOOZE_MINUTES,
    ON_TIME_SECONDS,
    SIGNAL_ALARMS_UPDATED,
    SIGNAL_CONFIG_UPDATED,
    SIGNAL_RINGING_UPDATED,
    SIGNAL_TARGETS_UPDATED,
    STORAGE_KEY,
    STORAGE_VERSION,
    TARGET_ENTITY_SUFFIXES,
)
from .http import StreamRegistry
from .i18n import LocalizedError, default_language, tr
from .models import Alarm, combine_local, is_valid_sound
from .ringer import RingConfig, RingSession
from .targets import Target, get_target, get_targets, match_targets

_LOGGER = logging.getLogger(__name__)

MAX_RECENT_SESSIONS = 10
# A snooze may end this much early rather than almost a minute late.
SNOOZE_ROUND_DOWN = timedelta(seconds=5)


class AlarmError(LocalizedError, ValueError):
    """Raised for invalid alarm operations (user facing, see ``i18n.py`` for the texts)."""


class AlarmManager:
    """Own all alarms and ring sessions."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        registry: StreamRegistry,
        loop: array,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.registry = registry
        self.loop = loop
        self.alarms: dict[str, Alarm] = {}
        self.sessions: dict[str, RingSession] = {}
        self.recent_sessions: list[RingSession] = []
        # Reminders that fired while an alarm rang on their satellite; spoken after it.
        self._queued: dict[str, list[Alarm]] = {}
        # Each alarm ringing or queued now: its last_fired from before it fired, and the
        # occurrence it fired for. A restart that interrupts the ring puts last_fired
        # back, so that the alarm rings after the restart.
        self._fired_from: dict[str, tuple[datetime | None, datetime]] = {}
        self.ffmpeg_binary: str | None = None
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._unsub_registry: CALLBACK_TYPE | None = None
        self._unsub_stopping: CALLBACK_TYPE | None = None
        # Listens to the offline satellites that due alarms wait for.
        self._unsub_waiting: CALLBACK_TYPE | None = None
        # What the shutdown put back, as in _fired_from: a ring dismissed later in the
        # shutdown is over after all.
        self._put_back_at_stop: dict[str, tuple[datetime | None, datetime]] = {}
        self._lock = asyncio.Lock()
        self._started = False

    # ------------------------------------------------------------- options

    def _opt(self, key: str, default: Any) -> Any:
        value = self.entry.options.get(key)
        return default if value is None else value

    @property
    def default_duration(self) -> int:
        """Ring duration in seconds."""
        return int(self._opt(CONF_DEFAULT_DURATION, DEFAULT_DURATION))

    @property
    def ramp(self) -> RampSpec:
        """Volume ramp settings."""
        return RampSpec(
            start=max(0.0, min(1.0, float(self._opt(CONF_RAMP_START, DEFAULT_RAMP_START)) / 100)),
            seconds=float(self._opt(CONF_RAMP_SECONDS, DEFAULT_RAMP_SECONDS)),
            curve=_ramp_curve(self.entry.options.get(CONF_RAMP_CURVE)),
        )

    @callback
    def async_set_ramp(self, *, seconds: float, start: float, curve: Curve) -> None:
        """Store new ramp settings from the panel.

        Written straight into the entry options (``start`` as percent, like
        the options flow stores it) without reloading the entry, so a ringing
        alarm is not interrupted; the next ring picks the new ramp up.
        """
        options = {
            **self.entry.options,
            CONF_RAMP_SECONDS: round(seconds, 3),
            CONF_RAMP_START: round(start * 100, 2),
            CONF_RAMP_CURVE: [round(v, 4) for v in curve],
        }
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        async_dispatcher_send(self.hass, SIGNAL_CONFIG_UPDATED)

    @property
    def alarm_volume(self) -> float | None:
        """Media player volume (0..1) during the alarm, None to leave alone."""
        value = self.entry.options.get(CONF_ALARM_VOLUME)
        if value is None or value == "":
            return None
        return max(0.0, min(1.0, float(value) / 100))

    @property
    def default_sound(self) -> str | None:
        """Configured default sound or None for the built-in one."""
        value = self.entry.options.get(CONF_DEFAULT_SOUND)
        return value.strip() if isinstance(value, str) and value.strip() else None

    @property
    def missed_grace(self) -> timedelta:
        """How long after its time an alarm still fires (e.g. after a restart)."""
        return timedelta(seconds=int(self._opt(CONF_MISSED_GRACE, DEFAULT_MISSED_GRACE)))

    def config_dict(self) -> dict[str, Any]:
        """Effective configuration for the frontend."""
        return {
            "default_duration": self.default_duration,
            "ramp_seconds": self.ramp.seconds,
            "ramp_start": self.ramp.start,
            "ramp_curve": list(self.ramp.curve),
            "alarm_volume": self.alarm_volume,
            "default_sound": self.default_sound,
            "reminder_repeats": int(self._opt(CONF_REMINDER_REPEATS, DEFAULT_REMINDER_REPEATS)),
            "reminder_interval": int(self._opt(CONF_REMINDER_INTERVAL, DEFAULT_REMINDER_INTERVAL)),
            "missed_grace": int(self.missed_grace.total_seconds()),
            "device_stop_pause": int(self._opt(CONF_DEVICE_STOP_PAUSE, DEFAULT_DEVICE_STOP_PAUSE)),
            "ffmpeg": self.ffmpeg_binary is not None,
        }

    def ring_config(
        self,
        alarm: Alarm | None = None,
        *,
        duration: int | None = None,
        sound: str | None = None,
    ) -> RingConfig:
        """Build the ring configuration for a session."""
        if duration is None:
            duration = alarm.duration if alarm and alarm.duration else self.default_duration
        if sound is None:
            sound = alarm.sound if alarm and alarm.sound else self.default_sound
        if sound and not is_valid_sound(sound):
            # Saved before sounds were checked; ffmpeg must not get it as a bare input.
            _LOGGER.warning("Alarm sound %s is not playable, using the default sound", sound)
            sound = self.default_sound
        return RingConfig(
            duration=max(1, int(duration)),
            sound=sound,
            ramp=self.ramp,
            volume=self.alarm_volume,
            reminder_repeats=int(self._opt(CONF_REMINDER_REPEATS, DEFAULT_REMINDER_REPEATS)),
            reminder_interval=int(self._opt(CONF_REMINDER_INTERVAL, DEFAULT_REMINDER_INTERVAL)),
            device_stop_pause=int(self._opt(CONF_DEVICE_STOP_PAUSE, DEFAULT_DEVICE_STOP_PAUSE)),
            ffmpeg_binary=self.ffmpeg_binary,
        )

    # ------------------------------------------------------------ lifecycle

    async def async_load(self) -> None:
        """Load alarms from storage."""
        data = await self._store.async_load()
        if not data:
            return
        for item in data.get("alarms", []):
            try:
                alarm = Alarm.from_dict(item)
            except (KeyError, ValueError, TypeError):
                _LOGGER.warning("Ignoring corrupt alarm in storage: %s", item)
                continue
            self.alarms[alarm.id] = alarm

    async def async_start(self) -> None:
        """Start scheduling."""
        self.ffmpeg_binary = await self.hass.async_add_executor_job(self._find_ffmpeg)
        if self.ffmpeg_binary is None:
            _LOGGER.warning("ffmpeg not found: custom alarm sounds will play without volume ramp")
        self._unsub_registry = self.hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            self._registry_updated,
            event_filter=_satellite_registry_filter,
        )
        self._unsub_stopping = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._hass_stopping
        )
        self._started = True
        await self._process()

    async def async_stop(self) -> None:
        """Stop scheduling and ringing."""
        self._started = False
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        self._cancel_waiting()
        if self._unsub_registry:
            self._unsub_registry()
            self._unsub_registry = None
        if self._unsub_stopping:
            self._unsub_stopping()
            self._unsub_stopping = None
        self._queued.clear()
        self._fired_from.clear()
        sessions = list(self.sessions.values())
        for session in sessions:
            session.dismiss(by="shutdown")
        for session in sessions:
            await session.wait_finished()
        await self._store.async_save(self._data_to_save())

    @callback
    def _hass_stopping(self, _event: Event) -> None:
        """Keep the alarms a restart interrupts, so that they ring after it.

        Config entries are not unloaded on shutdown: a ring that started just before
        plays into satellites that are disconnecting. Its alarm is put back as it was
        before it fired, and the missed alarm catch-up rings it once Home Assistant is
        back, within the missed grace. A dismissed ring is over and stays so.
        """
        self._unsub_stopping = None
        # Nothing more is fired or rung from the queue: the state goes back to
        # not_running before the end, where the is_stopping guard no longer holds.
        self._started = False
        interrupted = [
            alarm
            for session in self.active_sessions()
            if not session.dismissed
            for alarm in session.alarms
        ]
        interrupted += [alarm for queued in self._queued.values() for alarm in queued]
        self._queued.clear()
        self._put_back_at_stop = self._put_back(interrupted, "interrupted by the shutdown")

    @callback
    def _put_back(
        self, alarms: list[Alarm], why: str
    ) -> dict[str, tuple[datetime | None, datetime]]:
        """Put alarms that fired back as they were before, so that they are due again.

        Returns the records of those put back. One-time alarms return to the list they
        left when they fired. An alarm deleted or rescheduled since it fired (an update
        resets last_fired in place) stays as it is.
        """
        put_back: dict[str, tuple[datetime | None, datetime]] = {}
        for alarm in alarms:
            record = self._fired_from.pop(alarm.id, None)
            if record is None:
                continue
            previous, occurrence = record
            current = self.alarms.get(alarm.id)
            if current is None and not alarm.is_recurring:
                current = self.alarms[alarm.id] = alarm
            if current is None or current.last_fired != occurrence:
                continue
            _LOGGER.info("Keeping %s '%s' %s", alarm.kind, alarm.label, why)
            current.last_fired = previous
            put_back[alarm.id] = record
        if put_back:
            self._save()
            self._notify_alarms()
        return put_back

    @callback
    def _dismissed_while_stopping(self, session: RingSession) -> None:
        """A ring the shutdown put back was dismissed after all: it stays rung."""
        changed = False
        for alarm in session.alarms:
            record = self._put_back_at_stop.pop(alarm.id, None)
            current = self.alarms.get(alarm.id)
            if record is None or current is None or current.last_fired != record[0]:
                continue
            current.last_fired = record[1]
            if not current.is_recurring:
                self.alarms.pop(alarm.id)
            changed = True
        if changed:
            self._save()
            self._notify_alarms()

    def _find_ffmpeg(self) -> str | None:
        try:
            binary = get_ffmpeg_manager(self.hass).binary
        except ValueError:
            binary = "ffmpeg"
        return shutil.which(binary)

    @callback
    def _registry_updated(self, event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        data = event.data
        if data["action"] == "update" and (old := data.get("old_entity_id")):
            self._target_renamed(old, data["entity_id"])
        elif data["action"] == "remove":
            self._target_removed(data["entity_id"])
        async_dispatcher_send(self.hass, SIGNAL_TARGETS_UPDATED)

    @callback
    def _target_renamed(self, old: str, new: str) -> None:
        """Follow a satellite whose entity id changed: alarms, entities and device."""
        if not old.startswith(f"{ASSIST_SATELLITE_DOMAIN}."):
            return
        moved = False
        for alarm in self.alarms.values():
            if alarm.target == old:
                alarm.target = new
                moved = True
        ent_reg = er.async_get(self.hass)
        for suffix, platform in TARGET_ENTITY_SUFFIXES.items():
            entity_id = ent_reg.async_get_entity_id(platform, DOMAIN, f"{old}{suffix}")
            if entity_id is None:
                continue
            if ent_reg.async_get_entity_id(platform, DOMAIN, f"{new}{suffix}") is not None:
                ent_reg.async_remove(entity_id)
            else:
                ent_reg.async_update_entity(entity_id, new_unique_id=f"{new}{suffix}")
        dev_reg = dr.async_get(self.hass)
        if device := self._device(dev_reg, old):
            if self._device(dev_reg, new) is None:
                dev_reg.async_update_device(device.id, new_identifiers={(DOMAIN, new)})
        if moved:
            _LOGGER.info("Satellite %s is now %s; moved its alarms along", old, new)
            self._save()
        # The entities hold the old target; rebuilding them is far simpler than
        # rewiring each one (it also ends a session ringing on the satellite).
        self.hass.config_entries.async_schedule_reload(self.entry.entry_id)

    @callback
    def _device(self, dev_reg: dr.DeviceRegistry, entity_id: str) -> dr.DeviceEntry | None:
        """Our device grouping the entities of satellite ``entity_id``."""
        identifier = (DOMAIN, entity_id)
        if hasattr(dev_reg, "async_get_device_by_identifier"):  # 2026.10+
            return dev_reg.async_get_device_by_identifier(identifier, self.entry.entry_id)
        return dev_reg.async_get_device(identifiers={identifier})

    @callback
    def _target_removed(self, entity_id: str) -> None:
        """Drop the per-satellite entities of a deleted satellite.

        Its alarms stay (they can be moved to another satellite), and so does
        the device while they still need it for their switches.
        """
        if self._started:
            # An alarm waiting for it is reported now, not missed later.
            self.hass.async_create_task(self._process())
        ent_reg = er.async_get(self.hass)
        for suffix, platform in TARGET_ENTITY_SUFFIXES.items():
            if registered := ent_reg.async_get_entity_id(platform, DOMAIN, f"{entity_id}{suffix}"):
                ent_reg.async_remove(registered)
        if any(alarm.target == entity_id for alarm in self.alarms.values()):
            return
        dev_reg = dr.async_get(self.hass)
        if device := self._device(dev_reg, entity_id):
            dev_reg.async_remove_device(device.id)

    # -------------------------------------------------------------- storage

    def _data_to_save(self) -> dict[str, Any]:
        return {"alarms": [alarm.to_dict() for alarm in self.alarms.values()]}

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(self._data_to_save, 1)

    @callback
    def _notify_alarms(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_ALARMS_UPDATED)

    @callback
    def _notify_ringing(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_RINGING_UPDATED)

    # -------------------------------------------------------------- targets

    def targets(self) -> list[Target]:
        """All satellites."""
        return get_targets(self.hass)

    def target(self, entity_id: str) -> Target | None:
        """Look up a satellite."""
        return get_target(self.hass, entity_id)

    def match_target(self, query: str) -> list[Target]:
        """Resolve a spoken satellite name."""
        return match_targets(self.targets(), query)

    # ----------------------------------------------------------------- CRUD

    def get_alarm(self, alarm_id: str) -> Alarm | None:
        """Return an alarm by id."""
        return self.alarms.get(alarm_id)

    def sorted_alarms(self) -> list[Alarm]:
        """Alarms ordered by next occurrence (disabled / expired last)."""
        now = dt_util.utcnow()
        far = now + timedelta(days=3650)

        def key(alarm: Alarm) -> tuple[datetime, str]:
            nxt = alarm.next_pending(now)
            return (nxt or far, alarm.label.lower())

        return sorted(self.alarms.values(), key=key)

    def alarms_for_target(self, entity_id: str) -> list[Alarm]:
        """Alarms configured for one satellite."""
        return [a for a in self.sorted_alarms() if a.target == entity_id]

    def next_for_target(self, entity_id: str) -> tuple[Alarm, datetime] | None:
        """The next alarm on a satellite."""
        now = dt_util.utcnow()
        best: tuple[Alarm, datetime] | None = None
        for alarm in self.alarms.values():
            if alarm.target != entity_id:
                continue
            nxt = alarm.next_pending(now)
            if nxt is not None and (best is None or nxt < best[1]):
                best = (alarm, nxt)
        return best

    def _validate(
        self,
        alarm: Alarm,
        now: datetime,
        *,
        check_target: bool = True,
        check_sound: bool = True,
    ) -> None:
        """Check an alarm and fill in the date of a one-time alarm without one.

        ``check_target`` and ``check_sound`` are off when an update keeps
        them, so that an alarm whose satellite was deleted, or that was saved
        before sounds were checked, can still be disabled or renamed.
        """
        if check_target and self.target(alarm.target) is None:
            raise AlarmError("err_unknown_target", target=alarm.target)
        if check_sound and alarm.sound is not None and not is_valid_sound(alarm.sound):
            raise AlarmError("err_invalid_sound", sound=alarm.sound)
        if alarm.duration is not None and not 1 <= alarm.duration <= MAX_ALARM_DURATION:
            raise AlarmError("err_duration")
        if not alarm.is_recurring:
            if alarm.date is None:
                alarm.date = _next_date(alarm.time, now)
            elif alarm.enabled and combine_local(alarm.date, alarm.time) <= now:
                raise AlarmError("err_time_past")

    async def async_add_alarm(self, alarm: Alarm) -> Alarm:
        """Add a validated alarm."""
        now = dt_util.utcnow()
        alarm.created = now
        alarm.last_fired = None
        self._validate(alarm, now)
        self.alarms[alarm.id] = alarm
        self._save()
        self._notify_alarms()
        await self._process()
        return alarm

    async def async_update_alarm(self, alarm_id: str, **changes: Any) -> Alarm:
        """Update fields of an alarm.

        Recognised keys: target, time, date, weekdays, name, message, duration,
        sound, enabled, kind. Changing the schedule resets the fired state.
        Nothing changes when the result is invalid.
        """
        return (await self.async_update_alarms([(alarm_id, changes)]))[0]

    async def async_update_alarms(self, updates: list[tuple[str, dict[str, Any]]]) -> list[Alarm]:
        """Apply several updates all or nothing: if one is invalid, none is applied."""
        now = dt_util.utcnow()
        prepared: list[tuple[Alarm, Alarm]] = []
        for alarm_id, changes in updates:
            alarm = self.alarms.get(alarm_id)
            if alarm is None:
                raise AlarmError("err_no_such_alarm", alarm_id=alarm_id)
            prepared.append((alarm, self._prepare_update(alarm, changes, now)))
        for alarm, updated in prepared:
            # Copy back rather than swap objects: ring sessions hold the alarm.
            for item in fields(Alarm):
                setattr(alarm, item.name, getattr(updated, item.name))
        self._save()
        self._notify_alarms()
        await self._process()
        return [alarm for alarm, _ in prepared]

    def _prepare_update(self, alarm: Alarm, changes: dict[str, Any], now: datetime) -> Alarm:
        """Return a validated copy of ``alarm`` with ``changes`` applied."""
        updated = replace(alarm, weekdays=list(alarm.weekdays))
        schedule_changed = False
        for key, value in changes.items():
            if key == "time":
                if value != updated.time:
                    updated.time = value
                    schedule_changed = True
            elif key == "date":
                if value != updated.date:
                    updated.date = value
                    schedule_changed = True
            elif key == "weekdays":
                new = sorted(set(value or []))
                if new != updated.weekdays:
                    updated.weekdays = new
                    schedule_changed = True
                    if new:
                        updated.date = None
            elif key == "target":
                updated.target = value
            elif key == "name":
                updated.name = value or None
            elif key == "message":
                updated.message = value or None
                if updated.message and updated.kind == KIND_ALARM:
                    updated.kind = KIND_REMINDER
            elif key == "kind":
                updated.kind = value
            elif key == "duration":
                updated.duration = int(value) if value else None
            elif key == "sound":
                updated.sound = value or None
            elif key == "enabled":
                updated.enabled = bool(value)
            else:
                raise AlarmError("err_unknown_field", field=key)
        date_changed = updated.date != alarm.date
        if schedule_changed:
            updated.last_fired = None
            updated.skipped_occurrence = None
            updated.created = now
            # A one-time alarm whose date was not given moves to the next time
            # its clock time comes round. (The panel always sends the date.)
            if not updated.is_recurring and "date" not in changes:
                updated.date = None
        elif (
            updated.enabled
            and not alarm.enabled
            and not updated.is_recurring
            and not date_changed
            and updated.date is not None
            and combine_local(updated.date, updated.time) <= now
        ):
            # Re-enabling a one-time alarm whose day has passed: next time round.
            updated.date = None
            updated.last_fired = None
            updated.created = now
        self._validate(
            updated,
            now,
            check_target=updated.target != alarm.target,
            check_sound=updated.sound != alarm.sound,
        )
        return updated

    async def async_delete_alarm(self, alarm_id: str) -> Alarm:
        """Delete an alarm."""
        alarm = self.alarms.pop(alarm_id, None)
        if alarm is None:
            raise AlarmError("err_no_such_alarm", alarm_id=alarm_id)
        self._save()
        self._notify_alarms()
        await self._process()
        return alarm

    async def async_skip_next(
        self, alarm_id: str, undo: bool = False
    ) -> tuple[Alarm, datetime | None]:
        """Skip (or un-skip) the next occurrence of a repeating alarm.

        Returns the alarm and the occurrence that is (no longer) skipped.
        """
        alarm = self.alarms.get(alarm_id)
        if alarm is None:
            raise AlarmError("err_no_such_alarm", alarm_id=alarm_id)
        if not alarm.is_recurring:
            raise AlarmError("err_skip_not_recurring")
        now = dt_util.utcnow()
        after = alarm.upcoming_after(now)
        if undo:
            skipped = alarm.skipped_occurrence
            alarm.skipped_occurrence = None
        else:
            skipped = alarm.next_scheduled(after)
            alarm.skipped_occurrence = skipped
        self._save()
        self._notify_alarms()
        await self._process()
        return alarm, skipped

    # ------------------------------------------------------------- ringing

    def active_sessions(self) -> list[RingSession]:
        """Sessions that are ringing or paused."""
        return [s for s in self.sessions.values() if s.active]

    def session_for_target(self, entity_id: str) -> RingSession | None:
        """Active session on a satellite."""
        session = self.sessions.get(entity_id)
        return session if session and session.active else None

    def recently_finished(self, within: timedelta) -> list[RingSession]:
        """Sessions that ended recently (for 'it already stopped' answers)."""
        now = dt_util.utcnow()
        return [
            s
            for s in self.recent_sessions
            if s.finished_at is not None and now - s.finished_at <= within
        ]

    async def async_ring(
        self,
        target: Target,
        *,
        alarm: Alarm | None = None,
        kind: str = KIND_ALARM,
        message: str | None = None,
        label: str | None = None,
        duration: int | None = None,
        sound: str | None = None,
        origin: str = "alarm",
    ) -> RingSession:
        """Start ringing on a satellite, or join what is already active there.

        Alarms join a ringing alarm, reminders a speaking reminder. A reminder
        due while an alarm rings is spoken once the alarm is over; an alarm due
        while a reminder speaks takes over and the reminder follows it. Tests
        never interrupt anything and anything interrupts a test.
        """
        entity_id = target.entity_id
        existing = self.session_for_target(entity_id)
        if existing is not None and existing.dismissed:
            # Dismissed and only finishing: nothing to join or to repeat later.
            predecessor: RingSession | None = existing
            existing = None
        else:
            predecessor = existing
        if existing is not None:
            if origin == "test":
                return existing
            if existing.origin != "test":
                if existing.kind == kind:
                    if alarm is not None:
                        existing.attach(alarm)
                        self._notify_ringing()
                    return existing
                if existing.kind == KIND_ALARM:
                    if alarm is not None:
                        self._queued.setdefault(entity_id, []).append(alarm)
                    return existing
                # An alarm interrupts a reminder, which is repeated afterwards.
                self._queued.setdefault(entity_id, []).extend(existing.alarms)
            existing.dismiss(by="superseded")
        # Registered at once, so that the ending predecessor finds a successor
        # (and leaves the queue to it); the new session itself waits for the
        # predecessor to go quiet before it plays.
        session = RingSession(
            self.hass,
            self,
            self.registry,
            target,
            self.ring_config(alarm, duration=duration, sound=sound),
            alarm=alarm,
            kind=kind,
            message=message,
            label=label or (alarm.label if alarm else tr(default_language(), "label_alarm")),
            origin=origin,
            loop=self.loop,
            predecessor=predecessor,
        )
        self.sessions[target.entity_id] = session
        session.start()
        self._notify_ringing()
        return session

    async def async_dismiss(
        self, entity_id: str | None = None, by: str = "user"
    ) -> list[RingSession]:
        """Dismiss the session on one satellite, or all of them."""
        if entity_id:
            session = self.session_for_target(entity_id)
            sessions = [session] if session else []
        else:
            sessions = self.active_sessions()
        for session in sessions:
            session.dismiss(by=by)
        return sessions

    async def async_snooze(self, session: RingSession, minutes: int) -> Alarm:
        """Dismiss a session and ring again in ``minutes`` minutes."""
        if not 1 <= minutes <= MAX_SNOOZE_MINUTES:
            raise AlarmError("err_snooze_minutes")
        # Alarms ring on the minute. Round up, so that a snooze is never
        # noticeably short, unless that would add almost a whole minute.
        exact = dt_util.utcnow() + timedelta(minutes=minutes)
        when = exact.replace(second=0, microsecond=0)
        if exact - when > SNOOZE_ROUND_DOWN:
            when += timedelta(minutes=1)
        when = dt_util.as_local(when)
        base = session.alarms[0] if session.alarms else None
        alarm = Alarm(
            target=session.target.entity_id,
            time=when.time(),
            date=when.date(),
            name=tr(default_language(), "snoozed_name", label=session.label),
            kind=session.kind,
            message=session.message,
            duration=base.duration if base else None,
            # A sound saved before sounds were checked rings as the default anyway.
            sound=base.sound if base and base.sound and is_valid_sound(base.sound) else None,
        )
        # Check before stopping the ring, so a failing snooze leaves it ringing.
        self._validate(alarm, dt_util.utcnow())
        session.dismiss(by="snooze")
        return await self.async_add_alarm(alarm)

    @callback
    def session_changed(self, session: RingSession) -> None:
        """A session changed state (called by the session)."""
        self._notify_ringing()

    @callback
    def session_finished(self, session: RingSession) -> None:
        """A session ended (called by the session)."""
        if self.sessions.get(session.target.entity_id) is session:
            del self.sessions[session.target.entity_id]
        self.recent_sessions.append(session)
        del self.recent_sessions[:-MAX_RECENT_SESSIONS]
        self._notify_ringing()
        entity_id = session.target.entity_id
        if not self._started and session.dismissed_by in DISMISSED_ON_PURPOSE:
            self._dismissed_while_stopping(session)
        if (
            self._started
            and session.gave_up
            and not session.dismissed
            and self._satellite_offline(entity_id)
        ):
            # The satellite went away mid-ring: wait for it, as for a due alarm.
            self._put_back(session.alarms, f"until {entity_id} is back")
            self.hass.async_create_task(self._process())
        # Alarms still queued, or ringing in another session, still have to ring.
        in_play = {alarm.id for queued in self._queued.values() for alarm in queued}
        in_play.update(
            alarm.id
            for other in self.active_sessions()
            if other is not session
            for alarm in other.alarms
        )
        for alarm in session.alarms:
            if alarm.id not in in_play:
                self._fired_from.pop(alarm.id, None)
        # A session that was followed by another one leaves the queue to it.
        if self._started and self.session_for_target(entity_id) is None:
            if self._queued.get(entity_id):
                self.hass.async_create_task(self._ring_queued(entity_id))

    async def _ring_queued(self, entity_id: str) -> None:
        """Ring what had to wait for the previous session on this satellite.

        The alarms stay queued until now, so that a shutdown in between still finds them.
        """
        alarms = self._queued.pop(entity_id, None)
        if not alarms:
            return
        target = self.target(entity_id)
        if target is None:
            _LOGGER.error("Cannot ring queued alarms: satellite %s no longer exists", entity_id)
            for alarm in alarms:
                self._fired_from.pop(alarm.id, None)
            return
        if self._satellite_offline(entity_id):
            self._put_back(alarms, f"until {entity_id} is back")
            await self._process()
            return
        for alarm in alarms:
            await self.async_ring(
                target, alarm=alarm, kind=alarm.kind, message=alarm.message, label=alarm.label
            )

    # ----------------------------------------------------------- scheduling

    @callback
    def _cancel_timer(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

    @callback
    def _cancel_waiting(self) -> None:
        if self._unsub_waiting:
            self._unsub_waiting()
            self._unsub_waiting = None

    def _satellite_offline(self, entity_id: str) -> bool:
        """True while an existing satellite cannot play, as while it reconnects at startup.

        Its media player, when available, still rings: the session falls back to it.
        """
        target = self.target(entity_id)
        if target is None:
            return False  # gone for good: _fire reports it
        return all(
            (state := self.hass.states.get(watched)) is None or state.state == STATE_UNAVAILABLE
            for watched in self._watched(target)
        )

    @staticmethod
    def _watched(target: Target) -> list[str]:
        """Entities whose coming back lets an alarm on ``target`` ring."""
        return [target.entity_id, *([target.media_player] if target.media_player else [])]

    @callback
    def _satellite_changed(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        # Back, or removed (then the alarm is reported as having no satellite).
        if new_state is None or new_state.state != STATE_UNAVAILABLE:
            self.hass.async_create_task(self._process())

    async def _timer_fired(self, _now: datetime) -> None:
        self._unsub_timer = None
        await self._process()

    async def _process(self) -> None:
        """Fire due alarms and schedule the next wake-up."""
        # Config entries are not unloaded on shutdown, so the timer still runs while Home
        # Assistant stops. Firing then would ring nothing and drop a one-time alarm; left
        # alone, it is caught up within the missed grace when Home Assistant is back.
        if not self._started or self.hass.is_stopping:
            return
        async with self._lock:
            self._cancel_timer()
            self._cancel_waiting()
            now = dt_util.utcnow()
            grace = self.missed_grace
            # Checked a moment after its time, an alarm is on time even with no grace.
            missed_before = now - grace - timedelta(seconds=ON_TIME_SECONDS)
            due: list[tuple[Alarm, datetime]] = []
            expired: list[Alarm] = []
            offline: set[str] = set()
            waiting_changed = False
            next_time: datetime | None = None
            changed = False

            for alarm in list(self.alarms.values()):
                if (
                    alarm.skipped_occurrence is not None
                    and alarm.skipped_occurrence < missed_before
                ):
                    alarm.skipped_occurrence = None
                    changed = True
                was_waiting, alarm.waiting = alarm.waiting, None
                if not alarm.enabled:
                    waiting_changed |= was_waiting is not None
                    continue
                occurrence = alarm.next_occurrence(alarm.pending_after())
                while occurrence is not None and occurrence < missed_before:
                    _LOGGER.warning(
                        "Missed %s '%s' scheduled %s", alarm.kind, alarm.label, occurrence
                    )
                    alarm.last_fired = occurrence
                    changed = True
                    occurrence = alarm.next_occurrence(occurrence)
                if occurrence is None:
                    waiting_changed |= was_waiting is not None
                    if not alarm.is_recurring:
                        expired.append(alarm)
                    continue
                if occurrence <= now and self._satellite_offline(alarm.target):
                    # Wait for the satellite, until the missed grace runs out.
                    if was_waiting != occurrence:
                        _LOGGER.info(
                            "Waiting for %s to come back to ring %s '%s'",
                            alarm.target,
                            alarm.kind,
                            alarm.label,
                        )
                        waiting_changed = True
                    alarm.waiting = occurrence
                    target = self.target(alarm.target)
                    offline.update(self._watched(target) if target else [])
                    deadline = occurrence + grace + timedelta(seconds=ON_TIME_SECONDS)
                    if next_time is None or deadline < next_time:
                        next_time = deadline
                else:
                    waiting_changed |= was_waiting is not None
                    if occurrence <= now:
                        due.append((alarm, occurrence))
                    elif next_time is None or occurrence < next_time:
                        next_time = occurrence
            if offline:
                self._unsub_waiting = async_track_state_change_event(
                    self.hass, sorted(offline), self._satellite_changed
                )

            for alarm in expired:
                _LOGGER.info("Removing expired one-time %s '%s'", alarm.kind, alarm.label)
                self.alarms.pop(alarm.id, None)
                changed = True

            for alarm, occurrence in due:
                await self._fire(alarm, occurrence)
                changed = True

            if changed:
                self._save()
            if changed or waiting_changed:
                self._notify_alarms()

            if due:
                # Firing may have removed one-time alarms; recompute the wake-up.
                self.hass.async_create_task(self._process())
                return

            if next_time is not None:
                self._unsub_timer = async_track_point_in_utc_time(
                    self.hass, self._timer_fired, next_time + timedelta(milliseconds=50)
                )
                _LOGGER.debug("Next alarm check at %s", next_time)

    async def _fire(self, alarm: Alarm, occurrence: datetime) -> None:
        previous = alarm.last_fired
        alarm.last_fired = occurrence
        if alarm.skipped_occurrence is not None and alarm.skipped_occurrence <= occurrence:
            alarm.skipped_occurrence = None
        target = self.target(alarm.target)
        if target is None:
            _LOGGER.error(
                "Cannot ring %s '%s': satellite %s is missing or disabled",
                alarm.kind,
                alarm.label,
                alarm.target,
            )
        else:
            _LOGGER.info("Ringing %s '%s' on %s", alarm.kind, alarm.label, target.display)
            self._fired_from[alarm.id] = (previous, occurrence)
            await self.async_ring(
                target,
                alarm=alarm,
                kind=alarm.kind,
                message=alarm.message,
                label=alarm.label,
            )
        if not alarm.is_recurring:
            self.alarms.pop(alarm.id, None)

    # --------------------------------------------------------------- helpers

    def build_alarm(
        self,
        *,
        target: str,
        at: time,
        on_date: date | None = None,
        weekdays: list[int] | None = None,
        name: str | None = None,
        message: str | None = None,
        kind: str | None = None,
        duration: int | None = None,
        sound: str | None = None,
        enabled: bool = True,
    ) -> Alarm:
        """Create an Alarm object (not yet added)."""
        if kind is None:
            kind = KIND_REMINDER if message else KIND_ALARM
        return Alarm(
            target=target,
            time=at,
            date=on_date if not weekdays else None,
            weekdays=list(weekdays or []),
            name=name,
            message=message,
            kind=kind,
            duration=duration,
            sound=sound,
            enabled=enabled,
        )

    def snapshot(self) -> dict[str, Any]:
        """Full state for the frontend."""
        now = dt_util.utcnow()
        return {
            "alarms": [alarm.public_dict(now) for alarm in self.sorted_alarms()],
            "targets": [target.to_dict() for target in self.targets()],
            "ringing": [session.to_dict() for session in self.active_sessions()],
            "config": self.config_dict(),
            "now": now.isoformat(),
        }


def _next_date(at: time, now: datetime) -> date:
    """Local date of the next time the clock shows ``at`` after ``now``."""
    local_now = dt_util.as_local(now)
    candidate = combine_local(local_now.date(), at)
    if candidate <= now:
        candidate = combine_local(local_now.date() + timedelta(days=1), at)
    return candidate.astimezone(dt_util.get_default_time_zone()).date()


def _ramp_curve(value: Any) -> Curve:
    """Parse the stored ramp curve, falling back to the default when malformed."""
    try:
        x1, y1, x2, y2 = (max(0.0, min(1.0, float(v))) for v in value)
    except (TypeError, ValueError):
        return DEFAULT_RAMP_CURVE
    return (x1, y1, x2, y2)


@callback
def _satellite_registry_filter(event_data: er.EventEntityRegistryUpdatedData) -> bool:
    entity_id = event_data.get("entity_id", "")
    old_entity_id = event_data.get("old_entity_id", "") or ""
    return entity_id.startswith(f"{ASSIST_SATELLITE_DOMAIN}.") or old_entity_id.startswith(
        f"{ASSIST_SATELLITE_DOMAIN}."
    )
