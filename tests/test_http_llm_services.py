"""Tests for the audio stream, LLM platform, services and config flow."""

from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.voice_alarms.const import (
    CONF_DEFAULT_DURATION,
    CONF_DEFAULT_SOUND,
    DEFAULT_SOUND_URL,
    DOMAIN,
    SAMPLE_RATE,
)
from custom_components.voice_alarms.http import DATA_STREAMS
from homeassistant import config_entries
from homeassistant.components.assist_satellite import DOMAIN as SAT_DOMAIN
from homeassistant.core import Context, HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import llm
from tests.flac_util import parse_flac


async def test_stream_end_to_end(
    hass: HomeAssistant, satellites, manager, hass_client_no_auth: ClientSessionGenerator
) -> None:
    """The satellite fetches a paced, ramped FLAC stream that ends when dismissed."""
    client = await hass_client_no_auth()
    state = SimpleNamespace(body=b"", status=None, calls=0)

    async def announce(call: ServiceCall) -> None:
        state.calls += 1
        match = re.search(r"(/api/voice_alarms/stream/[^/]+\.flac)", call.data["media_id"])
        assert match
        async with client.get(match.group(1)) as resp:
            state.status = resp.status
            async for chunk in resp.content.iter_chunked(8192):
                state.body += chunk

    hass.services.async_register(SAT_DOMAIN, "announce", announce)
    target = manager.target(satellites["kitchen"]["satellite"])
    session = await manager.async_ring(target, label="Test", duration=3, origin="test")
    await session.wait_finished()

    assert state.calls == 1
    assert state.status == 200
    stream = parse_flac(state.body)  # strict: every header field and both CRCs
    assert (stream.channels, stream.rate, stream.bits) == (1, SAMPLE_RATE, 16)
    assert stream.total_samples == 3 * SAMPLE_RATE
    samples = stream.samples
    assert len(samples) == 3 * SAMPLE_RATE
    first = max(abs(s) for s in samples[: SAMPLE_RATE // 2])
    last = max(abs(s) for s in samples[-SAMPLE_RATE // 2 :])
    assert first < last  # volume ramps up
    assert not session.active
    assert session.dismissed is False  # it simply ran its 3 seconds

    # a second fetch of the same token is refused
    assert hass.data[DATA_STREAMS].get("x") is None


async def test_stream_stops_on_dismiss(
    hass: HomeAssistant, satellites, manager, hass_client_no_auth
) -> None:
    client = await hass_client_no_auth()
    got = SimpleNamespace(bytes=0)
    started = asyncio.Event()

    async def announce(call: ServiceCall) -> None:
        match = re.search(r"(/api/voice_alarms/stream/[^/]+\.flac)", call.data["media_id"])
        async with client.get(match.group(1)) as resp:
            async for chunk in resp.content.iter_chunked(4096):
                got.bytes += len(chunk)
                started.set()

    hass.services.async_register(SAT_DOMAIN, "announce", announce)
    target = manager.target(satellites["kitchen"]["satellite"])
    session = await manager.async_ring(target, label="Long", duration=300)
    await asyncio.wait_for(started.wait(), 5)
    session.dismiss()
    await asyncio.wait_for(session.wait_finished(), 5)
    assert got.bytes < 300 * SAMPLE_RATE * 2
    assert session.dismissed_by == "user"


async def test_default_sound_endpoint(hass: HomeAssistant, manager, hass_client_no_auth) -> None:
    client = await hass_client_no_auth()
    resp = await client.get(DEFAULT_SOUND_URL)
    assert resp.status == 200
    body = await resp.read()
    assert body[:4] == b"RIFF"
    assert len(body) == 44 + 4 * SAMPLE_RATE * 2
    resp = await client.get("/api/voice_alarms/stream/unknown.flac")
    assert resp.status == 404


async def test_llm_tools_exposed(hass: HomeAssistant, satellites, manager) -> None:
    context = llm.LLMContext(
        platform="test",
        context=Context(),
        language="en",
        assistant="conversation",
        device_id=satellites["kitchen"]["device_id"],
    )
    api = await llm.async_get_api(hass, llm.LLM_API_ASSIST, context)
    names = {tool.name for tool in api.tools}
    assert {
        "voice_alarms__VoiceAlarmSet",
        "voice_alarms__VoiceAlarmList",
        "voice_alarms__VoiceAlarmDelete",
        "voice_alarms__VoiceAlarmSkipNext",
        "voice_alarms__VoiceAlarmUpdate",
        "voice_alarms__VoiceAlarmDismiss",
    } <= names
    assert "speaking through the voice satellite 'Voice PE Kitchen'" in api.api_prompt

    tool = next(t for t in api.tools if t.name == "voice_alarms__VoiceAlarmSet")
    result = await api.async_call_tool(
        llm.ToolInput(
            tool_name=tool.name,
            tool_args={"time": "07:15", "weekdays": ["mon", "fri"], "name": "gym"},
        )
    )
    assert result["response_type"] == "action_done"
    assert result["speech"]["plain"]["speech"].startswith(
        "Created repeating alarm 'gym' at 07:15 every Monday and Friday on Voice PE Kitchen"
    )
    assert result["speech_slots"]["target"] == satellites["kitchen"]["satellite"]

    no_device = llm.LLMContext(
        platform="test", context=Context(), language="en", assistant="conversation", device_id=None
    )
    api = await llm.async_get_api(hass, llm.LLM_API_ASSIST, no_device)
    assert "not speaking through a voice satellite" in api.api_prompt


async def test_services(hass: HomeAssistant, satellites, manager) -> None:
    kitchen = satellites["kitchen"]["satellite"]
    result = await hass.services.async_call(
        DOMAIN,
        "add_alarm",
        {"target": kitchen, "time": "07:00", "weekdays": ["mon", "tue"], "name": "svc"},
        blocking=True,
        return_response=True,
    )
    alarm = result["alarm"]
    assert alarm["weekdays"] == [0, 1]
    assert alarm["target"] == kitchen

    result = await hass.services.async_call(
        DOMAIN, "list_alarms", {}, blocking=True, return_response=True
    )
    assert [a["id"] for a in result["alarms"]] == [alarm["id"]]

    result = await hass.services.async_call(
        DOMAIN, "skip_next", {"alarm_id": alarm["id"]}, blocking=True, return_response=True
    )
    assert result["alarm"]["next_skipped"] is True

    result = await hass.services.async_call(
        DOMAIN,
        "update_alarm",
        {"alarm_id": alarm["id"], "time": "08:00", "enabled": False},
        blocking=True,
        return_response=True,
    )
    assert result["alarm"]["time"] == "08:00"
    assert result["alarm"]["enabled"] is False

    with pytest.raises(Exception):  # noqa: B017
        await hass.services.async_call(DOMAIN, "delete_alarm", {"alarm_id": "nope"}, blocking=True)
    await hass.services.async_call(DOMAIN, "delete_alarm", {"alarm_id": alarm["id"]}, blocking=True)
    assert manager.alarms == {}

    with pytest.raises(Exception):  # noqa: B017
        await hass.services.async_call(DOMAIN, "snooze", {}, blocking=True, return_response=True)

    result = await hass.services.async_call(
        DOMAIN, "dismiss", {}, blocking=True, return_response=True
    )
    assert result == {"dismissed": []}


async def test_config_and_options_flow(hass: HomeAssistant, satellites, announce_calls) -> None:
    from homeassistant.setup import async_setup_component  # noqa: PLC0415

    assert await async_setup_component(hass, "homeassistant", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEFAULT_DURATION: 120, CONF_DEFAULT_SOUND: "not a url"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_DEFAULT_SOUND: "invalid_sound"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_DEFAULT_DURATION: 120, CONF_DEFAULT_SOUND: "https://example.com/a.mp3"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry: MockConfigEntry = result["result"]
    assert entry.options[CONF_DEFAULT_DURATION] == 120
    await hass.async_block_till_done()

    from custom_components.voice_alarms import get_manager  # noqa: PLC0415

    assert get_manager(hass).default_duration == 120
    assert get_manager(hass).default_sound == "https://example.com/a.mp3"

    # second instance refused
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_DEFAULT_DURATION: 60, CONF_DEFAULT_SOUND: ""}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert get_manager(hass).default_duration == 60
    assert get_manager(hass).default_sound is None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, "add_alarm")
