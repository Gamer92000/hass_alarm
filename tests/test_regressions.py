"""Regression tests for review findings: session priority, atomic updates, renames, ..."""

from __future__ import annotations

import asyncio
import re
import struct
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.voice_alarms import get_manager
from custom_components.voice_alarms.audio import FlacWriter, flac_crc16
from custom_components.voice_alarms.const import (
    DOMAIN,
    KIND_ALARM,
    KIND_REMINDER,
    SIGNAL_TARGETS_UPDATED,
)
from custom_components.voice_alarms.http import DATA_STREAMS
from custom_components.voice_alarms.i18n import set_default_language
from custom_components.voice_alarms.manager import AlarmError
from custom_components.voice_alarms.ringer import RingSession
from homeassistant.components.assist_satellite import DOMAIN as SAT_DOMAIN
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

TZ = ZoneInfo("Europe/Zurich")
START = datetime(2026, 9, 7, 10, 0, tzinfo=TZ)  # Monday 10:00 local


@pytest.fixture
async def local_tz(hass: HomeAssistant) -> None:
    await hass.config.async_set_time_zone("Europe/Zurich")


async def _advance(hass: HomeAssistant, freezer, to: datetime) -> None:
    freezer.move_to(to)
    async_fire_time_changed(hass, to)
    await hass.async_block_till_done()


async def _until(predicate, rounds: int = 1000) -> None:
    """Let background ring tasks run until ``predicate`` holds.

    Counts event loop rounds rather than time: the frozen clock of the
    ``freezer`` fixture also stops the loop's timers.
    """
    for _ in range(rounds):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition not reached")


async def _end(session: RingSession) -> None:
    session.dismiss()
    await asyncio.wait_for(session.wait_finished(), 5)


def _spoken(calls: list[ServiceCall]) -> list[str]:
    return [c.data["message"] for c in calls if c.data.get("message")]


# ------------------------------------------------------------- session priority


async def test_alarm_interrupts_reminder_which_follows(
    hass: HomeAssistant, local_tz, freezer, satellites, manager, announce_calls
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    await manager.async_add_alarm(
        manager.build_alarm(target=kitchen, at=time(10, 2), message="Take the pills")
    )
    await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(10, 3), name="Wake"))

    await _advance(hass, freezer, START.replace(minute=2, second=1))
    reminder = manager.session_for_target(kitchen)
    assert reminder.kind == KIND_REMINDER
    await _until(lambda: len(_spoken(announce_calls)) == 1)

    await _advance(hass, freezer, START.replace(minute=3, second=1))
    alarm = manager.session_for_target(kitchen)
    assert alarm is not reminder
    assert alarm.kind == KIND_ALARM and alarm.label == "Wake"
    assert reminder.dismissed_by == "superseded"

    # Once the alarm is dismissed, the interrupted reminder is spoken again.
    await _end(alarm)
    await hass.async_block_till_done()
    again = manager.session_for_target(kitchen)
    assert again is not None and again.kind == KIND_REMINDER
    await _until(lambda: len(_spoken(announce_calls)) == 2)
    assert "Take the pills" in _spoken(announce_calls)[-1]
    await _end(again)


async def test_reminder_waits_for_ringing_alarm(
    hass: HomeAssistant, local_tz, freezer, satellites, manager, announce_calls
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(10, 2), name="Wake"))
    await manager.async_add_alarm(
        manager.build_alarm(target=kitchen, at=time(10, 3), message="Water the plants")
    )
    await _advance(hass, freezer, START.replace(minute=2, second=1))
    alarm = manager.session_for_target(kitchen)
    await _advance(hass, freezer, START.replace(minute=3, second=1))
    assert manager.session_for_target(kitchen) is alarm
    assert alarm.alarm_ids == [a.id for a in alarm.alarms] and len(alarm.alarms) == 1
    assert not _spoken(announce_calls)

    await _end(alarm)
    await hass.async_block_till_done()
    reminder = manager.session_for_target(kitchen)
    assert reminder is not None and reminder.kind == KIND_REMINDER
    await _until(lambda: bool(_spoken(announce_calls)))
    assert "Water the plants" in _spoken(announce_calls)[0]
    await _end(reminder)


