"""Data model for Voice Alarms."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .const import KIND_ALARM, KIND_REMINDER, KINDS, WEEKDAY_CODES
from .i18n import WEEKDAYS, LocalizedError, default_language, tr

_TIME_RE = re.compile(
    r"^\s*(?P<h>\d{1,2})(?:[:.h](?P<m>\d{2}))?\s*(?:uhr)?\s*(?P<ampm>[ap]\.?m\.?)?\s*$",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"^\s*(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})\s*$")
_REL_RE = re.compile(r"^\s*\+\s*(?P<n>\d+)\s*(?:d|days?|tage?)?\s*$", re.IGNORECASE)

# Words the parsers accept in any supported language (the LLM is told to pass English
# or ISO forms, but a German conversation may well hand over 'morgen' or 'montags').
_WEEKDAY_ALIASES: dict[str, int] = {}
for _idx, _code in enumerate(WEEKDAY_CODES):
    _WEEKDAY_ALIASES[_code] = _idx
    for _names in WEEKDAYS.values():
        _WEEKDAY_ALIASES[_names[_idx].lower()] = _idx
        _WEEKDAY_ALIASES[_names[_idx].lower() + "s"] = _idx  # 'montags', 'mondays'
_WEEKDAY_ALIASES.update(
    {
        "tues": 1,
        "wednes": 2,
        "thur": 3,
        "thurs": 3,
        "mo": 0,
        "di": 1,
        "mi": 2,
        "do": 3,
        "fr": 4,
        "sa": 5,
        "so": 6,
        "sonnabend": 5,
    }
)

_EVERY_DAY = [0, 1, 2, 3, 4, 5, 6]
_WEEKDAY_GROUPS: dict[str, list[int]] = {
    "daily": _EVERY_DAY,
    "everyday": _EVERY_DAY,
    "every day": _EVERY_DAY,
    "all": _EVERY_DAY,
    "weekdays": [0, 1, 2, 3, 4],
    "workdays": [0, 1, 2, 3, 4],
    "weekend": [5, 6],
    "weekends": [5, 6],
    # German
    "täglich": _EVERY_DAY,
    "jeden tag": _EVERY_DAY,
    "alle": _EVERY_DAY,
    "wochentags": [0, 1, 2, 3, 4],
    "wochentage": [0, 1, 2, 3, 4],
    "werktags": [0, 1, 2, 3, 4],
    "werktage": [0, 1, 2, 3, 4],
    "wochenende": [5, 6],
    "am wochenende": [5, 6],
    "wochenenden": [5, 6],
}

_TODAY_WORDS = ("today", "now", "heute", "jetzt")
_TOMORROW_WORDS = ("tomorrow", "morgen")
_DAY_AFTER_WORDS = ("day after tomorrow", "overmorrow", "übermorgen")
_NEXT_PREFIXES = ("next ", "nächsten ", "nächster ", "nächste ", "kommenden ", "kommender ")
_THIS_PREFIXES = ("this ", "diesen ", "dieser ", "am ", "on ")


class ParseError(LocalizedError, ValueError):
    """Raised when user supplied input cannot be parsed."""


def parse_time(value: Any) -> time:
    """Parse a time given as 'HH:MM', 'H:MM', '7am', '7:30 pm' or a time object."""
    if isinstance(value, datetime):
        return value.time().replace(second=0, microsecond=0)
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    text = str(value)
    match = _TIME_RE.match(text)
    if not match:
        raise ParseError("err_time_format", text=text)
    hour = int(match.group("h"))
    minute = int(match.group("m") or 0)
    ampm = (match.group("ampm") or "").lower().replace(".", "")
    if ampm:
        if hour < 1 or hour > 12:
            raise ParseError("err_time_invalid", text=text)
        if ampm == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
    if hour > 23 or minute > 59:
        raise ParseError("err_time_format", text=text)
    return time(hour=hour, minute=minute)


def parse_weekdays(value: Any) -> list[int]:
    """Parse weekdays from a list or string of codes, names, ints or group words."""
    if value is None:
        return []
    if isinstance(value, str):
        lowered = value.strip().lower()
        if not lowered:
            return []
        if lowered in _WEEKDAY_GROUPS:
            return list(_WEEKDAY_GROUPS[lowered])
        parts: list[Any] = [p for p in re.split(r"[,\s/;]+|\band\b|\bund\b", lowered) if p]
    else:
        parts = list(value)
    result: set[int] = set()
    for part in parts:
        if isinstance(part, bool):
            raise ParseError("err_weekday", text=part)
        if isinstance(part, int):
            if 0 <= part <= 6:
                result.add(part)
                continue
            raise ParseError("err_weekday_int", text=part)
        text = str(part).strip().lower().rstrip(".")
        if not text:
            continue
        if text in _WEEKDAY_GROUPS:
            result.update(_WEEKDAY_GROUPS[text])
            continue
        if text in _WEEKDAY_ALIASES:
            result.add(_WEEKDAY_ALIASES[text])
            continue
        raise ParseError("err_weekday", text=part)
    return sorted(result)


def parse_date(value: Any, now: datetime) -> date:
    """Parse a date: ISO 'YYYY-MM-DD', 'today', 'tomorrow', weekday name, '+N'."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().lower()
    today = now.astimezone(dt_util.get_default_time_zone()).date()
    if text in _TODAY_WORDS:
        return today
    if text in _TOMORROW_WORDS:
        return today + timedelta(days=1)
    if text in _DAY_AFTER_WORDS:
        return today + timedelta(days=2)
    if match := _REL_RE.match(text):
        return today + timedelta(days=int(match.group("n")))
    if match := _DATE_RE.match(text):
        try:
            return date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
        except ValueError as err:
            raise ParseError("err_date_invalid", text=value) from err
    stripped = text
    is_next = False
    for prefix in _NEXT_PREFIXES + _THIS_PREFIXES:
        if stripped.startswith(prefix):
            is_next = prefix in _NEXT_PREFIXES
            stripped = stripped.removeprefix(prefix).strip()
            break
    if stripped in _WEEKDAY_ALIASES:
        weekday = _WEEKDAY_ALIASES[stripped]
        delta = (weekday - today.weekday()) % 7
        if delta == 0 and is_next:
            delta = 7
        return today + timedelta(days=delta)
    raise ParseError("err_date_format", text=value)


