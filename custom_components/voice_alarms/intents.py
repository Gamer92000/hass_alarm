"""Intents (also exposed as LLM tools) for Voice Alarms."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import intent
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    INTENT_DELETE,
    INTENT_DISMISS,
    INTENT_LIST,
    INTENT_SET,
    INTENT_SKIP_NEXT,
    INTENT_TYPES,
    INTENT_UPDATE,
    KIND_ALARM,
    KIND_REMINDER,
    RECENTLY_DISMISSED_SECONDS,
    WEEKDAY_CODES,
)
from .manager import AlarmError, AlarmManager
from .models import Alarm, ParseError, parse_date, parse_time, parse_weekdays
from .ringer import STATE_PAUSED, RingSession
from .speech import (
    describe_alarm,
    describe_briefly,
    format_day,
    format_days,
    format_relative,
    format_when,
    join_list,
)
from .targets import Target, get_target, get_target_for_device

_LOGGER = logging.getLogger(__name__)

WEEKDAYS_HELP = (
    "Weekdays the alarm repeats on, as a list or comma separated string of "
    f"{', '.join(WEEKDAY_CODES)}; 'daily', 'weekdays' and 'weekends' are also "
    "accepted. Omit for a one-time alarm."
)
TARGET_HELP = (
    "Name, area or entity id of the voice satellite. Defaults to the satellite the "
    "user is speaking through; only set it when the user names another one."
)
TIME_HELP = "Time in 24-hour HH:MM format, e.g. '06:30' or '18:00'."
DATE_HELP = (
    "Date for a one-time alarm as YYYY-MM-DD, or 'today', 'tomorrow' or a weekday name. "
    "Omit to use the next time the given time comes around."
)
MATCH_HELP = "Filters to pick the alarm(s): alarm_id (exact), name, time, weekdays, date, target."
ID_FILTER_HELP = "Exact alarm id from a previous listing."
NAME_FILTER_HELP = "Name or label of the alarm, to find it."
TIME_FILTER_HELP = "Ring time of the alarm, to find it; 24-hour HH:MM."
WEEKDAYS_FILTER_HELP = (
    "Repeat days of the alarm, to find it: list or comma separated "
    f"{', '.join(WEEKDAY_CODES)}, or 'daily', 'weekdays', 'weekends'."
)
DATE_FILTER_HELP = (
    "Day the alarm rings on, to find it: YYYY-MM-DD, 'today', 'tomorrow' or a weekday name."
)
TARGET_FILTER_HELP = "Satellite the alarm belongs to (name/area), to find it."


class IntentFailed(Exception):
    """User facing failure."""


class _VoiceAlarmIntent(intent.IntentHandler):
    """Base class."""

    platforms = None
    slot_schema: dict[str, Any] | None = None

    def __init__(self, manager: AlarmManager) -> None:
        self.manager = manager

    @property
    def hass(self) -> HomeAssistant:
        """Home Assistant."""
        return self.manager.hass

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _slot(intent_obj: intent.Intent, name: str) -> Any:
        slot = intent_obj.slots.get(name)
        if not slot:
            return None
        value = slot.get("value")
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    def _current_target(self, intent_obj: intent.Intent) -> Target | None:
        if intent_obj.satellite_id and (target := get_target(self.hass, intent_obj.satellite_id)):
            return target
        return get_target_for_device(self.hass, intent_obj.device_id)

    def _target_names(self) -> str:
        names = [t.display for t in self.manager.targets()]
        return join_list(names) if names else "none configured"

    def _resolve_target(self, intent_obj: intent.Intent, query: str | None) -> Target:
        if query:
            matches = self.manager.match_target(query)
            if len(matches) == 1:
                return matches[0]
            if not matches:
                raise IntentFailed(
                    f"I don't know a voice satellite called '{query}'. "
                    f"Available satellites: {self._target_names()}."
                )
            raise IntentFailed(
                f"'{query}' matches several satellites: "
                f"{join_list([t.display for t in matches])}. Which one?"
            )
        current = self._current_target(intent_obj)
        if current is not None:
            return current
        targets = self.manager.targets()
        if len(targets) == 1:
            return targets[0]
        raise IntentFailed(
            "I can't tell which voice satellite you are using, please name the target satellite. "
            f"Available satellites: {self._target_names()}."
        )

    def _match_alarms(self, intent_obj: intent.Intent) -> list[Alarm]:
        alarm_id = self._slot(intent_obj, "alarm_id")
        alarms = self.manager.sorted_alarms()
        if alarm_id:
            found = [a for a in alarms if a.id == alarm_id]
            if not found:
                raise IntentFailed(f"There is no alarm with id {alarm_id}.")
            return found
        target_query = self._slot(intent_obj, "target")
        if target_query:
            matches = self.manager.match_target(target_query)
            if not matches:
                raise IntentFailed(
                    f"I don't know a voice satellite called '{target_query}'. "
                    f"Available satellites: {self._target_names()}."
                )
            ids = {t.entity_id for t in matches}
            alarms = [a for a in alarms if a.target in ids]
        if time_text := self._slot(intent_obj, "time"):
            at = parse_time(time_text)
            alarms = [a for a in alarms if a.time == at]
        if name := self._slot(intent_obj, "name"):
            lowered = str(name).lower()
            exact = [a for a in alarms if (a.name or "").lower() == lowered]
            if exact:
                alarms = exact
            else:
                alarms = [
                    a
                    for a in alarms
                    if lowered in a.label.lower()
                    or (a.message and lowered in a.message.lower())
                    or (a.name and a.name.lower() in lowered)
                ]
        if weekdays := self._slot(intent_obj, "weekdays"):
            wanted = set(parse_weekdays(weekdays))
            if wanted:
                same = [a for a in alarms if set(a.weekdays) == wanted]
                alarms = same or [a for a in alarms if wanted & set(a.weekdays)]
        if date_text := self._slot(intent_obj, "date"):
            now = dt_util.utcnow()
            wanted_date = parse_date(date_text, now)
            alarms = [a for a in alarms if a.occurrence_on(wanted_date, now) is not None]
        return alarms

    def _has_filters(self, intent_obj: intent.Intent) -> bool:
        return any(
            self._slot(intent_obj, key)
            for key in ("alarm_id", "name", "time", "weekdays", "date", "target")
        )

    def _names_one(self, intent_obj: intent.Intent) -> bool:
        """True if the slots point at one particular alarm rather than a group."""
        return any(self._slot(intent_obj, key) for key in ("alarm_id", "name", "time"))

    def _pick_one(self, intent_obj: intent.Intent, candidates: list[Alarm], verb: str) -> Alarm:
        if not candidates:
            if not self.manager.alarms:
                raise IntentFailed("There are no alarms or reminders configured.")
            raise IntentFailed(
                f"No alarm matches. Configured: {self._describe_all(self.manager.sorted_alarms())}."
            )
        if len(candidates) == 1:
            return candidates[0]
        current = self._current_target(intent_obj)
        if current is not None:
            here = [a for a in candidates if a.target == current.entity_id]
            if len(here) == 1:
                return here[0]
        raise IntentFailed(
            f"{len(candidates)} alarms match, which one should I {verb}? "
            f"{self._describe_all(candidates)}."
        )

    def _describe_all(self, alarms: list[Alarm]) -> str:
        now = dt_util.utcnow()
        parts = [
            f"{describe_alarm(a, self.manager.target(a.target), now)} [id {a.id}]" for a in alarms
        ]
        return "; ".join(parts)

    # ------------------------------------------------------------- handling

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle with uniform error reporting."""
        response = intent_obj.create_response()
        try:
            await self._handle(intent_obj, response)
        except (IntentFailed, AlarmError, ParseError) as err:
            response.async_set_error(intent.IntentResponseErrorCode.FAILED_TO_HANDLE, str(err))
        except vol.Invalid as err:
            response.async_set_error(
                intent.IntentResponseErrorCode.FAILED_TO_HANDLE, f"Invalid input: {err}"
            )
        return response

    async def _handle(self, intent_obj: intent.Intent, response: intent.IntentResponse) -> None:
        raise NotImplementedError


