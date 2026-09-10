"""Human readable descriptions of alarms for voice responses."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.util import dt as dt_util

from .const import WEEKDAY_NAMES
from .models import Alarm
from .targets import Target


def format_days(weekdays: list[int]) -> str:
    """Describe a weekday set."""
    days = sorted(set(weekdays))
    if days == [0, 1, 2, 3, 4, 5, 6]:
        return "every day"
    if days == [0, 1, 2, 3, 4]:
        return "weekdays"
    if days == [5, 6]:
        return "weekends"
    names = [WEEKDAY_NAMES[d] for d in days]
    if len(names) == 1:
        return f"every {names[0]}"
    return "every " + ", ".join(names[:-1]) + " and " + names[-1]


def format_relative(target: datetime, now: datetime | None = None) -> str:
    """Return 'in 2 hours and 5 minutes' style text."""
    now = now or dt_util.utcnow()
    delta = target - now
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "in the past"
    if seconds < 60:
        return "in less than a minute"
    minutes, _ = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts: list[str] = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes and not days:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if not parts:
        return "in less than a minute"
    if len(parts) == 1:
        return f"in {parts[0]}"
    return f"in {parts[0]} and {parts[1]}"


def format_day(day: date, now: datetime | None = None) -> str:
    """Return 'today', 'tomorrow (Tuesday 8 September)' or 'on Friday 11 September'."""
    now = now or dt_util.utcnow()
    today = dt_util.as_local(now).date()
    long_day = f"{WEEKDAY_NAMES[day.weekday()]} {day.day} {day.strftime('%B')}"
    if day.year != today.year:
        long_day += f" {day.year}"
    if day == today:
        return "today"
    if day == today + timedelta(days=1):
        return f"tomorrow ({long_day})"
    return f"on {long_day}"


def format_when(target: datetime, now: datetime | None = None) -> str:
    """Return 'today at 18:00', 'tomorrow (Tuesday 8 September) at 06:30', ..."""
    local = dt_util.as_local(target)
    return f"{format_day(local.date(), now)} at {local.strftime('%H:%M')}"


def format_duration(seconds: int) -> str:
    """Describe a duration in seconds."""
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return f"{seconds} seconds"


def describe_schedule(alarm: Alarm) -> str:
    """Describe when an alarm is scheduled: '06:30 on weekdays' / '18:00 on ...'."""
    clock = alarm.time.strftime("%H:%M")
    if alarm.is_recurring:
        return f"{clock} {format_days(alarm.weekdays)}"
    if alarm.date:
        day = alarm.date
        return f"{clock} on {WEEKDAY_NAMES[day.weekday()]} {day.day} {day.strftime('%B')}"
    return clock


def describe_alarm(
    alarm: Alarm,
    target: Target | None,
    now: datetime | None = None,
    *,
    with_next: bool = True,
) -> str:
    """Describe an alarm in one sentence fragment."""
    now = now or dt_util.utcnow()
    kind = "reminder" if alarm.is_reminder else "alarm"
    if alarm.is_recurring:
        kind = f"repeating {kind}"
    else:
        kind = f"one-time {kind}"
    text = f"{kind} '{alarm.label}' at {describe_schedule(alarm)}"
    if alarm.is_reminder and alarm.message and alarm.message != alarm.label:
        text += f" saying '{alarm.message}'"
    where = target.display if target else alarm.target
    text += f" on {where}"
    if not alarm.enabled:
        text += " (disabled)"
        return text
    if with_next:
        after = max(now, alarm.pending_after())
        nxt = alarm.next_occurrence(after)
        scheduled = alarm.next_scheduled(after)
        if (
            scheduled is not None
            and alarm.skipped_occurrence is not None
            and scheduled == alarm.skipped_occurrence
        ):
            text += f", skipping {format_when(scheduled, now)}"
        if nxt is not None:
            text += f", next {format_when(nxt, now)} ({format_relative(nxt, now)})"
        elif not alarm.is_recurring:
            text += " (already in the past)"
    return text


def describe_briefly(alarm: Alarm, at: datetime, *, skipped: bool = False) -> str:
    """Describe one ring in a day listing: '08:45', '08:45 (work)', 'a reminder 'x' at 17:00'."""
    clock = dt_util.as_local(at).strftime("%H:%M")
    notes: list[str] = []
    if alarm.is_reminder:
        text = f"a reminder '{alarm.label}' at {clock}"
    else:
        text = clock
        if alarm.name:
            notes.append(alarm.name)
    if skipped:
        notes.append("skipped")
    if notes:
        text += f" ({', '.join(notes)})"
    return text


def join_list(items: list[str]) -> str:
    """Join with commas and 'and'."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
