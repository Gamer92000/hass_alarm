"""German responses, labels and input words (the English suite covers the wording there)."""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory

from custom_components.voice_alarms.const import (
    INTENT_DELETE,
    INTENT_DISMISS,
    INTENT_LIST,
    INTENT_SET,
    INTENT_SKIP_NEXT,
    INTENT_UPDATE,
    KIND_REMINDER,
)
from custom_components.voice_alarms.i18n import (
    STRINGS,
    default_language,
    normalize_language,
    set_default_language,
)
from custom_components.voice_alarms.manager import AlarmError
from custom_components.voice_alarms.models import (
    Alarm,
    ParseError,
    parse_date,
    parse_time,
    parse_weekdays,
)
from custom_components.voice_alarms.speech import (
    describe_alarm,
    format_days,
    format_relative,
    format_when,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.util import dt as dt_util

from .conftest import slot

TZ = ZoneInfo("Europe/Zurich")
START = datetime(2026, 9, 7, 10, 0, tzinfo=TZ)  # Monday


@pytest.fixture(autouse=True)
def _reset_default_language():
    yield
    set_default_language("en")


@pytest.fixture
def local_tz():
    old = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(TZ)
    yield
    dt_util.set_default_time_zone(old)


@pytest.fixture
async def ready(hass: HomeAssistant, freezer: FrozenDateTimeFactory, setup_integration, manager):
    await hass.config.async_set_time_zone("Europe/Zurich")
    freezer.move_to(START)
    return manager


async def handle(
    hass: HomeAssistant,
    intent_type: str,
    device_id: str | None = None,
    language: str = "de-DE",
    **slots,
):
    return await intent.async_handle(
        hass,
        "test",
        intent_type,
        {k: slot(v) for k, v in slots.items()},
        device_id=device_id,
        language=language,
    )


def speech(response: intent.IntentResponse) -> str:
    return response.speech["plain"]["speech"]


# ----------------------------------------------------------------- i18n table


def test_tables_are_complete() -> None:
    """Every language has every key with the same placeholders."""
    import re

    placeholders = {key: set(re.findall(r"{(\w+)}", text)) for key, text in STRINGS["en"].items()}
    for language, table in STRINGS.items():
        assert set(table) == set(STRINGS["en"]), language
        for key, text in table.items():
            assert set(re.findall(r"{(\w+)}", text)) == placeholders[key], (language, key)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [("de", "de"), ("de-DE", "de"), ("de_CH", "de"), ("en-GB", "en"), ("fr", "en"), (None, "en")],
)
def test_normalize_language(tag: str | None, expected: str) -> None:
    assert normalize_language(tag) == expected


# --------------------------------------------------------------------- speech


def test_format_days_german() -> None:
    assert format_days([0, 1, 2, 3, 4], "de") == "wochentags"
    assert format_days([5, 6], "de") == "am Wochenende"
    assert format_days([0, 1, 2, 3, 4, 5, 6], "de") == "täglich"
    assert format_days([0, 2, 4], "de") == "jeden Montag, Mittwoch und Freitag"
    assert format_days([6], "de") == "jeden Sonntag"


def test_format_relative_german() -> None:
    assert format_relative(START + timedelta(hours=20, minutes=5), START, "de") == (
        "in 20 Stunden und 5 Minuten"
    )
    assert format_relative(START + timedelta(minutes=1), START, "de") == "in 1 Minute"
    assert format_relative(START + timedelta(hours=1), START, "de") == "in 1 Stunde"
    assert format_relative(START + timedelta(days=2, hours=3), START, "de") == (
        "in 2 Tagen und 3 Stunden"
    )
    assert format_relative(START + timedelta(days=1), START, "de") == "in 1 Tag"
    assert format_relative(START - timedelta(seconds=1), START, "de") == "in der Vergangenheit"
    assert format_relative(START + timedelta(seconds=30), START, "de") == (
        "in weniger als einer Minute"
    )


def test_format_when_german(local_tz) -> None:
    assert format_when(START.replace(hour=18), START, "de") == "heute um 18:00"
    assert format_when(START + timedelta(days=1, hours=-4, minutes=30), START, "de") == (
        "morgen (Dienstag, 8. September) um 06:30"
    )
    assert format_when(START + timedelta(days=4), START, "de") == (
        "am Freitag, 11. September um 10:00"
    )
    assert format_when(datetime(2027, 1, 8, 7, 0, tzinfo=TZ), START, "de") == (
        "am Freitag, 8. Januar 2027 um 07:00"
    )


def test_describe_alarm_german(local_tz) -> None:
    alarm = Alarm(
        target="assist_satellite.x", time=time(6, 30), weekdays=[0, 1, 2, 3, 4], name="Arbeit"
    )
    alarm.created = START
    assert describe_alarm(alarm, None, START, language="de") == (
        "wiederkehrender Wecker 'Arbeit' um 06:30 wochentags auf assist_satellite.x, "
        "nächstes Mal morgen (Dienstag, 8. September) um 06:30 (in 20 Stunden und 30 Minuten)"
    )
    reminder = Alarm(
        target="assist_satellite.x",
        time=time(17, 0),
        date=START.date(),
        kind=KIND_REMINDER,
        name="Anruf",
        message="Mama anrufen",
        enabled=False,
    )
    assert describe_alarm(reminder, None, START, language="de") == (
        "einmalige Erinnerung 'Anruf' um 17:00 am Montag, 7. September mit dem Text "
        "'Mama anrufen' auf assist_satellite.x (deaktiviert)"
    )