class SetAlarmIntent(_VoiceAlarmIntent):
    """Create an alarm or reminder."""

    intent_type = INTENT_SET
    description = (
        "Create an alarm or a spoken reminder on a voice satellite. Examples: 'wake me at 7', "
        "'set an alarm for 6:30 on weekdays', 'remind me at 17:00 to call mom'. The alarm is "
        "one-time unless weekdays are given. Give a message to create a reminder that is spoken "
        "aloud instead of an alarm sound. Rings on the satellite the user is talking to unless "
        "a target is named. The response says exactly what was created; repeat it to the user."
    )
    slot_schema = {
        vol.Required("time", description=TIME_HELP): cv.string,
        vol.Optional("date", description=DATE_HELP): cv.string,
        vol.Optional("weekdays", description=WEEKDAYS_HELP): vol.Any(cv.string, [cv.string]),
        vol.Optional(
            "name", description="Short label for the alarm, e.g. 'work' or 'medication'."
        ): cv.string,
        vol.Optional(
            "message",
            description="Text to speak when it fires. Providing it makes this a reminder instead of an alarm.",
        ): cv.string,
        vol.Optional("target", description=TARGET_HELP): cv.string,
        vol.Optional(
            "duration_minutes",
            description="How many minutes the alarm sound plays before it stops by itself (default from settings, normally 5).",
        ): vol.Coerce(int),
    }

    async def _handle(self, intent_obj: intent.Intent, response: intent.IntentResponse) -> None:
        now = dt_util.utcnow()
        at = parse_time(self._slot(intent_obj, "time"))
        weekdays = parse_weekdays(self._slot(intent_obj, "weekdays"))
        date_text = self._slot(intent_obj, "date")
        if weekdays and date_text:
            raise IntentFailed(
                "An alarm either repeats on weekdays or rings once on a date, not both. Drop "
                "the date; a repeating alarm starts with its next occurrence."
            )
        on_date = parse_date(date_text, now) if date_text else None
        target = self._resolve_target(intent_obj, self._slot(intent_obj, "target"))
        message = self._slot(intent_obj, "message")
        duration_minutes = self._slot(intent_obj, "duration_minutes")
        alarm = self.manager.build_alarm(
            target=target.entity_id,
            at=at,
            on_date=on_date,
            weekdays=weekdays,
            name=self._slot(intent_obj, "name"),
            message=message,
            kind=KIND_REMINDER if message else KIND_ALARM,
            duration=int(duration_minutes) * 60 if duration_minutes else None,
        )
        alarm = await self.manager.async_add_alarm(alarm)
        nxt = alarm.next_pending(dt_util.utcnow())
        text = f"Created {describe_alarm(alarm, target, now)}."
        response.async_set_speech(text)
        response.async_set_speech_slots(
            {
                "alarm_id": alarm.id,
                "target": target.entity_id,
                "target_name": target.display,
                "next": nxt.isoformat() if nxt else None,
                "repeats": format_days(alarm.weekdays) if alarm.is_recurring else "once",
            }
        )