async def test_alarm_interrupts_test_but_test_never_interrupts(
    hass: HomeAssistant, local_tz, freezer, satellites, manager, announce_calls
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    target = manager.target(kitchen)
    test = await manager.async_ring(target, label="Test", duration=20, origin="test")
    await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(10, 2), name="Wake"))
    await _advance(hass, freezer, START.replace(minute=2, second=1))
    alarm = manager.session_for_target(kitchen)
    assert alarm is not test and alarm.label == "Wake"
    assert test.dismissed_by == "superseded"

    assert await manager.async_ring(target, label="Test", duration=20, origin="test") is alarm
    assert not alarm.dismissed
    await _end(alarm)


async def test_joining_reminder_is_spoken(
    hass: HomeAssistant, local_tz, freezer, satellites, manager, announce_calls
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(10, 2), message="A"))
    await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(10, 3), message="B"))
    await _advance(hass, freezer, START.replace(minute=2, second=1))
    session = manager.session_for_target(kitchen)
    await _until(lambda: len(_spoken(announce_calls)) == 1)
    await _advance(hass, freezer, START.replace(minute=3, second=1))
    assert manager.session_for_target(kitchen) is session
    # The second reminder wakes the session instead of waiting out the interval.
    await _until(lambda: len(_spoken(announce_calls)) == 2)
    assert "A. B" in _spoken(announce_calls)[-1]
    await _end(session)


# ------------------------------------------------------------------- updates


async def test_failed_update_changes_nothing(
    hass: HomeAssistant, local_tz, freezer, satellites, manager
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    alarm = await manager.async_add_alarm(
        manager.build_alarm(target=kitchen, at=time(11, 0), name="X")
    )
    before = alarm.to_dict()
    with pytest.raises(AlarmError):
        await manager.async_update_alarm(alarm.id, name="Changed", target="assist_satellite.nope")
    with pytest.raises(AlarmError):
        await manager.async_update_alarm(alarm.id, date=START.date() - timedelta(days=1))
    assert alarm.to_dict() == before


async def test_update_many_is_all_or_nothing(
    hass: HomeAssistant, local_tz, freezer, satellites, manager
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    first = await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(11, 0)))
    second = await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(12, 0)))
    with pytest.raises(AlarmError):
        await manager.async_update_alarms(
            [(first.id, {"name": "ok"}), (second.id, {"duration": -5})]
        )
    assert first.name is None and second.duration is None


async def test_reenabling_expired_one_time_alarm_rolls_forward(
    hass: HomeAssistant, local_tz, freezer, satellites, manager
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    alarm = await manager.async_add_alarm(
        manager.build_alarm(target=kitchen, at=time(10, 30), enabled=False)
    )
    await _advance(hass, freezer, START.replace(hour=11))
    assert manager.get_alarm(alarm.id) is alarm  # disabled alarms do not expire
    await manager.async_update_alarm(alarm.id, name="Renamed")  # past date is fine while off

    switch = er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"alarm_{alarm.id}")
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    assert alarm.enabled
    assert alarm.next_pending(dt_util.utcnow()) == START.replace(day=8, minute=30)


async def test_switch_reports_errors_as_validation_errors(
    hass: HomeAssistant, local_tz, freezer, satellites, manager, monkeypatch
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    alarm = await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(11, 0)))
    switch = er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"alarm_{alarm.id}")

    async def fail(*_args, **_kwargs):
        raise AlarmError("err_time_past")

    monkeypatch.setattr(manager, "async_update_alarm", fail)
    with pytest.raises(ServiceValidationError, match="past"):
        await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)


async def test_switch_follows_alarm_to_other_satellite(
    hass: HomeAssistant, local_tz, freezer, satellites, manager
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    bedroom = satellites["bedroom"]["satellite"]
    alarm = await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(11, 0)))
    await manager.async_update_alarm(alarm.id, target=bedroom)
    await hass.async_block_till_done()
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(ent_reg.async_get_entity_id("switch", DOMAIN, f"alarm_{alarm.id}"))
    device = dr.async_get(hass).async_get(entry.device_id)
    assert (DOMAIN, bedroom) in device.identifiers