# -------------------------------------------------------------------- parsing


def test_parse_german_words(local_tz) -> None:
    assert parse_weekdays("montag, mittwoch und freitag") == [0, 2, 4]
    assert parse_weekdays("wochentags") == [0, 1, 2, 3, 4]
    assert parse_weekdays("täglich") == [0, 1, 2, 3, 4, 5, 6]
    assert parse_weekdays("am wochenende") == [5, 6]
    assert parse_weekdays(["Mo", "Di", "Sa"]) == [0, 1, 5]
    assert parse_weekdays("montags") == [0]
    assert parse_date("heute", START) == START.date()
    assert parse_date("morgen", START) == START.date() + timedelta(days=1)
    assert parse_date("übermorgen", START) == START.date() + timedelta(days=2)
    assert parse_date("freitag", START).isoformat() == "2026-09-11"
    assert parse_date("am Freitag", START).isoformat() == "2026-09-11"
    assert parse_date("nächsten Montag", START).isoformat() == "2026-09-14"
    assert parse_date("Montag", START).isoformat() == "2026-09-07"
    assert parse_time("7 Uhr") == time(7, 0)
    assert parse_time("18:30 uhr") == time(18, 30)


def test_parse_errors_are_localized() -> None:
    with pytest.raises(ParseError) as info:
        parse_date("irgendwann", START)
    assert str(info.value) == "'irgendwann' is not a valid date, use YYYY-MM-DD"
    assert info.value.localized("de") == (
        "'irgendwann' ist kein gültiges Datum, verwende JJJJ-MM-TT"
    )
    with pytest.raises(ParseError) as info:
        parse_weekdays("gestern")
    assert info.value.localized("de") == "'gestern' ist kein Wochentag"


# -------------------------------------------------------------------- intents


async def test_set_repeating_german(hass: HomeAssistant, ready, satellites) -> None:
    response = await handle(
        hass,
        INTENT_SET,
        satellites["kitchen"]["device_id"],
        time="07:00",
        weekdays="wochentags",
        name="Arbeit",
    )
    assert response.response_type == intent.IntentResponseType.ACTION_DONE
    assert speech(response) == (
        "Erstellt: wiederkehrender Wecker 'Arbeit' um 07:00 wochentags auf Voice PE Kitchen, "
        "nächstes Mal morgen (Dienstag, 8. September) um 07:00 (in 21 Stunden)."
    )
    assert response.speech_slots["repeats"] == "wochentags"


async def test_set_reminder_german(hass: HomeAssistant, ready, satellites) -> None:
    response = await handle(
        hass,
        INTENT_SET,
        satellites["kitchen"]["device_id"],
        time="17:00",
        message="Mama anrufen",
    )
    assert speech(response) == (
        "Erstellt: einmalige Erinnerung 'Mama anrufen' um 17:00 am Montag, 7. September auf "
        "Voice PE Kitchen, nächstes Mal heute um 17:00 (in 7 Stunden)."
    )
    assert response.speech_slots["repeats"] == "einmalig"