class ListAlarmsIntent(_VoiceAlarmIntent):
    """List alarms."""

    intent_type = INTENT_LIST
    description = (
        "List all configured alarms and reminders with their next ring time, and anything "
        "currently ringing. Optionally limit to one satellite. Give a date to get only what "
        "rings on that day as a short list of times, e.g. for 'when will you wake me "
        "tomorrow?' or 'do I have an alarm on Friday?'."
    )
    slot_schema = {
        vol.Optional(
            "target", description="Only list alarms on this satellite (name/area)."
        ): cv.string,
        vol.Optional(
            "date",
            description="Only list what rings on this day: YYYY-MM-DD, 'today', 'tomorrow' or "
            "a weekday name.",
        ): cv.string,
    }

    async def _handle(self, intent_obj: intent.Intent, response: intent.IntentResponse) -> None:
        now = dt_util.utcnow()
        target_query = self._slot(intent_obj, "target")
        alarms = self.manager.sorted_alarms()
        scope = ""
        scoped: list[Target] = []
        if target_query:
            scoped = self.manager.match_target(target_query)
            if not scoped:
                raise IntentFailed(
                    f"I don't know a voice satellite called '{target_query}'. "
                    f"Available satellites: {self._target_names()}."
                )
            ids = {t.entity_id for t in scoped}
            alarms = [a for a in alarms if a.target in ids]
            scope = f" on {join_list([t.display for t in scoped])}"

        if date_text := self._slot(intent_obj, "date"):
            day = parse_date(date_text, now)
            self._list_day(intent_obj, response, alarms, day, scope, scoped, now)
            return

        parts: list[str] = []
        if not alarms:
            parts.append(f"There are no alarms or reminders configured{scope}.")
        else:
            count = len(alarms)
            noun = "alarm" if count == 1 else "alarms"
            listing = "; ".join(
                f"{idx}. {describe_alarm(a, self.manager.target(a.target), now)}"
                for idx, a in enumerate(alarms, start=1)
            )
            parts.append(f"You have {count} {noun}{scope}: {listing}.")
        ringing = self.manager.active_sessions()
        if ringing:
            parts.append(
                "Currently ringing: " + join_list([_describe_session(s) for s in ringing]) + "."
            )
        response.async_set_speech(" ".join(parts))
        response.async_set_speech_slots(
            {
                "count": len(alarms),
                "alarms": [_alarm_summary(a, now) for a in alarms],
                "ringing": [s.to_dict() for s in ringing],
            }
        )

    def _list_day(
        self,
        intent_obj: intent.Intent,
        response: intent.IntentResponse,
        alarms: list[Alarm],
        day: date,
        scope: str,
        scoped: list[Target],
        now: datetime,
    ) -> None:
        """Answer 'what rings on <day>' with just the times, grouped by satellite."""
        rings: list[tuple[datetime, Alarm, bool]] = []
        for alarm in alarms:
            if not alarm.enabled:
                continue
            at = alarm.occurrence_on(day, now)
            if at is not None:
                rings.append((at, alarm, alarm.skipped_occurrence == at))
        rings.sort(key=lambda ring: (ring[0], ring[1].label.lower()))
        when = format_day(day, now)

        if not rings:
            text = f"There are no alarms or reminders {when}{scope}."
            upcoming = [a for a in alarms if a.next_pending(now) is not None]
            if upcoming:
                nxt = upcoming[0]
                described = describe_alarm(nxt, self.manager.target(nxt.target), now)
                text += f" The next one is the {described}."
            response.async_set_speech(text)
            response.async_set_speech_slots({"date": day.isoformat(), "count": 0, "alarms": []})
            return

        # Group by satellite, keeping time order. The satellite is named unless everything
        # is on the one the user is talking to (or the one they asked about).
        groups: dict[str, list[str]] = {}
        for at, alarm, skipped in rings:
            groups.setdefault(alarm.target, []).append(describe_briefly(alarm, at, skipped=skipped))
        implied = {t.entity_id for t in scoped}
        if (current := self._current_target(intent_obj)) is not None:
            implied.add(current.entity_id)
        name_targets = len(groups) > 1 or not set(groups) <= implied
        segments: list[str] = []
        for entity_id, items in groups.items():
            segment = join_list(items)
            if name_targets:
                target = self.manager.target(entity_id)
                segment += f" on {target.display if target else entity_id}"
            segments.append(segment)
        count = len(rings)
        noun = "alarm" if count == 1 else "alarms"
        text = f"{when[0].upper()}{when[1:]} you have {count} {noun}{scope}: {'; '.join(segments)}."
        response.async_set_speech(text)
        response.async_set_speech_slots(
            {
                "date": day.isoformat(),
                "count": count,
                "alarms": [
                    {
                        "alarm_id": alarm.id,
                        "label": alarm.label,
                        "kind": alarm.kind,
                        "target": alarm.target,
                        "rings_at": at.isoformat(),
                        "skipped": skipped,
                    }
                    for at, alarm, skipped in rings
                ],
            }
        )