async def test_duration_can_be_reset(hass: HomeAssistant, satellites, manager) -> None:
    kitchen = satellites["kitchen"]["satellite"]
    result = await hass.services.async_call(
        DOMAIN,
        "add_alarm",
        {"target": kitchen, "time": "07:00", "weekdays": "daily", "duration": 120},
        blocking=True,
        return_response=True,
    )
    alarm_id = result["alarm"]["id"]
    for reset in (0, None):
        await manager.async_update_alarm(alarm_id, duration=600)
        await hass.services.async_call(
            DOMAIN, "update_alarm", {"alarm_id": alarm_id, "duration": reset}, blocking=True
        )
        assert manager.get_alarm(alarm_id).duration is None


# -------------------------------------------------------------------- snooze


@pytest.mark.parametrize(
    ("second", "minutes", "rings"),
    [(58, 1, (10, 4)), (3, 5, (10, 7)), (6, 5, (10, 8))],
)
async def test_snooze_is_never_noticeably_short(
    hass: HomeAssistant,
    local_tz,
    freezer,
    satellites,
    manager,
    announce_calls,
    second,
    minutes,
    rings,
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(10, 2)))
    await _advance(hass, freezer, START.replace(minute=2, second=second))
    session = manager.session_for_target(kitchen)
    snoozed = await manager.async_snooze(session, minutes)
    hour, minute = rings
    assert snoozed.next_pending(dt_util.utcnow()) == START.replace(hour=hour, minute=minute)
    await session.wait_finished(5)


async def test_invalid_snooze_keeps_ringing(
    hass: HomeAssistant, local_tz, freezer, satellites, manager, announce_calls
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    session = await manager.async_ring(manager.target(kitchen), label="Wake")
    with pytest.raises(AlarmError):
        await manager.async_snooze(session, 10**9)
    # Within range, but the alarm it would create is invalid: the satellite went away.
    er.async_get(hass).async_update_entity(kitchen, disabled_by=er.RegistryEntryDisabler.USER)
    with pytest.raises(AlarmError):
        await manager.async_snooze(session, 5)
    assert not session.dismissed
    await _end(session)


# ------------------------------------------------------------ satellite changes


async def test_renamed_satellite_keeps_alarms_and_entities(
    hass: HomeAssistant, local_tz, freezer, satellites, manager
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    alarm = await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(11, 0)))
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    sensor = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{kitchen}_next_alarm")
    device_id = manager._device(dev_reg, kitchen).id
    renamed = "assist_satellite.kitchen_renamed"

    ent_reg.async_update_entity(kitchen, new_entity_id=renamed)
    await hass.async_block_till_done()

    reloaded = get_manager(hass)
    assert reloaded.get_alarm(alarm.id).target == renamed
    assert reloaded.target(renamed) is not None
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, f"{renamed}_next_alarm") == sensor
    ours = [e.entity_id for e in ent_reg.entities.values() if e.platform == DOMAIN]
    assert not [entity_id for entity_id in ours if entity_id.endswith("_2")]
    # The same device now carries the new identifier; none is left for the old one.
    assert (DOMAIN, renamed) in dev_reg.async_get(device_id).identifiers
    assert manager._device(dev_reg, kitchen) is None
    assert ent_reg.async_get(sensor).device_id == device_id


