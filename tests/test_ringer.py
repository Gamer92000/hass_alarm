"""Tests for device-side stop handling and volume control."""

from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.voice_alarms.const import (
    CONF_ALARM_VOLUME,
    CONF_DEVICE_STOP_PAUSE,
    DOMAIN,
    KIND_REMINDER,
)
from custom_components.voice_alarms.ringer import RingSession
from homeassistant.components.assist_satellite import DOMAIN as SAT_DOMAIN
from homeassistant.core import HomeAssistant, ServiceCall


@pytest.fixture(autouse=True)
def fast_device_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("custom_components.voice_alarms.ringer.MIN_PLAYBACK_FOR_DEVICE_STOP", 0.05)
    monkeypatch.setattr("custom_components.voice_alarms.ringer.ANNOUNCE_RETRY_SECONDS", 0.05)


def _device_that_stops(hass: HomeAssistant, client, chunks_before_stop: int) -> SimpleNamespace:
    """Fake satellite that plays a few chunks, then stops (button / stop word)."""
    state = SimpleNamespace(calls=0)

    async def announce(call: ServiceCall) -> None:
        state.calls += 1
        match = re.search(r"(/api/voice_alarms/stream/[^/]+\.flac)", call.data["media_id"])
        async with client.get(match.group(1)) as resp:
            count = 0
            async for _chunk in resp.content.iter_chunked(4096):
                count += 1
                if count >= chunks_before_stop:
                    break
        await asyncio.sleep(0.1)

    hass.services.async_register(SAT_DOMAIN, "announce", announce)
    return state


async def test_device_stop_dismisses(
    hass: HomeAssistant, satellites, manager, hass_client_no_auth: ClientSessionGenerator
) -> None:
    client = await hass_client_no_auth()
    device = _device_that_stops(hass, client, 3)
    target = manager.target(satellites["kitchen"]["satellite"])
    session = await manager.async_ring(target, label="Stop me", duration=120)
    await asyncio.wait_for(session.wait_finished(), 10)
    assert device.calls == 1
    assert session.dismissed_by == "device"
    assert not session.active


async def test_device_stop_pause_then_resume(
    hass: HomeAssistant, satellites, hass_client_no_auth: ClientSessionGenerator
) -> None:
    """With a pause configured, the alarm resumes after the pause unless dismissed."""
    from custom_components.voice_alarms import get_manager  # noqa: PLC0415
    from homeassistant.setup import async_setup_component  # noqa: PLC0415

    entry = MockConfigEntry(
        domain=DOMAIN, data={}, options={CONF_DEVICE_STOP_PAUSE: 1}, unique_id=DOMAIN
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    manager = get_manager(hass)
    client = await hass_client_no_auth()
    device = _device_that_stops(hass, client, 3)
    target = manager.target(satellites["kitchen"]["satellite"])
    session = await manager.async_ring(target, label="Pause me", duration=120)

    async def wait_state(state: str) -> None:
        for _ in range(200):
            if session.state == state:
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"session never reached {state}, is {session.state}")

    await wait_state("paused")
    assert device.calls == 1
    assert hass.states.get("binary_sensor.voice_alarms_voice_pe_kitchen_ringing").state == "on"
    # resumes and the device stops it again
    await wait_state("ringing")
    await asyncio.sleep(0.3)
    assert device.calls >= 2
    await wait_state("paused")
    session.dismiss()
    await asyncio.wait_for(session.wait_finished(), 10)
    assert session.dismissed_by == "user"


def _satellite_in_dnd(hass: HomeAssistant, client, player: str, chunks_before_stop: int):
    """Fake satellite in do not disturb: announcements end at once, play_media plays."""
    state = SimpleNamespace(announces=0, plays=[], stops=0, tasks=[])
    hass.states.async_set(player, "idle", {"supported_features": 4 | 512, "volume_level": 0.4})

    async def announce(call: ServiceCall) -> None:
        state.announces += 1

    async def fetch(url: str) -> None:
        match = re.search(r"(/api/voice_alarms/stream/[^/]+\.flac)", url)
        async with client.get(match.group(1)) as resp:
            count = 0
            async for _chunk in resp.content.iter_chunked(4096):
                count += 1
                if count >= chunks_before_stop:
                    break
        await asyncio.sleep(0.1)
        hass.states.async_set(player, "idle", {"supported_features": 4 | 512})

    async def play_media(call: ServiceCall) -> None:
        state.plays.append(call.data)
        hass.states.async_set(player, "playing", {"supported_features": 4 | 512})
        state.tasks.append(hass.async_create_task(fetch(call.data["media_content_id"])))

    async def media_stop(call: ServiceCall) -> None:
        state.stops += 1

    hass.services.async_register(SAT_DOMAIN, "announce", announce)
    hass.services.async_register("media_player", "play_media", play_media)
    hass.services.async_register("media_player", "media_stop", media_stop)
    return state


