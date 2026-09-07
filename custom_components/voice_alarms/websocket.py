"""Websocket API used by the Voice Alarms panel."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    DOMAIN,
    SIGNAL_ALARMS_UPDATED,
    SIGNAL_RINGING_UPDATED,
    SIGNAL_TARGETS_UPDATED,
)
from .manager import AlarmManager


@callback
def async_register_websocket(hass: HomeAssistant, get_manager) -> None:
    """Register websocket commands.

    ``get_manager`` returns the current AlarmManager (or None when unloaded) so
    that the commands survive config entry reloads.
    """

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe"})
    @callback
    def subscribe(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        manager: AlarmManager | None = get_manager()
        if manager is None:
            connection.send_error(msg["id"], "not_loaded", "Voice Alarms is not loaded")
            return

        @callback
        def push() -> None:
            current = get_manager()
            if current is None:
                return
            connection.send_message(websocket_api.event_message(msg["id"], current.snapshot()))

        unsubs = [
            async_dispatcher_connect(hass, SIGNAL_ALARMS_UPDATED, push),
            async_dispatcher_connect(hass, SIGNAL_RINGING_UPDATED, push),
            async_dispatcher_connect(hass, SIGNAL_TARGETS_UPDATED, push),
        ]

        @callback
        def unsubscribe() -> None:
            for unsub in unsubs:
                unsub()

        connection.subscriptions[msg["id"]] = unsubscribe
        connection.send_result(msg["id"])
        push()

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/snapshot"})
    @callback
    def snapshot(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        manager: AlarmManager | None = get_manager()
        if manager is None:
            connection.send_error(msg["id"], "not_loaded", "Voice Alarms is not loaded")
            return
        connection.send_result(msg["id"], manager.snapshot())

    websocket_api.async_register_command(hass, subscribe)
    websocket_api.async_register_command(hass, snapshot)
