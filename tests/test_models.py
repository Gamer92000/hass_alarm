"""Tests for parsing and occurrence computation."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.voice_alarms.models import (
    Alarm,
    ParseError,
    parse_date,
    parse_time,
    parse_weekdays,
)
from homeassistant.util import dt as dt_util

TZ = ZoneInfo("Europe/Zurich")


@pytest.fixture(autouse=True)
def _local_tz():
    old = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(TZ)
    yield
    dt_util.set_default_time_zone(old)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("06:30", time(6, 30)),
        ("6:30", time(6, 30)),
        ("18:05", time(18, 5)),
        ("7am", time(7, 0)),
        ("7 pm", time(19, 0)),
        ("12am", time(0, 0)),
        ("12:15 PM", time(12, 15)),
        ("7", time(7, 0)),
        ("6.30", time(6, 30)),
        (time(9, 1, 30), time(9, 1)),
    ],
)
def test_parse_time(text, expected) -> None:
    assert parse_time(text) == expected


@pytest.mark.parametrize("text", ["25:00", "7:60", "13pm", "noon", ""])
def test_parse_time_invalid(text) -> None:
    with pytest.raises(ParseError):
        parse_time(text)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, []),
        ("", []),
        ("mon", [0]),
        ("Mon, Wed and fri", [0, 2, 4]),
        (["tue", "thursday"], [1, 3]),
        ("weekdays", [0, 1, 2, 3, 4]),
        ("weekend", [5, 6]),
        ("daily", [0, 1, 2, 3, 4, 5, 6]),
        ([0, 6], [0, 6]),
        ("sun,sun", [6]),
    ],
)
def test_parse_weekdays(value, expected) -> None:
    assert parse_weekdays(value) == expected


def test_parse_weekdays_invalid() -> None:
    with pytest.raises(ParseError):
        parse_weekdays("funday")


def test_parse_date() -> None:
    now = datetime(2026, 9, 7, 10, 0, tzinfo=TZ)  # Monday
    assert parse_date("2026-09-10", now) == date(2026, 9, 10)
    assert parse_date("today", now) == date(2026, 9, 7)
    assert parse_date("tomorrow", now) == date(2026, 9, 8)
    assert parse_date("friday", now) == date(2026, 9, 11)
    assert parse_date("monday", now) == date(2026, 9, 7)
    assert parse_date("next monday", now) == date(2026, 9, 14)
    assert parse_date("+3", now) == date(2026, 9, 10)
    with pytest.raises(ParseError):
        parse_date("someday", now)


def test_one_time_occurrence() -> None:
    created = datetime(2026, 9, 7, 10, 0, tzinfo=TZ)
    alarm = Alarm(
        target="assist_satellite.x", time=time(18, 0), date=date(2026, 9, 7), created=created
    )
    assert alarm.next_occurrence(created) == datetime(2026, 9, 7, 18, 0, tzinfo=TZ)
    assert alarm.next_occurrence(datetime(2026, 9, 7, 18, 0, tzinfo=TZ)) is None
    assert not alarm.is_recurring


def test_recurring_occurrence_and_skip() -> None:
    created = datetime(2026, 9, 7, 10, 0, tzinfo=TZ)  # Monday
    alarm = Alarm(
        target="assist_satellite.x", time=time(7, 0), weekdays=[0, 1, 2, 3, 4], created=created
    )
    tuesday = datetime(2026, 9, 8, 7, 0, tzinfo=TZ)
    wednesday = datetime(2026, 9, 9, 7, 0, tzinfo=TZ)
    assert alarm.next_occurrence(created) == tuesday
    assert alarm.next_pending(created) == tuesday

    alarm.skipped_occurrence = tuesday.astimezone(dt_util.UTC)
    assert alarm.next_occurrence(created) == wednesday
    assert alarm.next_scheduled(created) == tuesday
    assert alarm.public_dict(created)["next_skipped"] is True
    assert alarm.public_dict(created)["next"] == wednesday.isoformat()

    # Friday evening -> Monday
    friday_evening = datetime(2026, 9, 11, 20, 0, tzinfo=TZ)
    alarm.skipped_occurrence = None
    assert alarm.next_occurrence(friday_evening) == datetime(2026, 9, 14, 7, 0, tzinfo=TZ)


def test_last_fired_moves_pending() -> None:
    created = datetime(2026, 9, 7, 6, 0, tzinfo=TZ)
    alarm = Alarm(
        target="assist_satellite.x",
        time=time(7, 0),
        weekdays=[0, 1, 2, 3, 4, 5, 6],
        created=created,
    )
    monday_7 = datetime(2026, 9, 7, 7, 0, tzinfo=TZ)
    assert alarm.next_pending(created) == monday_7
    alarm.last_fired = monday_7
    # right at firing time the next pending one is tomorrow
    assert alarm.next_pending(monday_7) == monday_7 + timedelta(days=1)


def test_roundtrip() -> None:
    alarm = Alarm(
        target="assist_satellite.x",
        time=time(7, 30),
        weekdays=[0, 2],
        name="Work",
        message=None,
        duration=120,
        sound="media-source://media_source/local/a.mp3",
        skipped_occurrence=datetime(2026, 9, 9, 5, 30, tzinfo=dt_util.UTC),
    )
    restored = Alarm.from_dict(alarm.to_dict())
    assert restored == alarm
    assert restored.label == "Work"


def test_label_and_kind() -> None:
    reminder = Alarm(target="assist_satellite.x", time=time(17, 0), message="call mom", kind="nope")
    assert reminder.is_reminder
    assert reminder.label == "call mom"
    plain = Alarm(target="assist_satellite.x", time=time(17, 0))
    assert plain.label == "Alarm 17:00"