class DeleteAlarmIntent(_VoiceAlarmIntent):
    """Delete alarms."""

    intent_type = INTENT_DELETE
    description = (
        "Delete (cancel, remove) alarms or reminders. " + MATCH_HELP + " Set all=true to delete "
        "every matching alarm, or every alarm when no filter is given. To silence a repeating "
        "alarm for one day use skip next instead. The response lists what was deleted."
    )
    slot_schema = {
        vol.Optional("alarm_id", description=ID_FILTER_HELP): cv.string,
        vol.Optional("name", description=NAME_FILTER_HELP): cv.string,
        vol.Optional("time", description=TIME_FILTER_HELP): cv.string,
        vol.Optional("weekdays", description=WEEKDAYS_FILTER_HELP): vol.Any(cv.string, [cv.string]),
        vol.Optional("date", description=DATE_FILTER_HELP): cv.string,
        vol.Optional("target", description=TARGET_FILTER_HELP): cv.string,
        vol.Optional(
            "all", description="Delete every matching alarm instead of exactly one."
        ): cv.boolean,
    }

    async def _handle(self, intent_obj: intent.Intent, response: intent.IntentResponse) -> None:
        now = dt_util.utcnow()
        candidates = self._match_alarms(intent_obj)
        if self._slot(intent_obj, "all"):
            if not candidates:
                raise IntentFailed("There are no alarms to delete.")
            deleted = [await self.manager.async_delete_alarm(a.id) for a in candidates]
        else:
            if not self._has_filters(intent_obj) and len(candidates) > 1:
                raise IntentFailed(
                    f"There are {len(candidates)} alarms, which one should I delete? "
                    f"{self._describe_all(candidates)}. Say all=true to delete all of them."
                )
            deleted = [
                await self.manager.async_delete_alarm(
                    self._pick_one(intent_obj, candidates, "delete").id
                )
            ]
        descriptions = [
            describe_alarm(a, self.manager.target(a.target), now, with_next=False) for a in deleted
        ]
        response.async_set_speech(f"Deleted {join_list(descriptions)}.")
        response.async_set_speech_slots({"deleted": [a.id for a in deleted]})