async def test_do_not_disturb_rings_through_media_player(
    hass: HomeAssistant, satellites, manager, hass_client_no_auth: ClientSessionGenerator
) -> None:
    client = await hass_client_no_auth()
    player = satellites["kitchen"]["media_player"]
    device = _satellite_in_dnd(hass, client, player, 3)
    target = manager.target(satellites["kitchen"]["satellite"])
    session = await manager.async_ring(target, label="Wake up", duration=120)
    await asyncio.wait_for(session.wait_finished(), 10)
    assert device.announces == 1
    assert len(device.plays) == 1
    assert device.plays[0]["entity_id"] == player
    assert "/api/voice_alarms/stream/" in device.plays[0]["media_content_id"]
    assert session.dismissed_by == "device"


async def test_do_not_disturb_dismiss_stops_player(
    hass: HomeAssistant, satellites, manager, hass_client_no_auth: ClientSessionGenerator
) -> None:
    client = await hass_client_no_auth()
    device = _satellite_in_dnd(hass, client, satellites["kitchen"]["media_player"], 10**6)
    target = manager.target(satellites["kitchen"]["satellite"])
    session = await manager.async_ring(target, label="Wake up", duration=120)
    for _ in range(100):
        if device.plays:
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.3)
    session.dismiss()
    await asyncio.wait_for(session.wait_finished(), 10)
    await asyncio.wait_for(asyncio.gather(*device.tasks), 10)
    assert session.dismissed_by == "user"
    assert device.stops == 1


async def test_do_not_disturb_speaks_reminder_through_media_player(
    hass: HomeAssistant, satellites, manager, monkeypatch: pytest.MonkeyPatch
) -> None:
    player = satellites["kitchen"]["media_player"]
    hass.states.async_set(player, "idle", {"supported_features": 4 | 512})
    announces: list[ServiceCall] = []
    plays: list[ServiceCall] = []
    spoken: list[str] = []

    async def announce(call: ServiceCall) -> None:
        announces.append(call)

    async def play_media(call: ServiceCall) -> None:
        plays.append(call)
        hass.states.async_set(player, "playing", {"supported_features": 4 | 512})
        hass.loop.call_later(
            0.1, hass.states.async_set, player, "idle", {"supported_features": 4 | 512}
        )

    async def speech_url(self, text: str) -> str:
        spoken.append(text)
        return "/api/tts_proxy/reminder.mp3"

    hass.services.async_register(SAT_DOMAIN, "announce", announce)
    hass.services.async_register("media_player", "play_media", play_media)
    monkeypatch.setattr(RingSession, "_speech_url", speech_url)
    target = manager.target(satellites["kitchen"]["satellite"])
    session = await manager.async_ring(
        target, kind=KIND_REMINDER, message="Take out the trash", label="Trash", origin="test"
    )
    for _ in range(100):
        if plays and hass.states.get(player).state == "idle":
            break
        await asyncio.sleep(0.05)
    session.dismiss()
    await session.wait_finished()
    assert len(announces) == 1
    assert spoken == ["Reminder: Take out the trash"]
    assert len(plays) == 1
    assert plays[0].data["entity_id"] == player
    assert plays[0].data["media_content_id"].endswith("/api/tts_proxy/reminder.mp3")


async def test_volume_set_and_restored(
    hass: HomeAssistant, satellites, hass_client_no_auth
) -> None:
    from custom_components.voice_alarms import get_manager  # noqa: PLC0415
    from homeassistant.setup import async_setup_component  # noqa: PLC0415

    entry = MockConfigEntry(
        domain=DOMAIN, data={}, options={CONF_ALARM_VOLUME: 80}, unique_id=DOMAIN
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    manager = get_manager(hass)

    volume_calls: list[ServiceCall] = []

    async def volume_set(call: ServiceCall) -> None:
        volume_calls.append(call)

    hass.services.async_register("media_player", "volume_set", volume_set)
    release = asyncio.Event()

    async def announce(call: ServiceCall) -> None:
        await release.wait()

    hass.services.async_register(SAT_DOMAIN, "announce", announce)
    target = manager.target(satellites["kitchen"]["satellite"])
    session = await manager.async_ring(target, label="Loud", duration=60)
    await asyncio.sleep(0)
    await hass.async_block_till_done()
    assert len(volume_calls) == 1
    assert volume_calls[0].data == {
        "entity_id": satellites["kitchen"]["media_player"],
        "volume_level": 0.8,
    }
    session.dismiss()
    release.set()
    await session.wait_finished()
    assert len(volume_calls) == 2
    assert volume_calls[1].data["volume_level"] == 0.4  # restored