async def test_removed_satellite_entities_go_and_come_back(
    hass: HomeAssistant, local_tz, freezer, satellites, manager
) -> None:
    freezer.move_to(START)
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    kitchen = satellites["kitchen"]["satellite"]
    bedroom = satellites["bedroom"]["satellite"]
    alarm = await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(11, 0)))
    sensors = {
        satellite: ent_reg.async_get_entity_id("sensor", DOMAIN, f"{satellite}_next_alarm")
        for satellite in (kitchen, bedroom)
    }

    for satellite in (kitchen, bedroom):
        ent_reg.async_remove(satellite)
    await hass.async_block_till_done()
    for satellite, sensor in sensors.items():
        assert ent_reg.async_get_entity_id("sensor", DOMAIN, f"{satellite}_next_alarm") is None
        assert hass.states.get(sensor) is None
    # The kitchen device stays for the alarm's switch; the bedroom one goes.
    assert manager._device(dev_reg, kitchen) is not None
    assert manager._device(dev_reg, bedroom) is None
    # The orphaned alarm can still be switched off.
    await manager.async_update_alarm(alarm.id, enabled=False)

    other = hass.config_entries.async_entries("esphome")[0]
    back = ent_reg.async_get_or_create(SAT_DOMAIN, "esphome", "bedroom-sat", config_entry=other)
    await hass.async_block_till_done()
    sensor = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{back.entity_id}_next_alarm")
    assert sensor is not None and hass.states.get(sensor) is not None


async def test_disabled_satellite_is_no_target(hass: HomeAssistant, satellites, manager) -> None:
    kitchen = satellites["kitchen"]["satellite"]
    er.async_get(hass).async_update_entity(kitchen, disabled_by=er.RegistryEntryDisabler.USER)
    await hass.async_block_till_done()
    assert manager.target(kitchen) is None
    with pytest.raises(AlarmError):
        await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(7, 0)))


# --------------------------------------------------------------------- sounds


@pytest.mark.parametrize("sound", ["beep.mp3", "concat:/etc/hosts", "file:///etc/hosts"])
async def test_services_reject_unplayable_sounds(
    hass: HomeAssistant, satellites, manager, sound
) -> None:
    kitchen = satellites["kitchen"]["satellite"]
    with pytest.raises(ServiceValidationError, match="not a valid sound"):
        await hass.services.async_call(
            DOMAIN, "add_alarm", {"target": kitchen, "time": "07:00", "sound": sound}, blocking=True
        )
    with pytest.raises(ServiceValidationError, match="not a valid sound"):
        await hass.services.async_call(
            DOMAIN, "test_alarm", {"target": kitchen, "sound": sound}, blocking=True
        )
    await hass.services.async_call(
        DOMAIN,
        "add_alarm",
        {"target": kitchen, "time": "07:00", "sound": "/local/beep.mp3"},
        blocking=True,
    )


async def test_sound_download_is_capped(
    hass: HomeAssistant, satellites, manager, aioclient_mock: AiohttpClientMocker, monkeypatch
) -> None:
    monkeypatch.setattr("custom_components.voice_alarms.ringer.MAX_SOUND_DOWNLOAD_BYTES", 1000)
    aioclient_mock.get("http://example.invalid/huge.mp3", content=b"x" * 5000)
    aioclient_mock.get("http://example.invalid/small.mp3", content=b"x" * 500)
    target = manager.target(satellites["kitchen"]["satellite"])

    def session(url: str) -> RingSession:
        return RingSession(
            hass,
            manager,
            hass.data[DATA_STREAMS],
            target,
            manager.ring_config(sound=url),
            kind=KIND_ALARM,
            label="x",
            loop=manager.loop,
        )

    with pytest.raises(RuntimeError, match="larger than"):
        await session("http://example.invalid/huge.mp3")._resolve_sound_for_ffmpeg()
    small = session("http://example.invalid/small.mp3")
    path = await small._resolve_sound_for_ffmpeg()
    assert path
    await hass.async_add_executor_job(__import__("os").remove, path)