class SkipNextIntent(_VoiceAlarmIntent):
    """Skip the next occurrence of a repeating alarm."""

    intent_type = INTENT_SKIP_NEXT
    description = (
        "Skip only the next occurrence of a repeating alarm, e.g. 'skip tomorrow's alarm' or "
        "'don't wake me tomorrow'. Later occurrences stay. " + MATCH_HELP + " Without a name, "
        "time or id it skips every alarm of the next wake-up on the user's satellite (several "
        "alarms a few minutes apart count as one wake-up). Set all=true to skip every matching "
        "alarm, undo=true to reinstate skipped occurrences."
    )
    slot_schema = {
        vol.Optional("alarm_id", description=ID_FILTER_HELP): cv.string,
        vol.Optional("name", description=NAME_FILTER_HELP): cv.string,
        vol.Optional("time", description=TIME_FILTER_HELP): cv.string,
        vol.Optional("weekdays", description=WEEKDAYS_FILTER_HELP): vol.Any(cv.string, [cv.string]),
        vol.Optional(
            "date",
            description="Day of the ring to skip: YYYY-MM-DD, 'today', 'tomorrow' or a weekday "
            "name. Only the alarm's very next ring can be skipped.",
        ): cv.string,
        vol.Optional("target", description=TARGET_FILTER_HELP): cv.string,
        vol.Optional("all", description="Skip (or reinstate) every matching alarm."): cv.boolean,
        vol.Optional(
            "undo", description="Reinstate the skipped occurrence(s) instead."
        ): cv.boolean,
    }

    async def _handle(self, intent_obj: intent.Intent, response: intent.IntentResponse) -> None:
        now = dt_util.utcnow()
        undo = bool(self._slot(intent_obj, "undo"))
        candidates = [a for a in self._match_alarms(intent_obj) if a.is_recurring]
        if date_text := self._slot(intent_obj, "date"):
            day = parse_date(date_text, now)
            on_day = [a for a in candidates if _next_ring_day(a, now) == day]
            if candidates and not on_day:
                later = join_list(
                    [
                        f"'{a.label}' rings next {format_when(nxt, now)}"
                        for a in candidates
                        if (nxt := _next_ring(a, now)) is not None
                    ]
                )
                raise IntentFailed(f"I can only skip the very next ring: {later}.")
            candidates = on_day
        every = bool(self._slot(intent_obj, "all"))
        if not every and len(candidates) > 1 and not self._names_one(intent_obj):
            # "Don't wake me tomorrow": every alarm of the next wake-up on the user's
            # satellite (or the one asked about), not one picked at random.
            if self._slot(intent_obj, "target"):
                pool = candidates
            else:
                current = self._current_target(intent_obj)
                pool = [a for a in candidates if current and a.target == current.entity_id]
            if len(pool) > 1:
                first = min(_next_ring_day(a, now) for a in pool)
                candidates = [a for a in pool if _next_ring_day(a, now) == first]
                every = True
        if every and len(candidates) > 1:
            await self._skip_many(response, candidates, undo, now)
            return
        alarm = self._pick_one(intent_obj, candidates, "reinstate" if undo else "skip")
        target = self.manager.target(alarm.target)
        where = target.display if target else alarm.target
        if undo:
            if alarm.skipped_occurrence is None:
                raise IntentFailed(
                    f"The alarm '{alarm.label}' on {where} has no skipped occurrence."
                )
            alarm, restored = await self.manager.async_skip_next(alarm.id, undo=True)
            nxt = alarm.next_pending(now)
            text = f"Reinstated the alarm '{alarm.label}' on {where}"
            if restored:
                text += f" {format_when(restored, now)}"
            if nxt:
                text += f"; it rings next {format_when(nxt, now)} ({format_relative(nxt, now)})"
            response.async_set_speech(text + ".")
            response.async_set_speech_slots(
                {"alarm_id": alarm.id, "next": nxt.isoformat() if nxt else None}
            )
            return
        after = max(now, alarm.pending_after())
        scheduled = alarm.next_scheduled(after)
        if scheduled is not None and alarm.skipped_occurrence == scheduled:
            nxt = alarm.next_pending(now)
            text = (
                f"The alarm '{alarm.label}' on {where} {format_when(scheduled, now)} is already "
                "skipped"
            )
            if nxt:
                text += f"; it rings next {format_when(nxt, now)} ({format_relative(nxt, now)})"
            raise IntentFailed(text + ".")
        alarm, skipped = await self.manager.async_skip_next(alarm.id)
        nxt = alarm.next_pending(now)
        text = f"Skipping the alarm '{alarm.label}' on {where}"
        if skipped:
            text += f" {format_when(skipped, now)}"
        if nxt:
            text += f". It rings next {format_when(nxt, now)} ({format_relative(nxt, now)})"
        response.async_set_speech(text + ".")
        response.async_set_speech_slots(
            {
                "alarm_id": alarm.id,
                "skipped": skipped.isoformat() if skipped else None,
                "next": nxt.isoformat() if nxt else None,
            }
        )

    async def _skip_many(
        self,
        response: intent.IntentResponse,
        alarms: list[Alarm],
        undo: bool,
        now: datetime,
    ) -> None:
        """Skip (or reinstate) several alarms and describe them grouped by day and satellite."""
        if undo:
            alarms = [a for a in alarms if a.skipped_occurrence is not None]
            if not alarms:
                raise IntentFailed("None of the matching alarms has a skipped occurrence.")
        results = [await self.manager.async_skip_next(a.id, undo=undo) for a in alarms]
        results.sort(key=lambda r: (r[1] is None, r[1] or now, r[0].label.lower()))
        groups: dict[tuple[date, str], list[str]] = {}
        for alarm, at in results:
            if at is None:
                continue
            key = (dt_util.as_local(at).date(), alarm.target)
            groups.setdefault(key, []).append(describe_briefly(alarm, at))
        segments: list[str] = []
        for (day, entity_id), items in groups.items():
            target = self.manager.target(entity_id)
            where = target.display if target else entity_id
            segments.append(f"{join_list(items)} on {where} {format_day(day, now)}")
        verb = "Reinstated" if undo else "Skipping"
        text = f"{verb} {len(results)} alarms: {'; '.join(segments)}."
        nexts = [nxt for alarm, _ in results if (nxt := alarm.next_pending(now)) is not None]
        if nexts:
            nxt = min(nexts)
            text += f" The next ring is {format_when(nxt, now)} ({format_relative(nxt, now)})."
        response.async_set_speech(text)
        response.async_set_speech_slots(
            {
                "alarm_ids": [alarm.id for alarm, _ in results],
                "skipped": [at.isoformat() for _, at in results if at is not None],
                "next": min(nexts).isoformat() if nexts else None,
            }
        )


