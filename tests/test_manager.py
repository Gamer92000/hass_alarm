"""Tests for scheduling and ringing."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Generator
from datetime import datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.voice_alarms import get_manager
from custom_components.voice_alarms.const import DEFAULT_RAMP_CURVE, DOMAIN, STORAGE_KEY
from custom_components.voice_alarms.http import DATA_STREAMS
from custom_components.voice_alarms.manager import AlarmError, AlarmManager
from custom_components.voice_alarms.models import Alarm
from homeassistant.components.assist_satellite import DOMAIN as SAT_DOMAIN
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CoreState, HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util

TZ = ZoneInfo("Europe/Zurich")
START = datetime(2026, 9, 7, 10, 0, tzinfo=TZ)  # Monday 10:00 local


@pytest.fixture
async def local_tz(hass: HomeAssistant) -> None:
    await hass.config.async_set_time_zone("Europe/Zurich")


@pytest.fixture
def blocking_announce(hass: HomeAssistant, setup_integration) -> Generator[SimpleNamespace]:
    """Announce handler that blocks like real playback until released."""
    state = SimpleNamespace(calls=[], release=asyncio.Event())

    async def handler(call: ServiceCall) -> None:
        state.calls.append(call)
        media_id = call.data.get("media_id") or ""
        match = re.search(r"/stream/([^/]+)\.flac", media_id)
        spec = hass.data[DATA_STREAMS].get(match.group(1)) if match else None
        if spec:
            spec.opened = True
        await state.release.wait()
        if spec:
            spec.finished = True

    hass.services.async_register(SAT_DOMAIN, "announce", handler)
    yield state
    # A test that failed before releasing must not hang the shutdown on its ring.
    state.release.set()


async def _advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, to: datetime) -> None:
    freezer.move_to(to)
    async_fire_time_changed(hass, to)
    await hass.async_block_till_done()


async def test_one_time_alarm_fires_and_is_removed(
    hass: HomeAssistant,
    local_tz,
    freezer: FrozenDateTimeFactory,
    satellites,
    manager,
    blocking_announce,
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    alarm = await manager.async_add_alarm(
        manager.build_alarm(target=kitchen, at=time(10, 5), name="Tea")
    )
    assert alarm.date == START.date()
    assert alarm.next_pending(dt_util.utcnow()) == START.replace(minute=5)

    sensor = hass.states.get("sensor.voice_alarms_voice_pe_kitchen_next_alarm")
    assert sensor is not None
    assert sensor.state == START.replace(minute=5).astimezone(dt_util.UTC).isoformat()
    assert hass.states.get("switch.voice_alarms_voice_pe_kitchen_tea").state == "on"

    await _advance(hass, freezer, START.replace(minute=5, second=1))
    assert len(blocking_announce.calls) == 1
    call = blocking_announce.calls[0]
    assert call.data["entity_id"] == kitchen
    assert call.data["preannounce"] is False
    assert call.data["media_id"].startswith(f"/api/{DOMAIN}/stream/")

    session = manager.session_for_target(kitchen)
    assert session is not None and session.active
    assert session.label == "Tea"
    assert hass.states.get("binary_sensor.voice_alarms_voice_pe_kitchen_ringing").state == "on"
    # one-time alarm is gone once it fired
    assert alarm.id not in manager.alarms
    assert hass.states.get("sensor.voice_alarms_voice_pe_kitchen_next_alarm").state == "unknown"

    dismissed = await manager.async_dismiss(kitchen)
    assert dismissed == [session]
    blocking_announce.release.set()
    await session.wait_finished()
    await hass.async_block_till_done()
    assert not session.active
    assert session.dismissed_by == "user"
    assert hass.states.get("binary_sensor.voice_alarms_voice_pe_kitchen_ringing").state == "off"
    assert manager.recently_finished(timedelta(minutes=1)) == [session]
    await hass.async_block_till_done()
    assert hass.states.get("switch.voice_alarms_voice_pe_kitchen_tea") is None


async def _restart(hass: HomeAssistant, entry: MockConfigEntry) -> AlarmManager:
    """Stand in for a Home Assistant restart: the manager starts over from storage."""
    hass.set_state(CoreState.running)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    return get_manager(hass)


async def test_alarm_due_while_stopping_is_kept_for_the_catch_up(
    hass: HomeAssistant,
    local_tz,
    freezer: FrozenDateTimeFactory,
    satellites,
    setup_integration: MockConfigEntry,
    manager,
    blocking_announce,
) -> None:
    """A restart asked for just before an alarm: it rings after the restart, not during it."""
    blocking_announce.release.set()  # a ring started by mistake must not hang the test
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    bedroom = satellites["bedroom"]["satellite"]
    once = await manager.async_add_alarm(
        manager.build_alarm(target=kitchen, at=time(10, 5), name="Tea")
    )
    daily = await manager.async_add_alarm(
        manager.build_alarm(target=bedroom, at=time(10, 5), weekdays=list(range(7)), name="Daily")
    )
    hass.set_state(CoreState.stopping)
    await _advance(hass, freezer, START.replace(minute=5, second=1))
    assert blocking_announce.calls == []
    assert once.id in manager.alarms
    assert once.last_fired is None
    assert daily.last_fired is None

    freezer.move_to(START.replace(minute=6, second=30))
    manager = await _restart(hass, setup_integration)
    assert {call.data["entity_id"] for call in blocking_announce.calls} == {kitchen, bedroom}
    assert once.id not in manager.alarms
    assert manager.alarms[daily.id].last_fired == START.replace(minute=5)
    await manager.async_dismiss()
    await hass.async_block_till_done()


async def test_alarm_ringing_when_stopping_rings_again_after_the_restart(
    hass: HomeAssistant,
    local_tz,
    freezer: FrozenDateTimeFactory,
    satellites,
    setup_integration: MockConfigEntry,
    manager,
    blocking_announce,
) -> None:
    """A ring that a restart cuts short is put back and caught up after the restart."""
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    bedroom = satellites["bedroom"]["satellite"]
    once = await manager.async_add_alarm(
        manager.build_alarm(target=kitchen, at=time(10, 5), name="Tea")
    )
    daily = await manager.async_add_alarm(
        manager.build_alarm(target=bedroom, at=time(10, 5), weekdays=list(range(7)), name="Daily")
    )
    await _advance(hass, freezer, START.replace(minute=5, second=1))
    assert len(blocking_announce.calls) == 2
    assert once.id not in manager.alarms
    assert daily.last_fired == START.replace(minute=5)

    hass.set_state(CoreState.stopping)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert manager.alarms[once.id].last_fired is None
    assert daily.last_fired is None

    blocking_announce.release.set()
    freezer.move_to(START.replace(minute=6, second=30))
    manager = await _restart(hass, setup_integration)
    rung = [*manager.sessions.values(), *manager.recent_sessions]  # since the restart
    assert sorted((s.target.entity_id, s.alarm_ids) for s in rung) == [
        (bedroom, [daily.id]),
        (kitchen, [once.id]),
    ]
    assert once.id not in manager.alarms
    assert manager.alarms[daily.id].last_fired == START.replace(minute=5)
    await manager.async_dismiss()
    await hass.async_block_till_done()


async def test_shutdown_saves_the_alarms_it_puts_back(
    hass: HomeAssistant,
    hass_storage,
    local_tz,
    freezer: FrozenDateTimeFactory,
    satellites,
    manager,
    blocking_announce,
) -> None:
    """A real shutdown, which does not unload the entry, still stores what it put back."""
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    bedroom = satellites["bedroom"]["satellite"]
    once = await manager.async_add_alarm(
        manager.build_alarm(target=kitchen, at=time(10, 5), name="Tea")
    )
    daily = await manager.async_add_alarm(
        manager.build_alarm(target=bedroom, at=time(10, 5), weekdays=list(range(7)), name="Daily")
    )
    await _advance(hass, freezer, START.replace(minute=5, second=1))
    assert len(blocking_announce.calls) == 2
    # The save after firing is done before the shutdown starts.
    await _advance(hass, freezer, START.replace(minute=5, second=5))
    assert {a["id"] for a in hass_storage[STORAGE_KEY]["data"]["alarms"]} == {daily.id}

    await hass.async_stop()
    stored = {a["id"]: a for a in hass_storage[STORAGE_KEY]["data"]["alarms"]}
    assert stored.keys() == {once.id, daily.id}
    assert stored[once.id]["last_fired"] is None
    assert stored[daily.id]["last_fired"] is None


async def test_recurring_alarm_rescheduled_while_ringing_keeps_its_change(
    hass: HomeAssistant,
    local_tz,
    freezer: FrozenDateTimeFactory,
    satellites,
    manager,
    blocking_announce,
) -> None:
    """An alarm moved while it rings is not put back as it was before it fired."""
    freezer.move_to(START)
    bedroom = satellites["bedroom"]["satellite"]
    daily = await manager.async_add_alarm(
        manager.build_alarm(target=bedroom, at=time(10, 5), weekdays=list(range(7)), name="Daily")
    )
    yesterday = START.replace(minute=5) - timedelta(days=1)
    daily.created = yesterday - timedelta(hours=1)
    daily.last_fired = yesterday
    await _advance(hass, freezer, START.replace(minute=5, second=1))
    assert len(blocking_announce.calls) == 1

    await manager.async_update_alarm(daily.id, time=time(10, 3))
    hass.set_state(CoreState.stopping)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    # Moved to a time already past today: the next ring is tomorrow, not a catch-up now.
    assert daily.next_occurrence(daily.pending_after()) == START.replace(minute=3) + timedelta(
        days=1
    )
    hass.set_state(CoreState.running)


async def test_dismissed_ring_is_not_put_back_when_stopping(
    hass: HomeAssistant,
    local_tz,
    freezer: FrozenDateTimeFactory,
    satellites,
    manager,
    blocking_announce,
) -> None:
    """A ring dismissed before the shutdown is over: its alarm does not come back."""
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    once = await manager.async_add_alarm(
        manager.build_alarm(target=kitchen, at=time(10, 5), name="Tea")
    )
    await _advance(hass, freezer, START.replace(minute=5, second=1))
    session = manager.session_for_target(kitchen)
    assert session is not None
    session.dismiss()

    hass.set_state(CoreState.stopping)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert once.id not in manager.alarms
    hass.set_state(CoreState.running)
    blocking_announce.release.set()
    await session.wait_finished()


async def test_recurring_alarm_skip_and_fire(
    hass: HomeAssistant,
    local_tz,
    freezer: FrozenDateTimeFactory,
    satellites,
    manager,
    blocking_announce,
) -> None:
    freezer.move_to(START)
    bedroom = satellites["bedroom"]["satellite"]
    alarm = await manager.async_add_alarm(
        manager.build_alarm(target=bedroom, at=time(7, 0), weekdays=[0, 1, 2, 3, 4], name="Work")
    )
    tuesday = datetime(2026, 9, 8, 7, 0, tzinfo=TZ)
    wednesday = datetime(2026, 9, 9, 7, 0, tzinfo=TZ)
    assert alarm.next_pending(dt_util.utcnow()) == tuesday

    alarm, skipped = await manager.async_skip_next(alarm.id)
    assert skipped == tuesday
    assert alarm.next_pending(dt_util.utcnow()) == wednesday
    assert alarm.public_dict()["next_skipped"] is True

    with pytest.raises(AlarmError):
        await manager.async_skip_next("nope")

    # Tuesday passes silently
    await _advance(hass, freezer, tuesday + timedelta(seconds=1))
    assert blocking_announce.calls == []
    assert alarm.id in manager.alarms

    # Wednesday rings
    await _advance(hass, freezer, wednesday + timedelta(seconds=1))
    assert len(blocking_announce.calls) == 1
    assert alarm.last_fired == wednesday
    assert alarm.skipped_occurrence is None
    assert alarm.id in manager.alarms
    assert alarm.next_pending(dt_util.utcnow()) == wednesday + timedelta(days=1)

    session = manager.session_for_target(bedroom)
    assert session is not None
    session.dismiss()
    blocking_announce.release.set()
    await session.wait_finished()


async def test_undo_skip(hass: HomeAssistant, local_tz, freezer, satellites, manager) -> None:
    freezer.move_to(START)
    alarm = await manager.async_add_alarm(
        manager.build_alarm(
            target=satellites["kitchen"]["satellite"], at=time(7, 0), weekdays=[0, 1, 2, 3, 4, 5, 6]
        )
    )
    tuesday = datetime(2026, 9, 8, 7, 0, tzinfo=TZ)
    await manager.async_skip_next(alarm.id)
    assert alarm.next_pending(dt_util.utcnow()) == tuesday + timedelta(days=1)
    alarm, restored = await manager.async_skip_next(alarm.id, undo=True)
    assert restored == tuesday
    assert alarm.next_pending(dt_util.utcnow()) == tuesday


async def test_disabled_alarm_does_not_fire(
    hass: HomeAssistant, local_tz, freezer, satellites, manager, blocking_announce
) -> None:
    freezer.move_to(START)
    alarm = await manager.async_add_alarm(
        manager.build_alarm(target=satellites["kitchen"]["satellite"], at=time(10, 5))
    )
    await manager.async_update_alarm(alarm.id, enabled=False)
    await _advance(hass, freezer, START.replace(minute=6))
    assert blocking_announce.calls == []
    assert alarm.id in manager.alarms  # disabled one-time alarms are kept


async def test_update_time_resets_schedule(
    hass: HomeAssistant, local_tz, freezer, satellites, manager
) -> None:
    freezer.move_to(START)
    alarm = await manager.async_add_alarm(
        manager.build_alarm(
            target=satellites["kitchen"]["satellite"], at=time(7, 0), weekdays=[0, 1, 2, 3, 4]
        )
    )
    alarm.last_fired = datetime(2026, 9, 7, 7, 0, tzinfo=TZ)
    alarm = await manager.async_update_alarm(alarm.id, time=time(11, 0))
    assert alarm.last_fired is None
    assert alarm.next_pending(dt_util.utcnow()) == START.replace(hour=11)

    alarm = await manager.async_update_alarm(alarm.id, weekdays=[])
    assert not alarm.is_recurring
    assert alarm.date == START.date()

    with pytest.raises(AlarmError):
        await manager.async_update_alarm(alarm.id, date=START.date() - timedelta(days=1))
    with pytest.raises(AlarmError):
        await manager.async_add_alarm(
            manager.build_alarm(target="assist_satellite.nope", at=time(1, 0))
        )


async def test_missed_alarms_on_startup(
    hass: HomeAssistant, hass_storage, satellites, freezer: FrozenDateTimeFactory
) -> None:
    """Alarms missed within the grace period ring at startup, older ones are skipped."""
    await hass.config.async_set_time_zone("Europe/Zurich")
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    yesterday = START - timedelta(days=1)
    recent = Alarm(
        target=kitchen, time=time(9, 55), date=START.date(), name="recent", created=yesterday
    )
    old = Alarm(target=kitchen, time=time(9, 30), date=START.date(), name="old", created=yesterday)
    recurring = Alarm(
        target=kitchen,
        time=time(9, 30),
        weekdays=[0, 1, 2, 3, 4, 5, 6],
        name="rec",
        created=yesterday,
    )
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {"alarms": [a.to_dict() for a in (recent, old, recurring)]},
    }

    calls: list[ServiceCall] = []
    release = asyncio.Event()

    async def handler(call: ServiceCall) -> None:
        calls.append(call)
        await release.wait()

    from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: PLC0415

    from custom_components.voice_alarms import get_manager  # noqa: PLC0415
    from homeassistant.setup import async_setup_component  # noqa: PLC0415

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    hass.services.async_register(SAT_DOMAIN, "announce", handler)
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, DOMAIN, {})
    hass.services.async_register(SAT_DOMAIN, "announce", handler)
    await hass.async_block_till_done()

    manager = get_manager(hass)
    assert "recent" not in {a.name for a in manager.alarms.values()}  # fired and removed
    assert "old" not in {a.name for a in manager.alarms.values()}  # expired
    rec = next(a for a in manager.alarms.values() if a.name == "rec")
    assert rec.last_fired == START.replace(hour=9, minute=30)  # marked missed
    assert rec.next_pending(dt_util.utcnow()) == START.replace(hour=9, minute=30) + timedelta(
        days=1
    )
    session = manager.session_for_target(kitchen)
    assert session is not None and session.label == "recent"
    session.dismiss()
    release.set()
    await session.wait_finished()


async def test_reminder_is_spoken(
    hass: HomeAssistant, local_tz, freezer, satellites, manager, blocking_announce
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    alarm = await manager.async_add_alarm(
        manager.build_alarm(target=kitchen, at=time(10, 1), message="take out the trash")
    )
    assert alarm.is_reminder
    await _advance(hass, freezer, START.replace(minute=1, second=1))
    assert len(blocking_announce.calls) == 1
    call = blocking_announce.calls[0]
    assert call.data["message"] == "Reminder: take out the trash"
    assert call.data["preannounce"] is True
    session = manager.session_for_target(kitchen)
    assert session.kind == "reminder"
    session.dismiss()
    blocking_announce.release.set()
    await session.wait_finished()


async def test_two_alarms_same_target_share_session(
    hass: HomeAssistant, local_tz, freezer, satellites, manager, blocking_announce
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(10, 2), name="A"))
    await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(10, 2), name="B"))
    await _advance(hass, freezer, START.replace(minute=2, second=1))
    assert len(blocking_announce.calls) == 1
    session = manager.session_for_target(kitchen)
    assert set(session.label.split(" & ")) == {"A", "B"}
    assert len(session.alarms) == 2
    session.dismiss()
    blocking_announce.release.set()
    await session.wait_finished()


async def test_snooze_creates_one_time_alarm(
    hass: HomeAssistant, local_tz, freezer, satellites, manager, blocking_announce
) -> None:
    freezer.move_to(START)
    kitchen = satellites["kitchen"]["satellite"]
    await manager.async_add_alarm(manager.build_alarm(target=kitchen, at=time(10, 2), name="Nap"))
    await _advance(hass, freezer, START.replace(minute=2, second=1))
    session = manager.session_for_target(kitchen)
    snoozed = await manager.async_snooze(session, 5)
    blocking_announce.release.set()
    await session.wait_finished()
    assert session.dismissed_by == "snooze"
    assert snoozed.name == "Nap (snoozed)"
    assert snoozed.next_pending(dt_util.utcnow()) == START.replace(minute=7)


async def test_test_ring_and_options(
    hass: HomeAssistant, local_tz, satellites, manager, blocking_announce
) -> None:
    kitchen = manager.target(satellites["kitchen"]["satellite"])
    assert kitchen is not None
    assert kitchen.media_player == satellites["kitchen"]["media_player"]
    assert kitchen.area_name == "Kitchen"
    config = manager.ring_config()
    assert config.duration == 300
    assert config.ramp.seconds == 30
    assert config.ramp.start == pytest.approx(0.1)
    assert config.ramp.curve == DEFAULT_RAMP_CURVE
    assert config.volume is None

    session = await manager.async_ring(kitchen, duration=15, label="Test", origin="test")
    await asyncio.sleep(0)
    assert session.config.duration == 15
    assert len(blocking_announce.calls) == 1
    session.dismiss()
    blocking_announce.release.set()
    await session.wait_finished()
