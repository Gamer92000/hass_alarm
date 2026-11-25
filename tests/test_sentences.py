"""User-written custom sentences, run through Home Assistant's own agent."""

from __future__ import annotations

import shutil
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory

from custom_components.voice_alarms.const import INTENT_SET
from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import chat_session, intent
from homeassistant.setup import async_setup_component

SENTENCES = Path(__file__).parent / "custom_sentences"
TZ = ZoneInfo("America/Sao_Paulo")
START = datetime(2026, 9, 7, 10, 0, tzinfo=TZ)  # Monday


@pytest.fixture
async def ready(
    hass: HomeAssistant,
    tmp_path: Path,
    freezer: FrozenDateTimeFactory,
    setup_integration,
    manager,
):
    # The agent reads <config>/custom_sentences/<language>/, as an installation would.
    hass.config.config_dir = str(tmp_path)
    shutil.copytree(SENTENCES, tmp_path / "custom_sentences")
    assert await async_setup_component(hass, "conversation", {})
    await hass.config.async_set_time_zone("America/Sao_Paulo")
    freezer.move_to(START)
    return manager


async def handle_locally(
    hass: HomeAssistant, text: str, satellites
) -> intent.IntentResponse | None:
    """What a pipeline that prefers local intents does: None hands it to its LLM."""
    user_input = conversation.ConversationInput(
        text=text,
        context=Context(),
        conversation_id=None,
        device_id=satellites["kitchen"]["device_id"],
        satellite_id=None,
        language="en",
        agent_id=conversation.HOME_ASSISTANT_AGENT,
    )
    with (
        chat_session.async_get_chat_session(hass) as session,
        conversation.async_get_chat_log(hass, session, user_input) as chat_log,
    ):
        return await conversation.async_handle_intents(hass, user_input, chat_log)


async def test_set_alarm_is_handled_locally(hass: HomeAssistant, ready, satellites) -> None:
    response = await handle_locally(hass, "wake me up at 7:30", satellites)
    assert response is not None
    assert response.response_type == intent.IntentResponseType.ACTION_DONE, response.speech
    assert response.intent is not None
    assert response.intent.intent_type == INTENT_SET
    alarm = ready.get_alarm(response.speech_slots["alarm_id"])
    assert alarm.time == time(7, 30)


async def test_unparsable_time_goes_to_the_agent(hass: HomeAssistant, ready, satellites) -> None:
    # The sentence caught it as a time, but only the LLM can make sense of it.
    assert await handle_locally(hass, "wake me up at seven-ish", satellites) is None
    assert ready.sorted_alarms() == []


async def test_stop_is_handled_locally(hass: HomeAssistant, ready, satellites) -> None:
    target = ready.target(satellites["kitchen"]["satellite"])
    session = await ready.async_ring(target, label="Test", duration=60, origin="test")
    response = await handle_locally(hass, "stop the alarm", satellites)
    assert response is not None
    assert response.response_type == intent.IntentResponseType.ACTION_DONE, response.speech
    await session.wait_finished()
    assert session.dismissed_by == "user"


async def test_stop_with_nothing_ringing_goes_to_the_agent(
    hass: HomeAssistant, ready, satellites
) -> None:
    # "Stop the alarm" may mean disabling one, which only the LLM can tell.
    assert await handle_locally(hass, "stop the alarm", satellites) is None


async def test_stop_just_after_it_stopped_is_answered_locally(
    hass: HomeAssistant, ready, satellites
) -> None:
    # It just stopped: the LLM must not get the chance to read this as disabling it.
    target = ready.target(satellites["kitchen"]["satellite"])
    session = await ready.async_ring(target, label="Test", duration=60, origin="test")
    session.dismiss(by="device")
    await session.wait_finished()
    response = await handle_locally(hass, "stop the alarm", satellites)
    assert response is not None
    assert response.response_type == intent.IntentResponseType.ERROR
    assert response.error_code == intent.IntentResponseErrorCode.FAILED_TO_HANDLE
    assert "was stopped on the device" in response.speech["plain"]["speech"]


async def test_snooze_in_words_goes_to_the_agent(hass: HomeAssistant, ready, satellites) -> None:
    # The sentence caught 'ten' as the minutes; only the LLM can make it 10.
    target = ready.target(satellites["kitchen"]["satellite"])
    session = await ready.async_ring(target, label="Test", duration=60, origin="test")
    assert await handle_locally(hass, "snooze the alarm for ten minutes", satellites) is None
    assert ready.session_for_target(target.entity_id) is session
    response = await handle_locally(hass, "snooze the alarm for 10 minutes", satellites)
    assert response is not None
    assert response.response_type == intent.IntentResponseType.ACTION_DONE, response.speech


async def test_stop_on_a_satellite_just_after_it_stopped_is_answered_locally(
    hass: HomeAssistant, ready, satellites
) -> None:
    target = ready.target(satellites["kitchen"]["satellite"])
    session = await ready.async_ring(target, label="Test", duration=60, origin="test")
    session.dismiss(by="device")
    await session.wait_finished()
    response = await handle_locally(hass, "stop the alarm in the kitchen", satellites)
    assert response is not None
    assert response.error_code == intent.IntentResponseErrorCode.FAILED_TO_HANDLE
    assert "was stopped on the device" in response.speech["plain"]["speech"]
    # What stopped in the kitchen says nothing about the bedroom: that one is handed on.
    assert await handle_locally(hass, "stop the alarm in the bedroom", satellites) is None