class UpdateAlarmIntent(_VoiceAlarmIntent):
    """Change an alarm."""

    intent_type = INTENT_UPDATE
    description = (
        "Change an existing alarm or reminder: move it to a new time, date or weekdays, rename it, "
        "move it to another satellite, change its message, or enable/disable it. "
        + MATCH_HELP
        + " Set all=true to change every matching alarm, or every alarm when no filter is "
        "given (e.g. 'disable all my alarms'). The response says exactly what changed."
    )
    slot_schema = {
        vol.Optional("alarm_id", description=ID_FILTER_HELP): cv.string,
        vol.Optional("name", description="Current name (to find the alarm)."): cv.string,
        vol.Optional("time", description="Current time (to find the alarm), HH:MM."): cv.string,
        vol.Optional("weekdays", description="Current weekdays (to find the alarm)."): vol.Any(
            cv.string, [cv.string]
        ),
        vol.Optional("date", description=DATE_FILTER_HELP): cv.string,
        vol.Optional("target", description="Current satellite (to find the alarm)."): cv.string,
        vol.Optional(
            "all", description="Change every matching alarm instead of exactly one."
        ): cv.boolean,
        vol.Optional("new_time", description="New time, 24-hour HH:MM."): cv.string,
        vol.Optional(
            "new_date",
            description="New date for a one-time alarm (YYYY-MM-DD, today, tomorrow, weekday).",
        ): cv.string,
        vol.Optional(
            "new_weekdays", description="New repeat days; 'none' makes it one-time."
        ): vol.Any(cv.string, [cv.string]),
        vol.Optional("new_name", description="New label."): cv.string,
        vol.Optional("new_message", description="New reminder text."): cv.string,
        vol.Optional("new_target", description="Satellite to move the alarm to."): cv.string,
        vol.Optional(
            "enabled", description="true to enable, false to disable (pause) the alarm."
        ): cv.boolean,
        vol.Optional("duration_minutes", description="New ring duration in minutes."): vol.Coerce(
            int
        ),
    }

    async def _handle(self, intent_obj: intent.Intent, response: intent.IntentResponse) -> None:
        now = dt_util.utcnow()
        candidates = self._match_alarms(intent_obj)
        if self._slot(intent_obj, "all"):
            if not candidates:
                raise IntentFailed("There are no alarms to change.")
            alarms = candidates
        else:
            alarms = [self._pick_one(intent_obj, candidates, "change")]
        changes: dict[str, Any] = {}
        described: list[str] = []
        if new_time := self._slot(intent_obj, "new_time"):
            changes["time"] = parse_time(new_time)
            described.append(f"time to {changes['time'].strftime('%H:%M')}")
        if (new_weekdays := self._slot(intent_obj, "new_weekdays")) is not None:
            if isinstance(new_weekdays, str) and new_weekdays.lower() in (
                "none",
                "never",
                "once",
                "one-time",
                "one time",
            ):
                changes["weekdays"] = []
                described.append("repeat to one-time")
            else:
                changes["weekdays"] = parse_weekdays(new_weekdays)
                described.append(f"repeat to {format_days(changes['weekdays'])}")
        if new_date := self._slot(intent_obj, "new_date"):
            changes["date"] = parse_date(new_date, now)
            described.append(f"date to {changes['date'].isoformat()}")
        if new_name := self._slot(intent_obj, "new_name"):
            changes["name"] = new_name
            described.append(f"name to '{new_name}'")
        if new_message := self._slot(intent_obj, "new_message"):
            changes["message"] = new_message
            described.append(f"message to '{new_message}'")
        if new_target := self._slot(intent_obj, "new_target"):
            target = self._resolve_target(intent_obj, new_target)
            changes["target"] = target.entity_id
            described.append(f"satellite to {target.display}")
        if (enabled := self._slot(intent_obj, "enabled")) is not None:
            changes["enabled"] = bool(enabled)
            described.append("enabled it" if enabled else "disabled it")
        if duration_minutes := self._slot(intent_obj, "duration_minutes"):
            changes["duration"] = int(duration_minutes) * 60
            described.append(f"ring duration to {duration_minutes} minutes")
        if not changes:
            raise IntentFailed(
                "Nothing to change: give a new time, days, name, target or enabled flag."
            )
        updated: list[Alarm] = []
        for alarm in alarms:
            alarm_changes = dict(changes)
            # A new date turns a repeating alarm into a one-time one unless days were given too.
            if "date" in alarm_changes and "weekdays" not in alarm_changes and alarm.is_recurring:
                alarm_changes["weekdays"] = []
            updated.append(await self.manager.async_update_alarm(alarm.id, **alarm_changes))
        descriptions = [describe_alarm(a, self.manager.target(a.target), now) for a in updated]
        if len(updated) == 1:
            text = f"Changed {join_list(described)}. It is now {descriptions[0]}."
        else:
            text = (
                f"Changed {join_list(described)} for {len(updated)} alarms. They are now: "
                f"{'; '.join(descriptions)}."
            )
        response.async_set_speech(text)
        nexts = [nxt for a in updated if (nxt := a.next_pending(now)) is not None]
        response.async_set_speech_slots(
            {
                "alarm_id": updated[0].id,
                "alarm_ids": [a.id for a in updated],
                "next": min(nexts).isoformat() if nexts else None,
            }
        )