async def test_short_sound_without_ffmpeg_keeps_ringing(
    hass: HomeAssistant, satellites, manager, monkeypatch, caplog
) -> None:
    """A beep shorter than 3 s is not a failed or refused announcement."""
    monkeypatch.setattr("custom_components.voice_alarms.ringer.ANNOUNCE_REFUSED_SECONDS", 0.05)
    registry = hass.data[DATA_STREAMS]
    raw_calls: list[str] = []

    async def announce(call: ServiceCall) -> None:
        media_id = call.data["media_id"]
        if match := re.search(r"/stream/([^/]+)\.flac", media_id):
            spec = registry.get(match.group(1))
            spec.opened = True
            try:
                await anext(spec.make_source())
            except Exception as err:  # noqa: BLE001
                spec.error = str(err)
            return
        raw_calls.append(media_id)
        await asyncio.sleep(0.1)  # the beep plays

    hass.services.async_register(SAT_DOMAIN, "announce", announce)
    target = manager.target(satellites["kitchen"]["satellite"])
    session = await manager.async_ring(
        target, label="Beep", duration=2, sound="http://example.invalid/beep.mp3"
    )
    await asyncio.wait_for(session.wait_finished(), 5)
    assert len(raw_calls) >= 5
    assert "Giving up" not in caplog.text


# --------------------------------------------------------------- odds and ends


async def test_service_errors_follow_instance_language(
    hass: HomeAssistant, satellites, manager
) -> None:
    kitchen = satellites["kitchen"]["satellite"]
    alarm = await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(7, 0)))
    set_default_language("de")
    try:
        with pytest.raises(ServiceValidationError, match="Nichts zu ändern"):
            await hass.services.async_call(
                DOMAIN, "update_alarm", {"alarm_id": alarm.id}, blocking=True
            )
        with pytest.raises(ServiceValidationError, match="Gerade klingelt nichts"):
            await hass.services.async_call(DOMAIN, "snooze", {}, blocking=True)
    finally:
        set_default_language("en")


def test_sensor_does_not_record_alarm_list() -> None:
    from custom_components.voice_alarms.sensor import NextAlarmSensor  # noqa: PLC0415

    assert "alarms" in NextAlarmSensor._unrecorded_attributes


@pytest.mark.parametrize(("channels", "count"), [(1, 4096), (1, 77), (2, 1000)])
def test_frame_crc_matches_bytewise_crc(channels: int, count: int) -> None:
    from array import array  # noqa: PLC0415

    samples = array("h", ((i * 7919) % 65536 - 32768 for i in range(count * channels)))
    frame = FlacWriter(channels=channels).frame(samples)
    assert struct.unpack(">H", frame[-2:])[0] == flac_crc16(frame[:-2])


# ------------------------------------------------------- second review round


async def test_time_edit_keeps_given_date(
    hass: HomeAssistant, local_tz, freezer, satellites, manager
) -> None:
    """The panel sends the unchanged date along with a new time."""
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    day = START.date() + timedelta(days=13)
    alarm = await manager.async_add_alarm(
        manager.build_alarm(target=kitchen, at=time(7, 0), on_date=day)
    )
    await hass.services.async_call(
        DOMAIN,
        "update_alarm",
        {"alarm_id": alarm.id, "time": "08:00", "date": day.isoformat()},
        blocking=True,
    )
    assert alarm.date == day and alarm.time == time(8, 0)
    # Without a date, a new time moves the alarm to the next time it comes round.
    await manager.async_update_alarm(alarm.id, time=time(9, 0))
    assert alarm.date == START.date() + timedelta(days=1)


def _held_announce(hass: HomeAssistant) -> tuple[list[ServiceCall], asyncio.Event]:
    """Announce that returns at once for alarms but holds spoken text until released."""
    calls: list[ServiceCall] = []
    release = asyncio.Event()

    async def announce(call: ServiceCall) -> None:
        calls.append(call)
        if call.data.get("message"):
            await release.wait()

    hass.services.async_register(SAT_DOMAIN, "announce", announce)
    return calls, release


