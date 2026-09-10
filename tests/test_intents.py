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
    assert "[id " not in text
    assert response.speech_slots["count"] == 3
    first = response.speech_slots["alarms"][0]
    assert set(first) == {
        "alarm_id",
        "label",
        "kind",
        "target",
        "time",
        "repeats",
        "date",
        "next",
        "enabled",
    }
    assert first["alarm_id"] in ready.alarms

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


async def test_skip_whole_wakeup(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["device_id"]
    bedroom = satellites["bedroom"]["device_id"]
    for at in ("08:45", "08:50", "09:00"):
        await handle(hass, INTENT_SET, bedroom, time=at, weekdays="weekdays")
    await handle(hass, INTENT_SET, bedroom, time="10:00", weekdays="sat", name="brunch")
    await handle(hass, INTENT_SET, kitchen, time="07:00", weekdays="daily", name="work")

    def skipped(name: str):
        alarm = next(a for a in ready.alarms.values() if a.label == name)
        return alarm.skipped_occurrence

    # "don't wake me tomorrow" from the bedroom: the whole wake-up there, nothing else
    response = await handle(hass, INTENT_SKIP_NEXT, bedroom)
    assert speech(response) == (
        "Skipping 3 alarms: 08:45, 08:50 and 09:00 on Voice PE Bedroom tomorrow (Tuesday 8 "
        "September). The next ring is on Wednesday 9 September at 08:45 (in 1 day and 22 hours)."
    )
    assert len(response.speech_slots["alarm_ids"]) == 3
    assert skipped("Alarm 08:45") is not None
    assert skipped("brunch") is None
    assert skipped("work") is None

    # the day listing reflects it
    response = await handle(hass, INTENT_LIST, bedroom, date="tomorrow", target="bedroom")
    assert speech(response) == (
        "Tomorrow (Tuesday 8 September) you have 3 alarms on Voice PE Bedroom: 08:45 (skipped), "
        "08:50 (skipped) and 09:00 (skipped)."
    )

    # reinstate them by date
    response = await handle(hass, INTENT_SKIP_NEXT, bedroom, date="tomorrow", undo=True)
    assert speech(response) == (
        "Reinstated 3 alarms: 08:45, 08:50 and 09:00 on Voice PE Bedroom tomorrow (Tuesday 8 "
        "September). The next ring is tomorrow (Tuesday 8 September) at 08:45 "
        "(in 22 hours and 45 minutes)."
    )
    assert skipped("Alarm 08:45") is None

    # only the very next ring can be skipped
    response = await handle(hass, INTENT_SKIP_NEXT, bedroom, date="wednesday")
    assert response.response_type == intent.IntentResponseType.ERROR
    assert speech(response).startswith(
        "I can only skip the very next ring: 'work' rings next tomorrow (Tuesday 8 September) "
        "at 07:00, 'Alarm 08:45' rings next tomorrow"
    )

    # a time picks exactly one
    response = await handle(hass, INTENT_SKIP_NEXT, bedroom, time="08:50")
    assert speech(response).startswith(
        "Skipping the alarm 'Alarm 08:50' on Voice PE Bedroom tomorrow"
    )

    # from the kitchen with no filter only one alarm is there, so it is picked as before
    response = await handle(hass, INTENT_SKIP_NEXT, kitchen)
    assert speech(response).startswith("Skipping the alarm 'work' on Voice PE Kitchen tomorrow")

    # all=true with a target skips everything there, grouped by day
    response = await handle(hass, INTENT_SKIP_NEXT, kitchen, target="bedroom", all=True)
    assert speech(response) == (
        "Skipping 4 alarms: 08:45, 08:50 and 09:00 on Voice PE Bedroom tomorrow (Tuesday 8 "
        "September); 10:00 (brunch) on Voice PE Bedroom on Saturday 12 September. The next "
        "ring is on Wednesday 9 September at 08:45 (in 1 day and 22 hours)."
    )
    assert skipped("brunch") is not None

    # nothing left to reinstate on a day
    await handle(hass, INTENT_SKIP_NEXT, kitchen, target="bedroom", all=True, undo=True)
    response = await handle(hass, INTENT_SKIP_NEXT, kitchen, target="bedroom", all=True, undo=True)
    assert response.response_type == intent.IntentResponseType.ERROR
    assert "has a skipped occurrence" in speech(response)


async def test_update_all_and_date_filter(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["device_id"]
    await handle(hass, INTENT_SET, kitchen, time="07:00", weekdays="weekdays", name="work")
    await handle(hass, INTENT_SET, kitchen, time="07:15", weekdays="weekdays", name="gym")
    await handle(hass, INTENT_SET, kitchen, time="10:00", weekdays="sat", name="brunch")

    # without all=true and without a filter it still asks
    response = await handle(hass, INTENT_UPDATE, kitchen, enabled=False)
    assert response.response_type == intent.IntentResponseType.ERROR

    response = await handle(hass, INTENT_UPDATE, kitchen, enabled=False, all=True)
    text = speech(response)
    assert text.startswith("Changed disabled it for 3 alarms. They are now: ")
    assert text.count("(disabled)") == 3
    assert response.speech_slots["next"] is None
    assert len(response.speech_slots["alarm_ids"]) == 3
    assert all(not a.enabled for a in ready.alarms.values())

    # the date filter finds repeating alarms that ring that day
    response = await handle(hass, INTENT_UPDATE, kitchen, date="tomorrow", enabled=True, all=True)
    assert speech(response).startswith("Changed enabled it for 2 alarms.")
    assert [a.label for a in ready.alarms.values() if a.enabled] == ["work", "gym"]

    response = await handle(hass, INTENT_DELETE, kitchen, date="saturday")
    assert speech(response).startswith("Deleted repeating alarm 'brunch' at 10:00 every Saturday")
    response = await handle(hass, INTENT_DELETE, kitchen, date="sunday")
    assert response.response_type == intent.IntentResponseType.ERROR
    assert speech(response).startswith("No alarm matches.")


async def test_set_rejects_date_with_weekdays(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["device_id"]
    response = await handle(
        hass, INTENT_SET, kitchen, time="07:00", weekdays="weekdays", date="tomorrow"
    )
    assert response.response_type == intent.IntentResponseType.ERROR
    assert "not both" in speech(response)
    assert not ready.alarms


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


async def test_list_for_a_day(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["device_id"]
    bedroom = satellites["bedroom"]["device_id"]

    response = await handle(hass, INTENT_LIST, bedroom, date="tomorrow")
    assert speech(response) == "There are no alarms or reminders tomorrow (Tuesday 8 September)."
    assert response.speech_slots == {"date": "2026-09-08", "count": 0, "alarms": []}

    for at in ("09:00", "08:45", "08:50"):
        await handle(hass, INTENT_SET, bedroom, time=at, weekdays="weekdays")

    # asked from the satellite that rings: just the times
    response = await handle(hass, INTENT_LIST, bedroom, date="tomorrow")
    assert (
        speech(response)
        == "Tomorrow (Tuesday 8 September) you have 3 alarms: 08:45, 08:50 and 09:00."
    )
    slots = response.speech_slots
    assert slots["date"] == "2026-09-08"
    assert slots["count"] == 3
    assert [a["rings_at"] for a in slots["alarms"]] == [
        "2026-09-08T08:45:00+02:00",
        "2026-09-08T08:50:00+02:00",
        "2026-09-08T09:00:00+02:00",
    ]
    assert slots["alarms"][0]["target"] == satellites["bedroom"]["satellite"]
    assert slots["alarms"][0]["skipped"] is False

    # asked from another satellite (or without one): the satellite is named
    response = await handle(hass, INTENT_LIST, kitchen, date="tomorrow")
    assert speech(response) == (
        "Tomorrow (Tuesday 8 September) you have 3 alarms: 08:45, 08:50 and 09:00 "
        "on Voice PE Bedroom."
    )
    response = await handle(hass, INTENT_LIST, None, date="2026-09-08")
    assert "09:00 on Voice PE Bedroom." in speech(response)

    # explicitly asked about that satellite: scope in the sentence, not per group
    response = await handle(hass, INTENT_LIST, kitchen, date="tuesday", target="bedroom")
    assert speech(response) == (
        "Tomorrow (Tuesday 8 September) you have 3 alarms on Voice PE Bedroom: 08:45, 08:50 "
        "and 09:00."
    )

    # several satellites: grouped per satellite (ordered by first ring), each named;
    # reminders and names are spelled out
    await handle(hass, INTENT_SET, kitchen, time="17:00", message="call mom", date="tomorrow")
    await handle(hass, INTENT_SET, kitchen, time="07:00", name="gym", date="tomorrow")
    response = await handle(hass, INTENT_LIST, bedroom, date="tomorrow")
    assert speech(response) == (
        "Tomorrow (Tuesday 8 September) you have 5 alarms: 07:00 (gym) and a reminder "
        "'call mom' at 17:00 on Voice PE Kitchen; 08:45, 08:50 and 09:00 on Voice PE Bedroom."
    )

    # skipped and disabled occurrences
    await handle(hass, INTENT_SKIP_NEXT, bedroom, time="08:45")
    await handle(hass, INTENT_UPDATE, bedroom, time="09:00", enabled=False)
    response = await handle(hass, INTENT_LIST, bedroom, date="tomorrow", target="bedroom")
    assert speech(response) == (
        "Tomorrow (Tuesday 8 September) you have 2 alarms on Voice PE Bedroom: "
        "08:45 (skipped) and 08:50."
    )
    assert response.speech_slots["alarms"][0]["skipped"] is True

    # today only lists what is still ahead (it is 10:00)
    await handle(hass, INTENT_SET, kitchen, time="12:00", name="lunch")
    response = await handle(hass, INTENT_LIST, kitchen, date="today")
    assert speech(response) == "Today you have 1 alarm: 12:00 (lunch)."

    # a day without alarms points at the next one
    response = await handle(hass, INTENT_LIST, bedroom, date="saturday", target="bedroom")
    assert speech(response) == (
        "There are no alarms or reminders on Saturday 12 September on Voice PE Bedroom. "
        "The next one is the repeating alarm 'Alarm 08:50' at 08:50 weekdays on Voice PE "
        "Bedroom, next tomorrow (Tuesday 8 September) at 08:50 (in 22 hours and 50 minutes)."
    )

    response = await handle(hass, INTENT_LIST, bedroom, date="someday")
    assert response.response_type == intent.IntentResponseType.ERROR
    assert "not a valid date" in speech(response)