class DismissIntent(_VoiceAlarmIntent):
    """Stop a ringing alarm."""

    intent_type = INTENT_DISMISS
    description = (
        "Stop (dismiss, silence) an alarm or reminder that is ringing right now, optionally "
        "snoozing it. Use for 'stop', 'dismiss the alarm', 'snooze 10 minutes'. Defaults to the "
        "satellite the user is talking to, otherwise whatever is ringing."
    )
    slot_schema = {
        vol.Optional("target", description="Satellite whose alarm to stop (name/area)."): cv.string,
        vol.Optional(
            "snooze_minutes",
            description="If given, the alarm rings again after this many minutes.",
        ): vol.Coerce(int),
    }

    async def _handle(self, intent_obj: intent.Intent, response: intent.IntentResponse) -> None:
        now = dt_util.utcnow()
        target_query = self._slot(intent_obj, "target")
        snooze = self._slot(intent_obj, "snooze_minutes")
        sessions: list[RingSession] = []
        if target_query:
            target = self._resolve_target(intent_obj, target_query)
            session = self.manager.session_for_target(target.entity_id)
            if session is None:
                raise IntentFailed(f"Nothing is ringing on {target.display}.")
            sessions = [session]
        else:
            current = self._current_target(intent_obj)
            if current and (session := self.manager.session_for_target(current.entity_id)):
                sessions = [session]
            else:
                sessions = self.manager.active_sessions()
        if not sessions:
            recent = self.manager.recently_finished(timedelta(seconds=RECENTLY_DISMISSED_SECONDS))
            if recent:
                last = recent[-1]
                assert last.finished_at is not None
                ago = int((now - last.finished_at).total_seconds())
                how = {
                    "device": "was stopped on the device",
                    "user": "was already dismissed",
                    "snooze": "was snoozed",
                }.get(last.dismissed_by or "", "already stopped")
                raise IntentFailed(
                    f"Nothing is ringing right now. The {last.kind} '{last.label}' on "
                    f"{last.target.display} {how} {ago} seconds ago."
                )
            raise IntentFailed("Nothing is ringing right now.")

        if snooze:
            created = [await self.manager.async_snooze(s, int(snooze)) for s in sessions]
            parts = []
            for session, alarm in zip(sessions, created, strict=True):
                nxt = alarm.next_pending(dt_util.utcnow())
                when = (
                    f" at {dt_util.as_local(nxt).strftime('%H:%M')} ({format_relative(nxt, now)})"
                    if nxt
                    else ""
                )
                parts.append(f"{_describe_session(session)}, rings again{when}")
            response.async_set_speech(f"Snoozed {join_list(parts)}.")
            response.async_set_speech_slots({"snoozed": [a.id for a in created]})
            return

        await self.manager.async_dismiss(
            None if len(sessions) > 1 else sessions[0].target.entity_id
        )
        for session in sessions:
            session.dismiss(by="user")
        response.async_set_speech(f"Stopped {join_list([_describe_session(s) for s in sessions])}.")
        response.async_set_speech_slots({"stopped": [s.target.entity_id for s in sessions]})


