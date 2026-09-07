"""HTTP views serving alarm audio to satellites."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from aiohttp import web
from aiohttp.client_exceptions import ClientConnectionResetError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.http import HomeAssistantView
from homeassistant.util.hass_dict import HassKey

from .const import DEFAULT_SOUND_URL, DOMAIN, STREAM_URL_BASE

_LOGGER = logging.getLogger(__name__)

DATA_STREAMS: HassKey[StreamRegistry] = HassKey(f"{DOMAIN}_streams")
DATA_DEFAULT_WAV: HassKey[bytes] = HassKey(f"{DOMAIN}_default_wav")


@dataclass
class StreamSpec:
    """A one-shot audio stream that a satellite may fetch once."""

    make_source: Callable[[], AsyncIterator[bytes]]
    token: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    opened: bool = False
    opened_at: float | None = None
    finished: bool = False
    client_gone: bool = False
    error: str | None = None

    @property
    def url(self) -> str:
        """Relative URL of this stream."""
        return f"{STREAM_URL_BASE}/{self.token}.flac"


class StreamRegistry:
    """Registry of streams currently offered to satellites."""

    def __init__(self) -> None:
        self._streams: dict[str, StreamSpec] = {}

    def register(self, spec: StreamSpec) -> StreamSpec:
        """Register a stream."""
        self._streams[spec.token] = spec
        return spec

    def unregister(self, token: str) -> None:
        """Remove a stream."""
        self._streams.pop(token, None)

    def get(self, token: str) -> StreamSpec | None:
        """Look up a stream."""
        return self._streams.get(token)


class VoiceAlarmStreamView(HomeAssistantView):
    """Serve the alarm audio stream for a ring session segment.

    Satellites fetch this without authentication, so the URL contains an
    unguessable token that is valid only while the alarm segment is active.
    """

    url = f"{STREAM_URL_BASE}/{{token}}.flac"
    name = f"api:{DOMAIN}:stream"
    requires_auth = False

    def __init__(self, registry: StreamRegistry) -> None:
        self._registry = registry

    async def get(self, request: web.Request, token: str) -> web.StreamResponse:
        """Stream FLAC audio."""
        spec = self._registry.get(token)
        if spec is None:
            raise web.HTTPNotFound
        if spec.opened:
            # A second fetch of the same segment (e.g. a proxy retry) would
            # desynchronise the ramp; only ever serve a segment once.
            _LOGGER.debug("Stream %s requested twice", token)
            raise web.HTTPGone
        spec.opened = True
        spec.opened_at = time.monotonic()

        source = spec.make_source()
        try:
            first = await anext(source)
        except Exception as err:  # noqa: BLE001
            spec.error = str(err) or err.__class__.__name__
            _LOGGER.warning("Alarm audio stream failed to start: %s", spec.error)
            await source.aclose()
            raise web.HTTPInternalServerError(text=spec.error) from err

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "audio/flac",
                "Cache-Control": "no-store",
                "Accept-Ranges": "none",
            },
        )
        await response.prepare(request)
        try:
            await response.write(first)
            async for chunk in source:
                await response.write(chunk)
            spec.finished = True
            await response.write_eof()
        except (ConnectionResetError, ClientConnectionResetError, asyncio.CancelledError):
            spec.client_gone = True
            _LOGGER.debug("Client closed alarm stream %s", token)
            raise
        finally:
            await source.aclose()
        return response


class VoiceAlarmDefaultSoundView(HomeAssistantView):
    """Serve one iteration of the built-in alarm sound (for previews)."""

    url = DEFAULT_SOUND_URL
    name = f"api:{DOMAIN}:default_sound"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: web.Request) -> web.Response:
        """Return the WAV file."""
        data = self._hass.data.get(DATA_DEFAULT_WAV)
        if data is None:
            raise web.HTTPServiceUnavailable
        return web.Response(
            body=data,
            content_type="audio/wav",
            headers={"Cache-Control": "public, max-age=86400"},
        )
