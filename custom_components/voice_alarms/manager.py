"""Alarm manager: storage, scheduling and ringing orchestration."""

from __future__ import annotations

import asyncio
import logging
import shutil
from array import array
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.components.assist_satellite import DOMAIN as ASSIST_SATELLITE_DOMAIN
from homeassistant.components.ffmpeg import get_ffmpeg_manager
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_utc_time
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
    KIND_ALARM,
    KIND_REMINDER,
    SIGNAL_ALARMS_UPDATED,
    SIGNAL_CONFIG_UPDATED,
    SIGNAL_RINGING_UPDATED,
    SIGNAL_TARGETS_UPDATED,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .http import StreamRegistry
from .models import Alarm, combine_local
from .ringer import RingConfig, RingSession
from .targets import Target, get_target, get_targets, match_targets

_LOGGER = logging.getLogger(__name__)

MAX_RECENT_SESSIONS = 10


class AlarmError(ValueError):
    """Raised for invalid alarm operations (user facing message)."""


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
        self.ffmpeg_binary: str | None = None
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._unsub_registry: CALLBACK_TYPE | None = None
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
        self._started = True
        await self._process()

    async def async_stop(self) -> None:
        """Stop scheduling and ringing."""
        self._started = False
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        if self._unsub_registry:
            self._unsub_registry()
            self._unsub_registry = None
        sessions = list(self.sessions.values())
        for session in sessions:
            session.dismiss(by="shutdown")
        for session in sessions:
            await session.wait_finished()
        await self._store.async_save(self._data_to_save())

    def _find_ffmpeg(self) -> str | None:
        try:
            binary = get_ffmpeg_manager(self.hass).binary
        except ValueError:
            binary = "ffmpeg"
        return shutil.which(binary)

    @callback
    def _registry_updated(self, event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        async_dispatcher_send(self.hass, SIGNAL_TARGETS_UPDATED)

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

    def _validate(self, alarm: Alarm, now: datetime) -> None:
        if self.target(alarm.target) is None:
            raise AlarmError(f"Unknown voice satellite '{alarm.target}'")
        if not alarm.is_recurring:
            if alarm.date is None:
                local_now = dt_util.as_local(now)
                candidate = combine_local(local_now.date(), alarm.time)
                if candidate <= now:
                    candidate = combine_local(local_now.date() + timedelta(days=1), alarm.time)
                alarm.date = candidate.astimezone(dt_util.get_default_time_zone()).date()
            elif combine_local(alarm.date, alarm.time) <= now:
                raise AlarmError("That time is already in the past")
        if alarm.duration is not None and alarm.duration < 1:
            raise AlarmError("Duration must be at least 1 second")

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
        """
        alarm = self.alarms.get(alarm_id)
        if alarm is None:
            raise AlarmError(f"No alarm with id {alarm_id}")
        now = dt_util.utcnow()
        schedule_changed = False
        for key, value in changes.items():
            if key == "time":
                if value != alarm.time:
                    alarm.time = value
                    schedule_changed = True
            elif key == "date":
                if value != alarm.date:
                    alarm.date = value
                    schedule_changed = True
            elif key == "weekdays":
                new = sorted(set(value or []))
                if new != alarm.weekdays:
                    alarm.weekdays = new
                    schedule_changed = True
                    if new:
                        alarm.date = None
            elif key == "target":
                alarm.target = value
            elif key == "name":
                alarm.name = value or None
            elif key == "message":
                alarm.message = value or None
                if alarm.message and alarm.kind == KIND_ALARM:
                    alarm.kind = KIND_REMINDER
            elif key == "kind":
                alarm.kind = value
            elif key == "duration":
                alarm.duration = int(value) if value else None
            elif key == "sound":
                alarm.sound = value or None
            elif key == "enabled":
                alarm.enabled = bool(value)
            else:
                raise AlarmError(f"Unknown field {key}")
        if schedule_changed:
            alarm.last_fired = None
            alarm.skipped_occurrence = None
            alarm.created = now
            if not alarm.is_recurring and "date" not in changes:
                alarm.date = None
        self._validate(alarm, now)
        self._save()
        self._notify_alarms()
        await self._process()
        return alarm

    async def async_delete_alarm(self, alarm_id: str) -> Alarm:
        """Delete an alarm."""
        alarm = self.alarms.pop(alarm_id, None)
        if alarm is None:
            raise AlarmError(f"No alarm with id {alarm_id}")
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
            raise AlarmError(f"No alarm with id {alarm_id}")
        if not alarm.is_recurring:
            raise AlarmError("Only repeating alarms can skip an occurrence; delete it instead")
        now = dt_util.utcnow()
        after = max(now, alarm.pending_after())
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
        """Start ringing on a satellite (or attach to the active session)."""
        existing = self.session_for_target(target.entity_id)
        if existing is not None:
            if alarm is not None:
                existing.attach(alarm)
                self._notify_ringing()
            return existing
        session = RingSession(
            self.hass,
            self,
            self.registry,
            target,
            self.ring_config(alarm, duration=duration, sound=sound),
            alarm=alarm,
            kind=kind,
            message=message,
            label=label or (alarm.label if alarm else "Alarm"),
            origin=origin,
            loop=self.loop,
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
        if minutes < 1:
            raise AlarmError("Snooze must be at least 1 minute")
        session.dismiss(by="snooze")
        when = dt_util.as_local(dt_util.utcnow() + timedelta(minutes=minutes))
        when = when.replace(second=0, microsecond=0)
        if minutes >= 1 and when <= dt_util.now():
            when += timedelta(minutes=1)
        base = session.alarms[0] if session.alarms else None
        alarm = Alarm(
            target=session.target.entity_id,
            time=when.time(),
            date=when.date(),
            name=f"{session.label} (snoozed)",
            kind=session.kind,
            message=session.message,
            duration=base.duration if base else None,
            sound=base.sound if base else None,
        )
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

    # ----------------------------------------------------------- scheduling

    @callback
    def _cancel_timer(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

    async def _timer_fired(self, _now: datetime) -> None:
        self._unsub_timer = None
        await self._process()

    async def _process(self) -> None:
        """Fire due alarms and schedule the next wake-up."""
        if not self._started:
            return
        async with self._lock:
            self._cancel_timer()
            now = dt_util.utcnow()
            grace = self.missed_grace
            due: list[tuple[Alarm, datetime]] = []
            expired: list[Alarm] = []
            next_time: datetime | None = None
            changed = False

            for alarm in list(self.alarms.values()):
                if alarm.skipped_occurrence is not None and alarm.skipped_occurrence < now - grace:
                    alarm.skipped_occurrence = None
                    changed = True
                if not alarm.enabled:
                    continue
                occurrence = alarm.next_occurrence(alarm.pending_after())
                while occurrence is not None and occurrence < now - grace:
                    _LOGGER.warning(
                        "Missed %s '%s' scheduled %s", alarm.kind, alarm.label, occurrence
                    )
                    alarm.last_fired = occurrence
                    changed = True
                    occurrence = alarm.next_occurrence(occurrence)
                if occurrence is None:
                    if not alarm.is_recurring:
                        expired.append(alarm)
                    continue
                if occurrence <= now:
                    due.append((alarm, occurrence))
                elif next_time is None or occurrence < next_time:
                    next_time = occurrence

            for alarm in expired:
                _LOGGER.info("Removing expired one-time %s '%s'", alarm.kind, alarm.label)
                self.alarms.pop(alarm.id, None)
                changed = True

            for alarm, occurrence in due:
                await self._fire(alarm, occurrence)
                changed = True

            if changed:
                self._save()
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
        alarm.last_fired = occurrence
        if alarm.skipped_occurrence is not None and alarm.skipped_occurrence <= occurrence:
            alarm.skipped_occurrence = None
        target = self.target(alarm.target)
        if target is None:
            _LOGGER.error(
                "Cannot ring %s '%s': satellite %s no longer exists",
                alarm.kind,
                alarm.label,
                alarm.target,
            )
        else:
            _LOGGER.info("Ringing %s '%s' on %s", alarm.kind, alarm.label, target.display)
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