def _describe_session(session: RingSession) -> str:
    state = " (paused)" if session.state == STATE_PAUSED else ""
    return f"the {session.kind} '{session.label}' on {session.target.display}{state}"


def _alarm_summary(alarm: Alarm, now: datetime) -> dict[str, Any]:
    """Compact alarm record for tool responses (the LLM sees speech slots too)."""
    nxt = alarm.next_pending(now)
    return {
        "alarm_id": alarm.id,
        "label": alarm.label,
        "kind": alarm.kind,
        "target": alarm.target,
        "time": alarm.time.strftime("%H:%M"),
        "repeats": format_days(alarm.weekdays) if alarm.is_recurring else "once",
        "date": alarm.date.isoformat() if alarm.date else None,
        "next": nxt.isoformat() if nxt else None,
        "enabled": alarm.enabled,
    }


def _next_ring(alarm: Alarm, now: datetime) -> datetime | None:
    """The alarm's very next scheduled ring, skipped or not."""
    return alarm.next_scheduled(max(now, alarm.pending_after()))


def _next_ring_day(alarm: Alarm, now: datetime) -> date:
    """Local date of the very next ring (far future if there is none)."""
    nxt = _next_ring(alarm, now)
    return dt_util.as_local(nxt).date() if nxt is not None else date.max


@callback
def async_register_intents(hass: HomeAssistant, manager: AlarmManager) -> None:
    """Register all intents."""
    for handler_cls in (
        SetAlarmIntent,
        ListAlarmsIntent,
        DeleteAlarmIntent,
        SkipNextIntent,
        UpdateAlarmIntent,
        DismissIntent,
    ):
        intent.async_register(hass, handler_cls(manager))
    _LOGGER.debug("Registered %s intents for %s", len(INTENT_TYPES), DOMAIN)


@callback
def async_unregister_intents(hass: HomeAssistant) -> None:
    """Remove all intents."""
    for intent_type in INTENT_TYPES:
        intent.async_remove(hass, intent_type)
