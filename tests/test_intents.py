"""Tests for the voice intents / LLM tools."""

from __future__ import annotations

import asyncio
from datetime import datetime, time
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
)
from homeassistant.components.assist_satellite import DOMAIN as SAT_DOMAIN
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import intent
from homeassistant.util import dt as dt_util

from .conftest import slot

TZ = ZoneInfo("Europe/Zurich")
START = datetime(2026, 9, 7, 10, 0, tzinfo=TZ)  # Monday


@pytest.fixture
async def ready(hass: HomeAssistant, freezer: FrozenDateTimeFactory, setup_integration, manager):
    await hass.config.async_set_time_zone("Europe/Zurich")
    freezer.move_to(START)
    return manager


async def handle(hass: HomeAssistant, intent_type: str, device_id: str | None = None, **slots):
    return await intent.async_handle(
        hass,
        "test",
        intent_type,
        {k: slot(v) for k, v in slots.items()},
        device_id=device_id,
        language="en",
    )


def speech(response: intent.IntentResponse) -> str:
    return response.speech["plain"]["speech"]


async def test_set_defaults_to_speaking_satellite(hass: HomeAssistant, ready, satellites) -> None:
    response = await handle(
        hass,
        INTENT_SET,
        satellites["kitchen"]["device_id"],
        time="07:00",
        weekdays="weekdays",
        name="work",
    )
    assert response.response_type == intent.IntentResponseType.ACTION_DONE
    text = speech(response)
    assert text.startswith("Created repeating alarm 'work' at 07:00 weekdays on Voice PE Kitchen")
    assert "tomorrow (Tuesday 8 September) at 07:00" in text
    assert "in 21 hours" in text
    alarm = ready.get_alarm(response.speech_slots["alarm_id"])
    assert alarm.target == satellites["kitchen"]["satellite"]
    assert alarm.weekdays == [0, 1, 2, 3, 4]


async def test_set_with_named_target_and_date(hass: HomeAssistant, ready, satellites) -> None:
    response = await handle(
        hass,
        INTENT_SET,
        satellites["kitchen"]["device_id"],
        time="6:30",
        date="friday",
        target="bedroom",
    )
    assert response.response_type == intent.IntentResponseType.ACTION_DONE
    alarm = ready.get_alarm(response.speech_slots["alarm_id"])
    assert alarm.target == satellites["bedroom"]["satellite"]
    assert alarm.date.isoformat() == "2026-09-11"
    assert (
        "one-time alarm 'Alarm 06:30' at 06:30 on Friday 11 September on Voice PE Bedroom"
        in speech(response)
    )


async def test_set_reminder(hass: HomeAssistant, ready, satellites) -> None:
    response = await handle(
        hass, INTENT_SET, satellites["kitchen"]["device_id"], time="17:00", message="call mom"
    )
    alarm = ready.get_alarm(response.speech_slots["alarm_id"])
    assert alarm.is_reminder
    assert (
        "one-time reminder 'call mom' at 17:00 on Monday 7 September on Voice PE Kitchen, next today at 17:00"
        in speech(response)
    )


async def test_set_without_context_needs_target(hass: HomeAssistant, ready, satellites) -> None:
    response = await handle(hass, INTENT_SET, None, time="07:00")
    assert response.response_type == intent.IntentResponseType.ERROR
    assert "name the target satellite" in speech(response)
    assert "Voice PE Bedroom" in speech(response)

    response = await handle(hass, INTENT_SET, None, time="07:00", target="garage")
    assert response.response_type == intent.IntentResponseType.ERROR
    assert "don't know a voice satellite called 'garage'" in speech(response)

    response = await handle(hass, INTENT_SET, None, time="25:00", target="kitchen")
    assert response.response_type == intent.IntentResponseType.ERROR
    assert "not a valid time" in speech(response)


