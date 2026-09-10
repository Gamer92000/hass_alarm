"""Services for Voice Alarms."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.assist_satellite import DOMAIN as ASSIST_SATELLITE_DOMAIN
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ALARM_ID,
    ATTR_DATE,
    ATTR_DURATION,
    ATTR_ENABLED,
    ATTR_MESSAGE,
    ATTR_MINUTES,
    ATTR_NAME,
    ATTR_SOUND,
    ATTR_TARGET,
    ATTR_TIME,
    ATTR_UNDO,
    ATTR_WEEKDAYS,
    DEFAULT_TEST_DURATION,
    DOMAIN,
    KIND_ALARM,
    KIND_REMINDER,
    KINDS,
    SERVICE_ADD_ALARM,
    SERVICE_DELETE_ALARM,
    SERVICE_DISMISS,
    SERVICE_LIST_ALARMS,
    SERVICE_SKIP_NEXT,
    SERVICE_SNOOZE,
    SERVICE_TEST_ALARM,
    SERVICE_UPDATE_ALARM,
)
from .i18n import LocalizedError, default_language
from .manager import AlarmError, AlarmManager
from .models import ParseError, parse_date, parse_time, parse_weekdays

SERVICES = [
    SERVICE_ADD_ALARM,
    SERVICE_UPDATE_ALARM,
    SERVICE_DELETE_ALARM,
    SERVICE_SKIP_NEXT,
    SERVICE_DISMISS,
    SERVICE_SNOOZE,
    SERVICE_LIST_ALARMS,
    SERVICE_TEST_ALARM,
]

_TARGET = cv.entity_domain(ASSIST_SATELLITE_DOMAIN)
_WEEKDAYS = vol.Any(cv.string, [vol.Any(cv.string, vol.All(int, vol.Range(0, 6)))])
_ALARM_FIELDS = {
    vol.Optional(ATTR_DATE): cv.string,
    vol.Optional(ATTR_WEEKDAYS): _WEEKDAYS,
    vol.Optional(ATTR_NAME): cv.string,
    vol.Optional(ATTR_MESSAGE): cv.string,
    vol.Optional("kind"): vol.In(KINDS),
    vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(int), vol.Range(min=1, max=86400)),
    vol.Optional(ATTR_SOUND): cv.string,
    vol.Optional(ATTR_ENABLED): cv.boolean,
}

ADD_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TARGET): _TARGET,
        vol.Required(ATTR_TIME): cv.string,
        **_ALARM_FIELDS,
    }
)
UPDATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ALARM_ID): cv.string,
        vol.Optional(ATTR_TARGET): _TARGET,
        vol.Optional(ATTR_TIME): cv.string,
        **_ALARM_FIELDS,
    }
)
DELETE_SCHEMA = vol.Schema({vol.Required(ATTR_ALARM_ID): cv.string})
SKIP_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ALARM_ID): cv.string, vol.Optional(ATTR_UNDO, default=False): cv.boolean}
)
DISMISS_SCHEMA = vol.Schema({vol.Optional(ATTR_TARGET): _TARGET})
SNOOZE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_TARGET): _TARGET,
        vol.Optional(ATTR_MINUTES, default=9): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
    }
)
TEST_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TARGET): _TARGET,
        vol.Optional(ATTR_DURATION, default=DEFAULT_TEST_DURATION): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=3600)
        ),
        vol.Optional(ATTR_SOUND): cv.string,
        vol.Optional(ATTR_MESSAGE): cv.string,
    }
)


def _wrap(err: Exception) -> ServiceValidationError:
    if isinstance(err, LocalizedError):
        return ServiceValidationError(err.localized(default_language()))
    return ServiceValidationError(str(err))


def _parsed_fields(call: ServiceCall) -> dict[str, Any]:
    """Turn raw service data into manager arguments."""
    data = call.data
    fields: dict[str, Any] = {}
    try:
        if ATTR_TIME in data:
            fields["time"] = parse_time(data[ATTR_TIME])
        if ATTR_WEEKDAYS in data:
            fields["weekdays"] = parse_weekdays(data[ATTR_WEEKDAYS])
        if ATTR_DATE in data:
            fields["date"] = (
                parse_date(data[ATTR_DATE], dt_util.utcnow()) if data[ATTR_DATE] else None
            )
    except ParseError as err:
        raise _wrap(err) from err
    for key in (
        ATTR_TARGET,
        ATTR_NAME,
        ATTR_MESSAGE,
        "kind",
        ATTR_DURATION,
        ATTR_SOUND,
        ATTR_ENABLED,
    ):
        if key in data:
            fields[key] = data[key]
    return fields


@callback
def async_register_services(hass: HomeAssistant, manager: AlarmManager) -> None:
    """Register all services."""

    async def add_alarm(call: ServiceCall) -> ServiceResponse:
        fields = _parsed_fields(call)
        message = fields.get(ATTR_MESSAGE)
        alarm = manager.build_alarm(
            target=fields[ATTR_TARGET],
            at=fields["time"],
            on_date=fields.get("date"),
            weekdays=fields.get("weekdays"),
            name=fields.get(ATTR_NAME),
            message=message,
            kind=fields.get("kind") or (KIND_REMINDER if message else KIND_ALARM),
            duration=fields.get(ATTR_DURATION),
            sound=fields.get(ATTR_SOUND),
            enabled=fields.get(ATTR_ENABLED, True),
        )
        try:
            alarm = await manager.async_add_alarm(alarm)
        except AlarmError as err:
            raise _wrap(err) from err
        return {"alarm": alarm.public_dict()}

    async def update_alarm(call: ServiceCall) -> ServiceResponse:
        fields = _parsed_fields(call)
        changes = {k: v for k, v in fields.items() if k != ATTR_ALARM_ID}
        if not changes:
            raise ServiceValidationError("Nothing to update")
        try:
            alarm = await manager.async_update_alarm(call.data[ATTR_ALARM_ID], **changes)
        except AlarmError as err:
            raise _wrap(err) from err
        return {"alarm": alarm.public_dict()}

    async def delete_alarm(call: ServiceCall) -> None:
        try:
            await manager.async_delete_alarm(call.data[ATTR_ALARM_ID])
        except AlarmError as err:
            raise _wrap(err) from err

    async def skip_next(call: ServiceCall) -> ServiceResponse:
        try:
            alarm, occurrence = await manager.async_skip_next(
                call.data[ATTR_ALARM_ID], undo=call.data[ATTR_UNDO]
            )
        except AlarmError as err:
            raise _wrap(err) from err
        return {
            "alarm": alarm.public_dict(),
            "occurrence": occurrence.isoformat() if occurrence else None,
        }

    async def dismiss(call: ServiceCall) -> ServiceResponse:
        sessions = await manager.async_dismiss(call.data.get(ATTR_TARGET))
        return {"dismissed": [s.to_dict() for s in sessions]}

    async def snooze(call: ServiceCall) -> ServiceResponse:
        target = call.data.get(ATTR_TARGET)
        if target:
            session = manager.session_for_target(target)
            sessions = [session] if session else []
        else:
            sessions = manager.active_sessions()
        if not sessions:
            raise ServiceValidationError("Nothing is ringing")
        try:
            created = [await manager.async_snooze(s, call.data[ATTR_MINUTES]) for s in sessions]
        except AlarmError as err:
            raise _wrap(err) from err
        return {"alarms": [a.public_dict() for a in created]}

    async def list_alarms(call: ServiceCall) -> ServiceResponse:
        snapshot = manager.snapshot()
        return {"alarms": snapshot["alarms"], "ringing": snapshot["ringing"]}

    async def test_alarm(call: ServiceCall) -> ServiceResponse:
        target = manager.target(call.data[ATTR_TARGET])
        if target is None:
            raise ServiceValidationError(f"Unknown satellite {call.data[ATTR_TARGET]}")
        message = call.data.get(ATTR_MESSAGE)
        session = await manager.async_ring(
            target,
            kind=KIND_REMINDER if message else KIND_ALARM,
            message=message,
            label="Test",
            duration=call.data[ATTR_DURATION],
            sound=call.data.get(ATTR_SOUND),
            origin="test",
        )
        return {"session": session.to_dict()}

    hass.services.async_register(
        DOMAIN, SERVICE_ADD_ALARM, add_alarm, ADD_SCHEMA, SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_ALARM, update_alarm, UPDATE_SCHEMA, SupportsResponse.OPTIONAL
    )
    hass.services.async_register(DOMAIN, SERVICE_DELETE_ALARM, delete_alarm, DELETE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_SKIP_NEXT, skip_next, SKIP_SCHEMA, SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DISMISS, dismiss, DISMISS_SCHEMA, SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SNOOZE, snooze, SNOOZE_SCHEMA, SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LIST_ALARMS, list_alarms, vol.Schema({}), SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN, SERVICE_TEST_ALARM, test_alarm, TEST_SCHEMA, SupportsResponse.OPTIONAL
    )


@callback
def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove all services."""
    for service in SERVICES:
        hass.services.async_remove(DOMAIN, service)
