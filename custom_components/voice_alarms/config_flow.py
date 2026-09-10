"""Config flow for Voice Alarms."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import media_source
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .const import (
    CONF_ALARM_VOLUME,
    CONF_DEFAULT_DURATION,
    CONF_DEFAULT_SOUND,
    CONF_DEVICE_STOP_PAUSE,
    CONF_MISSED_GRACE,
    CONF_RAMP_CURVE,
    CONF_RAMP_SECONDS,
    CONF_RAMP_START,
    CONF_REMINDER_INTERVAL,
    CONF_REMINDER_REPEATS,
    DEFAULT_DEVICE_STOP_PAUSE,
    DEFAULT_DURATION,
    DEFAULT_MISSED_GRACE,
    DEFAULT_RAMP_SECONDS,
    DEFAULT_RAMP_START,
    DEFAULT_REMINDER_INTERVAL,
    DEFAULT_REMINDER_REPEATS,
    DOMAIN,
)


def _number(
    minimum: float, maximum: float, step: float = 1, unit: str | None = None
) -> NumberSelector:
    config = NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


# Options without a form field: they are edited in the panel and must survive
# a save of this form, which otherwise replaces all options.
PANEL_OPTIONS = (CONF_RAMP_CURVE,)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DEFAULT_DURATION, default=DEFAULT_DURATION): _number(5, 3600, 5, "s"),
        vol.Optional(CONF_RAMP_SECONDS, default=DEFAULT_RAMP_SECONDS): _number(0, 300, 1, "s"),
        vol.Optional(CONF_RAMP_START, default=DEFAULT_RAMP_START): _number(0, 100, 1, "%"),
        vol.Optional(CONF_ALARM_VOLUME): _number(0, 100, 1, "%"),
        vol.Optional(CONF_DEFAULT_SOUND): TextSelector(),
        vol.Optional(CONF_REMINDER_REPEATS, default=DEFAULT_REMINDER_REPEATS): _number(1, 20),
        vol.Optional(CONF_REMINDER_INTERVAL, default=DEFAULT_REMINDER_INTERVAL): _number(
            5, 900, 5, "s"
        ),
        vol.Optional(CONF_MISSED_GRACE, default=DEFAULT_MISSED_GRACE): _number(0, 3600, 10, "s"),
        vol.Optional(CONF_DEVICE_STOP_PAUSE, default=DEFAULT_DEVICE_STOP_PAUSE): _number(
            0, 900, 5, "s"
        ),
    }
)


def _validate(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    sound = (user_input.get(CONF_DEFAULT_SOUND) or "").strip()
    if sound:
        if not (
            media_source.is_media_source_id(sound) or sound.startswith(("http://", "https://", "/"))
        ):
            errors[CONF_DEFAULT_SOUND] = "invalid_sound"
        user_input[CONF_DEFAULT_SOUND] = sound
    else:
        user_input.pop(CONF_DEFAULT_SOUND, None)
    if user_input.get(CONF_ALARM_VOLUME) in (None, ""):
        user_input.pop(CONF_ALARM_VOLUME, None)
    return errors


class VoiceAlarmsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the (single instance) config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Create the entry with initial options."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(title="Voice Alarms", data={}, options=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> VoiceAlarmsOptionsFlow:
        """Options flow."""
        return VoiceAlarmsOptionsFlow()


class VoiceAlarmsOptionsFlow(OptionsFlowWithReload):
    """Edit options; the entry reloads automatically afterwards."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show / save the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                options = self.config_entry.options
                kept = {key: options[key] for key in PANEL_OPTIONS if key in options}
                return self.async_create_entry(data={**kept, **user_input})
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, user_input if user_input is not None else self.config_entry.options
            ),
            errors=errors,
        )