async def test_set_past_time_today_rolls_to_tomorrow(
    hass: HomeAssistant, ready, satellites
) -> None:
    response = await handle(hass, INTENT_SET, satellites["kitchen"]["device_id"], time="09:00")
    assert "tomorrow (Tuesday 8 September) at 09:00" in speech(response)
    response = await handle(
        hass, INTENT_SET, satellites["kitchen"]["device_id"], time="09:00", date="today"
    )
    assert response.response_type == intent.IntentResponseType.ERROR
    assert "already in the past" in speech(response)


async def test_list_delete_and_ambiguity(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["device_id"]
    bedroom = satellites["bedroom"]["device_id"]
    response = await handle(hass, INTENT_LIST, kitchen)
    assert speech(response) == "There are no alarms or reminders configured."

    await handle(hass, INTENT_SET, kitchen, time="07:00", weekdays="weekdays", name="work")
    await handle(hass, INTENT_SET, bedroom, time="07:00", weekdays="weekdays", name="work")
    await handle(hass, INTENT_SET, kitchen, time="12:00", name="lunch")

    response = await handle(hass, INTENT_LIST, kitchen)
    text = speech(response)
    assert text.startswith("You have 3 alarms: 1. ")
    assert "[id " in text
    assert response.speech_slots["count"] == 3

    response = await handle(hass, INTENT_LIST, kitchen, target="bedroom")
    assert "You have 1 alarm on Voice PE Bedroom" in speech(response)

    # 'work' matches two, but the speaking satellite disambiguates
    response = await handle(hass, INTENT_DELETE, kitchen, name="work")
    assert response.response_type == intent.IntentResponseType.ACTION_DONE
    assert (
        speech(response) == "Deleted repeating alarm 'work' at 07:00 weekdays on Voice PE Kitchen."
    )
    assert len(ready.alarms) == 2

    # without context and two candidates -> ask
    await handle(hass, INTENT_SET, kitchen, time="07:00", weekdays="weekdays", name="work")
    response = await handle(hass, INTENT_DELETE, None, name="work")
    assert response.response_type == intent.IntentResponseType.ERROR
    assert "2 alarms match" in speech(response)

    response = await handle(hass, INTENT_DELETE, None, name="work", all=True)
    assert response.response_type == intent.IntentResponseType.ACTION_DONE
    assert len(ready.alarms) == 1

    response = await handle(hass, INTENT_DELETE, None, time="12:00")
    assert (
        speech(response)
        == "Deleted one-time alarm 'lunch' at 12:00 on Monday 7 September on Voice PE Kitchen."
    )
    assert ready.alarms == {}

    response = await handle(hass, INTENT_DELETE, None, name="whatever")
    assert response.response_type == intent.IntentResponseType.ERROR


async def test_skip_next(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["device_id"]
    await handle(hass, INTENT_SET, kitchen, time="07:00", weekdays="daily", name="work")
    response = await handle(hass, INTENT_SKIP_NEXT, kitchen, name="work")
    assert speech(response) == (
        "Skipping the alarm 'work' on Voice PE Kitchen tomorrow (Tuesday 8 September) at 07:00. "
        "It rings next on Wednesday 9 September at 07:00 (in 1 day and 21 hours)."
    )
    response = await handle(hass, INTENT_SKIP_NEXT, kitchen, name="work")
    assert response.response_type == intent.IntentResponseType.ERROR
    assert "already skipped" in speech(response)
    response = await handle(hass, INTENT_SKIP_NEXT, kitchen, name="work", undo=True)
    assert speech(response).startswith("Reinstated the alarm 'work' on Voice PE Kitchen tomorrow")

    await handle(hass, INTENT_SET, kitchen, time="12:00", name="lunch")
    response = await handle(hass, INTENT_SKIP_NEXT, kitchen, name="lunch")
    assert response.response_type == intent.IntentResponseType.ERROR


async def test_update(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["device_id"]
    response = await handle(
        hass, INTENT_SET, kitchen, time="07:00", weekdays="weekdays", name="work"
    )
    alarm_id = response.speech_slots["alarm_id"]
    response = await handle(
        hass,
        INTENT_UPDATE,
        kitchen,
        alarm_id=alarm_id,
        new_time="06:45",
        new_target="bedroom",
        enabled=False,
    )
    assert response.response_type == intent.IntentResponseType.ACTION_DONE
    text = speech(response)
    assert text.startswith("Changed time to 06:45, satellite to Voice PE Bedroom and disabled it.")
    assert "(disabled)" in text
    alarm = ready.get_alarm(alarm_id)
    assert alarm.time == time(6, 45)
    assert alarm.target == satellites["bedroom"]["satellite"]
    assert alarm.enabled is False

    response = await handle(hass, INTENT_UPDATE, kitchen, alarm_id=alarm_id)
    assert response.response_type == intent.IntentResponseType.ERROR

    response = await handle(
        hass,
        INTENT_UPDATE,
        kitchen,
        alarm_id=alarm_id,
        new_weekdays="none",
        new_date="friday",
        enabled=True,
    )
    assert response.response_type == intent.IntentResponseType.ACTION_DONE
    alarm = ready.get_alarm(alarm_id)
    assert not alarm.is_recurring
    assert alarm.date.isoformat() == "2026-09-11"


async def test_dismiss(hass: HomeAssistant, ready, satellites) -> None:
    kitchen_dev = satellites["kitchen"]["device_id"]
    kitchen = satellites["kitchen"]["satellite"]
    response = await handle(hass, INTENT_DISMISS, kitchen_dev)
    assert response.response_type == intent.IntentResponseType.ERROR
    assert speech(response) == "Nothing is ringing right now."

    release = asyncio.Event()
    calls: list[ServiceCall] = []

    async def announce(call: ServiceCall) -> None:
        calls.append(call)
        await release.wait()

    hass.services.async_register(SAT_DOMAIN, "announce", announce)
    target = ready.target(kitchen)
    session = await ready.async_ring(target, label="Work", duration=60)
    await asyncio.sleep(0)

    response = await handle(hass, INTENT_LIST, kitchen_dev)
    assert "Currently ringing: the alarm 'Work' on Voice PE Kitchen." in speech(response)

    response = await handle(
        hass, INTENT_DISMISS, satellites["bedroom"]["device_id"], target="bedroom"
    )
    assert response.response_type == intent.IntentResponseType.ERROR
    assert speech(response) == "Nothing is ringing on Voice PE Bedroom."

    # speaking from the bedroom with nothing ringing there stops whatever rings elsewhere
    response = await handle(hass, INTENT_DISMISS, satellites["bedroom"]["device_id"])
    assert speech(response) == "Stopped the alarm 'Work' on Voice PE Kitchen."
    release.set()
    await session.wait_finished()
    assert session.dismissed_by == "user"

    response = await handle(hass, INTENT_DISMISS, kitchen_dev)
    assert response.response_type == intent.IntentResponseType.ERROR
    assert "was already dismissed 0 seconds ago" in speech(response)


async def test_snooze_via_dismiss(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["satellite"]
    release = asyncio.Event()

    async def announce(call: ServiceCall) -> None:
        await release.wait()

    hass.services.async_register(SAT_DOMAIN, "announce", announce)
    session = await ready.async_ring(ready.target(kitchen), label="Nap", duration=60)
    await asyncio.sleep(0)
    response = await handle(
        hass, INTENT_DISMISS, satellites["kitchen"]["device_id"], snooze_minutes=10
    )
    assert (
        speech(response)
        == "Snoozed the alarm 'Nap' on Voice PE Kitchen, rings again at 10:10 (in 10 minutes)."
    )
    release.set()
    await session.wait_finished()
    assert len(ready.alarms) == 1
    snoozed = next(iter(ready.alarms.values()))
    assert snoozed.next_pending(dt_util.utcnow()) == START.replace(minute=10)