async def test_list_day_german(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["device_id"]
    await handle(hass, INTENT_SET, kitchen, time="07:00", weekdays="wochentags", name="Arbeit")
    await handle(hass, INTENT_SET, kitchen, time="07:10", weekdays="wochentags")
    response = await handle(hass, INTENT_LIST, kitchen, date="morgen")
    assert speech(response) == (
        "Morgen (Dienstag, 8. September) hast du 2 Wecker: 07:00 (Arbeit) und 07:10."
    )
    response = await handle(hass, INTENT_LIST, kitchen, date="sonntag")
    assert speech(response).startswith(
        "Am Sonntag, 13. September gibt es keine Wecker oder Erinnerungen. Als Nächstes: "
        "wiederkehrender Wecker 'Arbeit' um 07:00 wochentags auf Voice PE Kitchen"
    )
    response = await handle(hass, INTENT_LIST, kitchen)
    assert speech(response).startswith("Du hast 2 Wecker: 1. wiederkehrender Wecker 'Arbeit'")


async def test_skip_and_update_german(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["device_id"]
    await handle(hass, INTENT_SET, kitchen, time="07:00", weekdays="wochentags", name="Arbeit")
    response = await handle(hass, INTENT_SKIP_NEXT, kitchen, name="Arbeit")
    assert speech(response) == (
        "Wecker 'Arbeit' auf Voice PE Kitchen morgen (Dienstag, 8. September) um 07:00 wird "
        "übersprungen. Er klingelt als Nächstes am Mittwoch, 9. September um 07:00 "
        "(in 1 Tag und 21 Stunden)."
    )
    response = await handle(hass, INTENT_SKIP_NEXT, kitchen, name="Arbeit")
    assert response.response_type == intent.IntentResponseType.ERROR
    assert speech(response) == (
        "Der Wecker 'Arbeit' auf Voice PE Kitchen morgen (Dienstag, 8. September) um 07:00 "
        "ist bereits übersprungen; er klingelt als Nächstes am Mittwoch, 9. September um "
        "07:00 (in 1 Tag und 21 Stunden)."
    )
    response = await handle(hass, INTENT_SKIP_NEXT, kitchen, name="Arbeit", undo=True)
    assert speech(response) == (
        "Wecker 'Arbeit' auf Voice PE Kitchen morgen (Dienstag, 8. September) um 07:00 "
        "wiederhergestellt; er klingelt als Nächstes morgen (Dienstag, 8. September) um "
        "07:00 (in 21 Stunden)."
    )
    response = await handle(
        hass, INTENT_UPDATE, kitchen, name="Arbeit", new_time="06:45", new_weekdays="mo, mi"
    )
    assert speech(response) == (
        "Geändert: Uhrzeit auf 06:45 und Wiederholung auf jeden Montag und Mittwoch. Jetzt: "
        "wiederkehrender Wecker 'Arbeit' um 06:45 jeden Montag und Mittwoch auf Voice PE "
        "Kitchen, nächstes Mal am Mittwoch, 9. September um 06:45 (in 1 Tag und 20 Stunden)."
    )


async def test_errors_german(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["device_id"]
    response = await handle(hass, INTENT_DELETE, kitchen)
    assert response.response_type == intent.IntentResponseType.ERROR
    assert speech(response) == "Es sind keine Wecker oder Erinnerungen eingerichtet."
    response = await handle(hass, INTENT_DISMISS, kitchen)
    assert speech(response) == "Gerade klingelt nichts."
    response = await handle(hass, INTENT_SET, kitchen, time="abc")
    assert speech(response) == (
        "'abc' ist keine gültige Uhrzeit, verwende HH:MM (24-Stunden-Format)"
    )
    response = await handle(hass, INTENT_SET, kitchen, time="09:00", date="heute")
    assert speech(response) == "Dieser Zeitpunkt liegt bereits in der Vergangenheit"
    response = await handle(hass, INTENT_SET, kitchen, time="09:00", target="Garage")
    assert speech(response) == (
        "Ich kenne keinen Sprachsatelliten namens 'Garage'. Verfügbare Satelliten: "
        "Voice PE Bedroom und Voice PE Kitchen."
    )


async def test_unknown_language_falls_back_to_english(
    hass: HomeAssistant, ready, satellites
) -> None:
    response = await handle(
        hass, INTENT_SET, satellites["kitchen"]["device_id"], language="fr", time="07:00"
    )
    assert speech(response).startswith("Created one-time alarm 'Alarm 07:00' at 07:00")


# ----------------------------------------------------------- instance language


async def test_instance_language_follows_core_config(hass: HomeAssistant, ready) -> None:
    assert default_language() == "en"
    assert Alarm(target="assist_satellite.x", time=time(7, 0)).label == "Alarm 07:00"
    await hass.config.async_update(language="de")
    await hass.async_block_till_done()
    assert default_language() == "de"
    assert Alarm(target="assist_satellite.x", time=time(7, 0)).label == "Wecker 07:00"
    assert Alarm(target="assist_satellite.x", time=time(7, 0), kind=KIND_REMINDER).label == (
        "Erinnerung 07:00"
    )
    with pytest.raises(AlarmError) as info:
        await ready.async_delete_alarm("nope")
    assert str(info.value) == "No alarm with id nope"
    assert info.value.localized("de") == "Kein Wecker mit der ID nope"
    await hass.config.async_update(language="en")
    await hass.async_block_till_done()
    assert default_language() == "en"


async def test_reminder_spoken_in_german(
    hass: HomeAssistant, ready, satellites, announce_calls
) -> None:
    set_default_language("de")
    target = ready.target(satellites["kitchen"]["satellite"])
    session = await ready.async_ring(
        target, kind=KIND_REMINDER, message="Müll rausbringen", label="Test", origin="test"
    )
    for _ in range(10):
        if announce_calls:
            break
        await asyncio.sleep(0)
    assert announce_calls[0].data["message"] == "Erinnerung: Müll rausbringen"
    session.dismiss()
    await session.wait_finished()


async def test_snoozed_name_in_german(
    hass: HomeAssistant, ready, satellites, announce_calls
) -> None:
    set_default_language("de")
    target = ready.target(satellites["kitchen"]["satellite"])
    session = await ready.async_ring(target, label="Nickerchen", duration=5, origin="test")
    snoozed = await ready.async_snooze(session, 5)
    await session.wait_finished()
    assert snoozed.name == "Nickerchen (Schlummern)"


async def test_service_error_in_instance_language(hass: HomeAssistant, ready) -> None:
    from homeassistant.exceptions import ServiceValidationError

    set_default_language("de")
    with pytest.raises(ServiceValidationError) as info:
        await hass.services.async_call(
            "voice_alarms", "delete_alarm", {"alarm_id": "nope"}, blocking=True
        )
    assert str(info.value) == "Kein Wecker mit der ID nope"