def combine_local(day: date, at: time) -> datetime:
    """Combine a local date and time into an aware datetime."""
    return datetime.combine(day, at, tzinfo=dt_util.get_default_time_zone())


@dataclass
class Alarm:
    """An alarm or reminder."""

    target: str
    time: time
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str | None = None
    date: date | None = None
    weekdays: list[int] = field(default_factory=list)
    kind: str = KIND_ALARM
    message: str | None = None
    duration: int | None = None
    sound: str | None = None
    enabled: bool = True
    skipped_occurrence: datetime | None = None
    last_fired: datetime | None = None
    created: datetime = field(default_factory=dt_util.utcnow)

    def __post_init__(self) -> None:
        """Normalise fields."""
        self.weekdays = sorted(set(self.weekdays))
        if self.kind not in KINDS:
            self.kind = KIND_REMINDER if self.message else KIND_ALARM
        if self.message is not None and not self.message.strip():
            self.message = None
        if self.name is not None and not self.name.strip():
            self.name = None
        if self.sound is not None and not self.sound.strip():
            self.sound = None
        self.time = self.time.replace(second=0, microsecond=0)

    # ---- derived properties -------------------------------------------------

    @property
    def is_recurring(self) -> bool:
        """Return True if the alarm repeats weekly."""
        return bool(self.weekdays)

    @property
    def is_reminder(self) -> bool:
        """Return True if the alarm is a spoken reminder."""
        return self.kind == KIND_REMINDER

    @property
    def label(self) -> str:
        """Short human label ('Alarm 07:00' in the instance language when unnamed)."""
        if self.name:
            return self.name
        if self.is_reminder and self.message:
            return self.message
        kind = tr(default_language(), "label_reminder" if self.is_reminder else "label_alarm")
        return f"{kind} {self.time.strftime('%H:%M')}"

    # ---- occurrence computation --------------------------------------------

    def occurrences_after(self, after: datetime, days: int = 15) -> Iterator[datetime]:
        """Yield scheduled occurrences strictly after ``after`` (ignores skips)."""
        if not self.is_recurring:
            if self.date is None:
                return
            candidate = combine_local(self.date, self.time)
            if candidate > after:
                yield candidate
            return
        start = after.astimezone(dt_util.get_default_time_zone()).date()
        for offset in range(days):
            day = start + timedelta(days=offset)
            if day.weekday() not in self.weekdays:
                continue
            candidate = combine_local(day, self.time)
            if candidate > after:
                yield candidate

    def next_occurrence(self, after: datetime | None = None) -> datetime | None:
        """Return the next occurrence after ``after`` honouring the skipped one."""
        if after is None:
            after = dt_util.utcnow()
        for candidate in self.occurrences_after(after):
            if self.skipped_occurrence is not None and candidate == self.skipped_occurrence:
                continue
            return candidate
        return None

    def next_scheduled(self, after: datetime | None = None) -> datetime | None:
        """Return the next occurrence ignoring the skip (what would be skipped)."""
        if after is None:
            after = dt_util.utcnow()
        return next(iter(self.occurrences_after(after)), None)

    def pending_after(self) -> datetime:
        """Reference point: occurrences after this are still to be fired."""
        if self.last_fired is not None:
            return self.last_fired
        return self.created

    def next_pending(self, now: datetime) -> datetime | None:
        """Return the next occurrence that still has to fire (>= now context)."""
        if not self.enabled:
            return None
        return self.next_occurrence(max(now, self.pending_after()))

    def occurrence_on(self, day: date, now: datetime) -> datetime | None:
        """Return the still-pending occurrence on the local ``day``, ignoring skips."""
        start = combine_local(day, time(0, 0))
        end = combine_local(day + timedelta(days=1), time(0, 0))
        after = max(now, self.pending_after(), start - timedelta(microseconds=1))
        at = self.next_scheduled(after)
        if at is None or at >= end:
            return None
        return at

    # ---- (de)serialisation ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise for storage."""
        return {
            "id": self.id,
            "target": self.target,
            "time": self.time.strftime("%H:%M"),
            "name": self.name,
            "date": self.date.isoformat() if self.date else None,
            "weekdays": list(self.weekdays),
            "kind": self.kind,
            "message": self.message,
            "duration": self.duration,
            "sound": self.sound,
            "enabled": self.enabled,
            "skipped_occurrence": (
                self.skipped_occurrence.isoformat() if self.skipped_occurrence else None
            ),
            "last_fired": self.last_fired.isoformat() if self.last_fired else None,
            "created": self.created.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Alarm:
        """Restore from storage."""
        return cls(
            id=data["id"],
            target=data["target"],
            time=parse_time(data["time"]),
            name=data.get("name"),
            date=date.fromisoformat(data["date"]) if data.get("date") else None,
            weekdays=[int(d) for d in data.get("weekdays") or []],
            kind=data.get("kind") or KIND_ALARM,
            message=data.get("message"),
            duration=data.get("duration"),
            sound=data.get("sound"),
            enabled=bool(data.get("enabled", True)),
            skipped_occurrence=parse_dt(data.get("skipped_occurrence")),
            last_fired=parse_dt(data.get("last_fired")),
            created=parse_dt(data.get("created")) or dt_util.utcnow(),
        )

    def public_dict(self, now: datetime | None = None) -> dict[str, Any]:
        """Serialise for the frontend / service responses with computed fields."""
        now = now or dt_util.utcnow()
        after = max(now, self.pending_after())
        nxt = self.next_occurrence(after) if self.enabled else None
        scheduled = self.next_scheduled(after) if self.enabled else None
        data = self.to_dict()
        data.update(
            {
                "label": self.label,
                "is_recurring": self.is_recurring,
                "next": nxt.isoformat() if nxt else None,
                "next_skipped": bool(
                    self.enabled
                    and scheduled is not None
                    and self.skipped_occurrence is not None
                    and scheduled == self.skipped_occurrence
                ),
            }
        )
        return data


def parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO datetime string into an aware UTC datetime."""
    if not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return dt_util.as_utc(parsed)