async def test_dismissed_reminder_is_not_repeated(
    hass: HomeAssistant, local_tz, freezer, satellites, manager
) -> None:
    calls, release = _held_announce(hass)
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(10, 2), message="P"))
    await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(10, 3), name="Wake"))
    await _advance(hass, freezer, START.replace(minute=2, second=1))
    reminder = manager.session_for_target(kitchen)
    await _until(lambda: len(_spoken(calls)) == 1)
    await manager.async_dismiss(kitchen)  # while it is still being spoken

    await _advance(hass, freezer, START.replace(minute=3, second=1))
    alarm = manager.session_for_target(kitchen)
    assert alarm is not reminder and alarm.kind == KIND_ALARM
    release.set()
    await asyncio.wait_for(reminder.wait_finished(), 5)
    await hass.async_block_till_done()
    assert manager.session_for_target(kitchen) is alarm
    assert manager.active_sessions() == [alarm]
    await _end(alarm)
    await hass.async_block_till_done()
    assert manager.session_for_target(kitchen) is None
    assert len(_spoken(calls)) == 1


async def test_supersede_hands_over_volume_restore(
    hass: HomeAssistant, satellites, setup_integration, manager, monkeypatch
) -> None:
    """An alarm that takes over from a still talking reminder restores the user's volume.

    Runs on the real clock: the frozen one of ``freezer`` stops the wait timeout.
    """
    monkeypatch.setattr("custom_components.voice_alarms.ringer.SUPERSEDE_TIMEOUT", 0.1)
    hass.config_entries.async_update_entry(setup_integration, options={"alarm_volume": 80})
    player = satellites["kitchen"]["media_player"]

    async def volume_set(call: ServiceCall) -> None:
        state = hass.states.get(player)
        hass.states.async_set(
            player, state.state, {**state.attributes, "volume_level": call.data["volume_level"]}
        )

    def volume() -> float:
        return hass.states.get(player).attributes["volume_level"]

    async def until(predicate) -> None:
        async with asyncio.timeout(3):
            while not predicate():
                await asyncio.sleep(0.01)

    hass.services.async_register("media_player", "volume_set", volume_set)
    calls, release = _held_announce(hass)
    target = manager.target(satellites["kitchen"]["satellite"])
    try:
        reminder = await manager.async_ring(target, kind=KIND_REMINDER, message="P", label="P")
        await until(lambda: len(_spoken(calls)) == 1)
        assert volume() == 0.8

        alarm = await manager.async_ring(target, label="Wake")
        assert not any(c.data.get("media_id") for c in calls)  # waits for the reminder
        await until(lambda: any(c.data.get("media_id") for c in calls))  # gave up waiting
        assert volume() == 0.8
        alarm.dismiss()
        await asyncio.wait_for(alarm.wait_finished(), 5)
        assert volume() == 0.4  # the volume from before the reminder
        release.set()
        await asyncio.wait_for(reminder.wait_finished(), 5)
        assert volume() == 0.4  # the reminder handed its restore over
    finally:
        release.set()
        manager._queued.clear()
        for session in [*manager.sessions.values()]:
            session.dismiss()
            await asyncio.wait_for(session.wait_finished(), 5)


async def test_alarm_with_old_unchecked_sound_can_be_switched_off(
    hass: HomeAssistant, local_tz, freezer, satellites, manager, caplog
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    alarm = await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(11, 0)))
    alarm.sound = "www/wake.mp3"  # saved before sounds were checked
    switch = er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"alarm_{alarm.id}")
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    assert not alarm.enabled
    # It rings with the default sound rather than handing the path to ffmpeg.
    assert manager.ring_config(alarm).sound is None
    assert "not playable" in caplog.text
    # And snoozing it works.
    session = await manager.async_ring(manager.target(kitchen), alarm=alarm, label="x")
    snoozed = await manager.async_snooze(session, 5)
    assert snoozed.sound is None
    await asyncio.wait_for(session.wait_finished(), 5)


async def test_renamed_entity_is_not_created_twice(
    hass: HomeAssistant, satellites, manager, caplog
) -> None:
    kitchen = satellites["kitchen"]["satellite"]
    ent_reg = er.async_get(hass)
    sensor = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{kitchen}_next_alarm")
    ent_reg.async_update_entity(sensor, new_entity_id="sensor.my_kitchen_next")
    await hass.async_block_till_done()
    async_dispatcher_send(hass, SIGNAL_TARGETS_UPDATED)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_kitchen_next") is not None
    assert "does not generate unique IDs" not in caplog.text
