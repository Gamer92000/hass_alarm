"""Human readable descriptions of alarms for voice responses.

Every function takes the language of the conversation (``"en"`` or ``"de"``); the
wording comes from the tables in ``i18n.py``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.util import dt as dt_util

from .i18n import DEFAULT_LANGUAGE, MONTHS, WEEKDAYS, tr
from .models import Alarm
from .targets import Target


def join_list(items: list[str], language: str = DEFAULT_LANGUAGE) -> str:
    """Join with commas and 'and'."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + tr(language, "and") + items[-1]


def weekday_name(weekday: int, language: str = DEFAULT_LANGUAGE) -> str:
    """Full weekday name (0 = Monday)."""
    return (WEEKDAYS.get(language) or WEEKDAYS[DEFAULT_LANGUAGE])[weekday]


def format_days(weekdays: list[int], language: str = DEFAULT_LANGUAGE) -> str:
    """Describe a weekday set."""
    days = sorted(set(weekdays))
    if days == [0, 1, 2, 3, 4, 5, 6]:
        return tr(language, "days_every_day")
    if days == [0, 1, 2, 3, 4]:
        return tr(language, "days_weekdays")
    if days == [5, 6]:
        return tr(language, "days_weekends")
    names = [weekday_name(d, language) for d in days]
    return tr(language, "days_every", days=join_list(names, language))


def _unit(n: int, unit: str, language: str) -> str:
    return tr(language, f"unit_{unit}" if n == 1 else f"unit_{unit}s", n=n)


def format_relative(
    target: datetime, now: datetime | None = None, language: str = DEFAULT_LANGUAGE
) -> str:
    """Return 'in 2 hours and 5 minutes' style text."""
    now = now or dt_util.utcnow()
    delta = target - now
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return tr(language, "rel_past")
    if seconds < 60:
        return tr(language, "rel_under_minute")
    minutes, _ = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts: list[str] = []
    if days:
        parts.append(_unit(days, "day", language))
    if hours:
        parts.append(_unit(hours, "hour", language))
    if minutes and not days:
        parts.append(_unit(minutes, "minute", language))
    if not parts:
        return tr(language, "rel_under_minute")
    if len(parts) == 1:
        return tr(language, "rel_in", a=parts[0])
    return tr(language, "rel_in_two", a=parts[0], b=parts[1])


def format_long_day(day: date, language: str = DEFAULT_LANGUAGE, *, year: bool = False) -> str:
    """Return 'Tuesday 8 September' (English) or 'Dienstag, 8. September' (German)."""
    month = (MONTHS.get(language) or MONTHS[DEFAULT_LANGUAGE])[day.month - 1]
    return tr(
        language,
        "long_day_year" if year else "long_day",
        weekday=weekday_name(day.weekday(), language),
        day=day.day,
        month=month,
        year=day.year,
    )


def format_day(day: date, now: datetime | None = None, language: str = DEFAULT_LANGUAGE) -> str:
    """Return 'today', 'tomorrow (Tuesday 8 September)' or 'on Friday 11 September'."""
    now = now or dt_util.utcnow()
    today = dt_util.as_local(now).date()
    long_day = format_long_day(day, language, year=day.year != today.year)
    if day == today:
        return tr(language, "day_today")
    if day == today + timedelta(days=1):
        return tr(language, "day_tomorrow", day=long_day)
    return tr(language, "day_on", day=long_day)


def format_when(
    target: datetime, now: datetime | None = None, language: str = DEFAULT_LANGUAGE
) -> str:
    """Return 'today at 18:00', 'tomorrow (Tuesday 8 September) at 06:30', ..."""
    local = dt_util.as_local(target)
    return tr(
        language,
        "when_at",
        day=format_day(local.date(), now, language),
        time=local.strftime("%H:%M"),
    )


def format_duration(seconds: int, language: str = DEFAULT_LANGUAGE) -> str:
    """Describe a duration in seconds."""
    if seconds % 60 == 0:
        return _unit(seconds // 60, "minute", language)
    return tr(language, "unit_seconds", n=seconds)


def describe_schedule(alarm: Alarm, language: str = DEFAULT_LANGUAGE) -> str:
    """Describe when an alarm is scheduled: '06:30 on weekdays' / '18:00 on ...'."""
    clock = alarm.time.strftime("%H:%M")
    if alarm.is_recurring:
        return tr(
            language, "schedule_recurring", time=clock, days=format_days(alarm.weekdays, language)
        )
    if alarm.date:
        return tr(language, "schedule_date", time=clock, day=format_long_day(alarm.date, language))
    return clock


def describe_alarm(
    alarm: Alarm,
    target: Target | None,
    now: datetime | None = None,
    *,
    with_next: bool = True,
    language: str = DEFAULT_LANGUAGE,
) -> str:
    """Describe an alarm in one sentence fragment."""
    now = now or dt_util.utcnow()
    kind = "reminder" if alarm.is_reminder else "alarm"
    kind_text = tr(language, f"kind_{kind}_{'repeating' if alarm.is_recurring else 'once'}")
    text = tr(
        language,
        "alarm_desc",
        kind=kind_text,
        label=alarm.label,
        schedule=describe_schedule(alarm, language),
    )
    if alarm.is_reminder and alarm.message and alarm.message != alarm.label:
        text += tr(language, "alarm_desc_saying", message=alarm.message)
    where = target.display if target else alarm.target
    text += tr(language, "alarm_desc_on", where=where)
    if not alarm.enabled:
        return text + tr(language, "alarm_desc_disabled")
    if with_next:
        after = max(now, alarm.pending_after())
        nxt = alarm.next_occurrence(after)
        scheduled = alarm.next_scheduled(after)
        if (
            scheduled is not None
            and alarm.skipped_occurrence is not None
            and scheduled == alarm.skipped_occurrence
        ):
            text += tr(language, "alarm_desc_skipping", when=format_when(scheduled, now, language))
        if nxt is not None:
            text += tr(
                language,
                "alarm_desc_next",
                when=format_when(nxt, now, language),
                relative=format_relative(nxt, now, language),
            )
        elif not alarm.is_recurring:
            text += tr(language, "alarm_desc_past")
    return text


def describe_briefly(
    alarm: Alarm, at: datetime, *, skipped: bool = False, language: str = DEFAULT_LANGUAGE
) -> str:
    """Describe one ring in a day listing: '08:45', '08:45 (work)', 'a reminder 'x' at 17:00'."""
    clock = dt_util.as_local(at).strftime("%H:%M")
    notes: list[str] = []
    if alarm.is_reminder:
        text = tr(language, "brief_reminder", label=alarm.label, time=clock)
    else:
        text = clock
        if alarm.name:
            notes.append(alarm.name)
    if skipped:
        notes.append(tr(language, "brief_skipped"))
    if notes:
        text += f" ({', '.join(notes)})"
    return text


def capitalize(text: str) -> str:
    """Upper-case the first character only (str.capitalize lowers the rest)."""
    return text[:1].upper() + text[1:]
