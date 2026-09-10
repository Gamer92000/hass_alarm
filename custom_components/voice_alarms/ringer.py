"""Ring sessions: play an alarm or speak a reminder on a satellite."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from array import array
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components import media_source
from homeassistant.components.assist_satellite import DOMAIN as ASSIST_SATELLITE_DOMAIN
from homeassistant.components.media_player import (
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    MediaPlayerEntityFeature,
)
from homeassistant.components.media_player import (
    DOMAIN as MEDIA_PLAYER_DOMAIN,
)
from homeassistant.components.media_player.browse_media import (
    async_process_play_media_url,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_SUPPORTED_FEATURES
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .audio import RampSpec, stream_builtin, stream_ffmpeg
from .const import (
    ANNOUNCE_RETRY_SECONDS,
    KIND_REMINDER,
    MAX_SEGMENT_SECONDS,
    MIN_PLAYBACK_FOR_DEVICE_STOP,
)
from .http import StreamRegistry, StreamSpec
from .i18n import default_language, tr
from .models import Alarm
from .targets import Target

if TYPE_CHECKING:
    from .manager import AlarmManager

_LOGGER = logging.getLogger(__name__)

STATE_RINGING = "ringing"
STATE_PAUSED = "paused"
STATE_DONE = "done"


@dataclass(slots=True)
class RingConfig:
    """Everything a session needs to know about how to ring."""

    duration: int
    sound: str | None  # None -> built-in
    ramp: RampSpec
    volume: float | None  # 0..1 or None to leave the media player alone
    reminder_repeats: int
    reminder_interval: int
    device_stop_pause: int
    ffmpeg_binary: str | None


class RingSession:
    """One alarm ringing (or reminder speaking) on one satellite."""

    def __init__(
        self,
        hass: HomeAssistant,
        manager: AlarmManager,
        registry: StreamRegistry,
        target: Target,
        config: RingConfig,
        *,
        alarm: Alarm | None = None,
        kind: str,
        message: str | None = None,
        label: str,
        origin: str = "alarm",
        loop: array,
    ) -> None:
        self.hass = hass
        self.manager = manager
        self.registry = registry
        self.target = target
        self.config = config
        self.alarms: list[Alarm] = [alarm] if alarm else []
        self.kind = kind
        self.message = message
        self.label = label
        self.origin = origin
        self.loop = loop

        self.id = secrets.token_hex(6)
        self.started: datetime = dt_util.utcnow()
        self.ends: datetime = self.started + timedelta(seconds=config.duration)
        self.state = STATE_RINGING
        self.dismissed = False
        self.dismissed_by: str | None = None
        self.finished_at: datetime | None = None
        self.context = Context()

        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._use_raw = False
        self._resolved_sound: str | None = None
        self._temp_file: str | None = None

    # ------------------------------------------------------------------ public

    @property
    def active(self) -> bool:
        """True while the session is ringing or paused."""
        return self.state != STATE_DONE

    @property
    def alarm_ids(self) -> list[str]:
        """Ids of alarms attached to this session."""
        return [alarm.id for alarm in self.alarms]

    def start(self) -> None:
        """Start ringing in the background."""
        self._task = self.hass.async_create_background_task(
            self._run(), name=f"voice_alarms ring {self.target.entity_id}"
        )

    def attach(self, alarm: Alarm) -> None:
        """Attach another alarm that fired while this session is active."""
        if alarm.id not in self.alarm_ids:
            self.alarms.append(alarm)
        if alarm.is_reminder and alarm.message:
            if self.message:
                self.message = f"{self.message}. {alarm.message}"
            else:
                self.message = alarm.message
        self.label = " & ".join(a.label for a in self.alarms) or self.label

    def dismiss(self, by: str = "user") -> None:
        """Stop the session."""
        if self.dismissed:
            return
        self.dismissed = True
        self.dismissed_by = by
        self._stop.set()
        self._wake.set()

    async def wait_finished(self) -> None:
        """Wait for the background task to finish."""
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the frontend."""
        return {
            "id": self.id,
            "target": self.target.entity_id,
            "target_name": self.target.display,
            "kind": self.kind,
            "label": self.label,
            "message": self.message,
            "alarm_ids": self.alarm_ids,
            "state": self.state,
            "origin": self.origin,
            "started": self.started.isoformat(),
            "ends": self.ends.isoformat(),
            "dismissed_by": self.dismissed_by,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

    # ----------------------------------------------------------------- running

    async def _run(self) -> None:
        restore = None
        try:
            restore = await self._apply_volume()
            if self.kind == KIND_REMINDER:
                await self._run_reminder()
            else:
                await self._run_alarm()
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Ring session on %s failed", self.target.entity_id)
        finally:
            self.state = STATE_DONE
            self.finished_at = dt_util.utcnow()
            if restore is not None:
                try:
                    await restore()
                except Exception:  # noqa: BLE001
                    _LOGGER.debug("Could not restore volume on %s", self.target.media_player)
            if self._temp_file:
                await self.hass.async_add_executor_job(_remove_file, self._temp_file)
            self.manager.session_finished(self)

    async def _sleep(self, seconds: float) -> None:
        """Sleep, returning early when the session is dismissed."""
        self._wake.clear()
        if self.dismissed:
            return
        try:
            await asyncio.wait_for(self._wake.wait(), seconds)
        except TimeoutError:
            pass

    async def _announce(self, **data: Any) -> None:
        await self.hass.services.async_call(
            ASSIST_SATELLITE_DOMAIN,
            "announce",
            {ATTR_ENTITY_ID: self.target.entity_id, "preannounce": False, **data},
            blocking=True,
            context=self.context,
        )

    async def _run_alarm(self) -> None:
        elapsed = 0.0
        failures = 0
        while not self.dismissed:
            remaining = self.config.duration - elapsed
            if remaining < 1.0:
                break
            if self._use_raw:
                played = await self._play_raw_once()
                elapsed += played
                if played < MIN_PLAYBACK_FOR_DEVICE_STOP and not self.dismissed:
                    failures += 1
                    if failures > 5:
                        _LOGGER.error(
                            "Giving up ringing %s: playback keeps failing", self.target.entity_id
                        )
                        break
                    await self._sleep(ANNOUNCE_RETRY_SECONDS)
                    elapsed += ANNOUNCE_RETRY_SECONDS
                continue

            segment = min(remaining, MAX_SEGMENT_SECONDS)
            spec = self._make_spec(offset=elapsed, duration=segment)
            self.registry.register(spec)
            started = time.monotonic()
            try:
                await self._announce(media_id=spec.url)
            except HomeAssistantError as err:
                _LOGGER.warning("Announcing alarm on %s failed: %s", self.target.entity_id, err)
                spec.error = spec.error or str(err)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Announcing alarm on %s failed", self.target.entity_id)
                spec.error = spec.error or "announce failed"
            finally:
                self.registry.unregister(spec.token)
            played = time.monotonic() - started

            if self.dismissed:
                break
            if spec.finished:
                # The whole segment was delivered (the device is at most a
                # couple of seconds of buffer behind), so account for the
                # audio length rather than the wall clock.
                elapsed += segment
                failures = 0
                continue
            elapsed += played

            if (
                spec.error
                and self.config.sound
                and not self._use_raw
                and "ffmpeg" in spec.error.lower()
            ):
                _LOGGER.warning(
                    "ffmpeg could not process alarm sound %s; playing it without volume ramp",
                    self.config.sound,
                )
                self._use_raw = True
                continue

            if spec.error or not spec.opened or played < MIN_PLAYBACK_FOR_DEVICE_STOP:
                failures += 1
                if failures > 5:
                    _LOGGER.error(
                        "Giving up ringing %s: playback keeps failing", self.target.entity_id
                    )
                    break
                _LOGGER.debug(
                    "Retrying alarm playback on %s (%s)", self.target.entity_id, spec.error
                )
                await self._sleep(ANNOUNCE_RETRY_SECONDS)
                elapsed += ANNOUNCE_RETRY_SECONDS
                continue

            # The device ended playback before the stream did: somebody pressed
            # the button or said the wake/stop word on the satellite.
            failures = 0
            if self.config.device_stop_pause <= 0:
                _LOGGER.info("Alarm on %s stopped on the device", self.target.entity_id)
                self.dismiss(by="device")
                break
            _LOGGER.info(
                "Alarm on %s paused on the device for %s s",
                self.target.entity_id,
                self.config.device_stop_pause,
            )
            self.state = STATE_PAUSED
            self.manager.session_changed(self)
            await self._sleep(self.config.device_stop_pause)
            elapsed += self.config.device_stop_pause
            if self.dismissed:
                break
            self.state = STATE_RINGING
            self.manager.session_changed(self)

    async def _run_reminder(self) -> None:
        text = self.message or self.label
        for attempt in range(max(1, self.config.reminder_repeats)):
            if self.dismissed:
                break
            try:
                await self.hass.services.async_call(
                    ASSIST_SATELLITE_DOMAIN,
                    "announce",
                    {
                        ATTR_ENTITY_ID: self.target.entity_id,
                        "message": tr(default_language(), "spoken_reminder", text=text),
                        "preannounce": True,
                    },
                    blocking=True,
                    context=self.context,
                )
            except HomeAssistantError as err:
                _LOGGER.warning("Speaking reminder on %s failed: %s", self.target.entity_id, err)
            if attempt < self.config.reminder_repeats - 1:
                await self._sleep(self.config.reminder_interval)

    # ------------------------------------------------------------------ audio

    def _make_spec(self, *, offset: float, duration: float) -> StreamSpec:
        sound = self.config.sound
        if not sound:
            return StreamSpec(make_source=lambda: self._builtin_source(offset, duration))
        return StreamSpec(make_source=lambda: self._ffmpeg_source(offset, duration))

    def _builtin_source(self, offset: float, duration: float) -> AsyncIterator[bytes]:
        return stream_builtin(
            self.loop,
            duration=duration,
            offset=offset,
            ramp=self.config.ramp,
            stop=self._stop,
        )

    async def _ffmpeg_source(self, offset: float, duration: float) -> AsyncIterator[bytes]:
        if not self.config.ffmpeg_binary:
            raise RuntimeError("ffmpeg is not available")
        source = await self._resolve_sound_for_ffmpeg()
        async for chunk in stream_ffmpeg(
            self.config.ffmpeg_binary,
            source,
            duration=duration,
            offset=offset,
            ramp=self.config.ramp,
            stop=self._stop,
        ):
            yield chunk

    async def _resolve_sound(self) -> str:
        """Resolve the configured sound to a playable (absolute) URL."""
        if self._resolved_sound:
            return self._resolved_sound
        sound = self.config.sound
        assert sound
        if media_source.is_media_source_id(sound):
            play = await media_source.async_resolve_media(self.hass, sound, None)
            if play.path is not None:
                self._resolved_sound = str(play.path)
                return self._resolved_sound
            url = play.url
        else:
            url = sound
        self._resolved_sound = async_process_play_media_url(self.hass, url)
        return self._resolved_sound

    async def _resolve_sound_for_ffmpeg(self) -> str:
        """Return a local file path ffmpeg can loop (downloads URLs once)."""
        if self._temp_file:
            return self._temp_file
        resolved = await self._resolve_sound()
        if "://" not in resolved:
            return resolved
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(resolved, timeout=30) as resp:
                resp.raise_for_status()
                data = await resp.read()
        except Exception as err:
            raise RuntimeError(f"ffmpeg source download failed: {err}") from err
        path = await self.hass.async_add_executor_job(_write_temp, data)
        self._temp_file = path
        return path

    async def _play_raw_once(self) -> float:
        """Announce the custom sound directly (no ramp); return seconds played."""
        started = time.monotonic()
        try:
            url = await self._resolve_sound()
            await self._announce(media_id=url)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Playing alarm sound on %s failed: %s", self.target.entity_id, err)
        return time.monotonic() - started

    # ----------------------------------------------------------------- volume

    async def _apply_volume(self):
        """Set the media player to the alarm volume; return a restore coroutine."""
        player = self.target.media_player
        volume = self.config.volume
        if player is None or volume is None:
            return None
        state = self.hass.states.get(player)
        if state is None:
            return None
        features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
        if not features & MediaPlayerEntityFeature.VOLUME_SET:
            return None
        previous = state.attributes.get(ATTR_MEDIA_VOLUME_LEVEL)
        was_muted = bool(state.attributes.get(ATTR_MEDIA_VOLUME_MUTED))
        try:
            await self.hass.services.async_call(
                MEDIA_PLAYER_DOMAIN,
                SERVICE_VOLUME_SET,
                {ATTR_ENTITY_ID: player, ATTR_MEDIA_VOLUME_LEVEL: volume},
                blocking=True,
                context=self.context,
            )
            if was_muted and features & MediaPlayerEntityFeature.VOLUME_MUTE:
                await self.hass.services.async_call(
                    MEDIA_PLAYER_DOMAIN,
                    SERVICE_VOLUME_MUTE,
                    {ATTR_ENTITY_ID: player, ATTR_MEDIA_VOLUME_MUTED: False},
                    blocking=True,
                    context=self.context,
                )
        except HomeAssistantError as err:
            _LOGGER.warning("Could not set alarm volume on %s: %s", player, err)
            return None

        async def restore() -> None:
            if previous is not None:
                await self.hass.services.async_call(
                    MEDIA_PLAYER_DOMAIN,
                    SERVICE_VOLUME_SET,
                    {ATTR_ENTITY_ID: player, ATTR_MEDIA_VOLUME_LEVEL: previous},
                    blocking=True,
                    context=self.context,
                )
            if was_muted and features & MediaPlayerEntityFeature.VOLUME_MUTE:
                await self.hass.services.async_call(
                    MEDIA_PLAYER_DOMAIN,
                    SERVICE_VOLUME_MUTE,
                    {ATTR_ENTITY_ID: player, ATTR_MEDIA_VOLUME_MUTED: True},
                    blocking=True,
                    context=self.context,
                )

        return restore


def _write_temp(data: bytes) -> str:
    import tempfile  # noqa: PLC0415

    with tempfile.NamedTemporaryFile(prefix="voice_alarm_", suffix=".bin", delete=False) as handle:
        handle.write(data)
        return handle.name


def _remove_file(path: str) -> None:
    import contextlib  # noqa: PLC0415
    import os  # noqa: PLC0415

    with contextlib.suppress(OSError):
        os.remove(path)
