"""LLM tools platform: exposes the Voice Alarms intents to the Assist API."""

from __future__ import annotations

from homeassistant.components.llm import LLMTools
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import intent
from homeassistant.helpers.llm import LLM_API_ASSIST, IntentTool, LLMContext, Tool

from . import DATA_MANAGER
from .const import DOMAIN, INTENT_TYPES
from .targets import get_target_for_device

_TIMES = (
    "Pass times as 24-hour HH:MM and dates as YYYY-MM-DD ('today', 'tomorrow' and "
    "weekday names are also accepted). "
)
_TIMES_TWELVE_HOUR = (
    "Pass a time from 1 to 12 o'clock said without morning, evening, am or pm exactly as "
    "said ('8', '10:30'): the tools pick the morning or the evening time, so do not pick one "
    "yourself. When the user does say morning, evening, am or pm, always add am or pm "
    "('10:30 in the morning' is '10:30 am', never '10:30'; '8 in the evening' is '8 pm'). "
    "Pass a time from 13 to 23 o'clock as 24-hour HH:MM ('20:00'), and dates as YYYY-MM-DD "
    "('today', 'tomorrow' and weekday names are also accepted). "
)


def _prompt(times: str) -> str:
    return (
        "Alarms and reminders on voice satellites are managed with the voice_alarms__ tools "
        "(set, list, update, skip next, delete, dismiss). Always use them instead of timers "
        "for anything at a clock time or on a date; a duration like 'in 20 minutes' is a "
        "timer, not an alarm. " + times + "Pick alarms with the time, name or date filters; "
        "there is no need to list first to get an id. When the user asks what rings on a "
        "particular day ('when will you wake me tomorrow?', 'do I have an alarm on Friday?'), "
        "call the list tool with that date and answer with just the times it reports. After "
        "creating or changing an alarm, tell the user exactly what the tool reported: the "
        "time, the days, the date of the next ring and the satellite. If the tool reports an "
        "error or asks a question, relay it."
    )


PROMPT = _prompt(_TIMES)
PROMPT_TWELVE_HOUR = _prompt(_TIMES_TWELVE_HOUR)


@callback
def async_get_tools(hass: HomeAssistant, llm_context: LLMContext, api_id: str) -> LLMTools | None:
    """Return the alarm tools for the Assist API."""
    if api_id != LLM_API_ASSIST:
        return None
    wanted = set(INTENT_TYPES)
    tools: list[Tool] = [
        IntentTool(f"{DOMAIN}__{handler.intent_type}", handler)
        for handler in intent.async_get(hass)
        if handler.intent_type in wanted
    ]
    if not tools:
        return None
    # HA 2026.10 wants every tool to name its integration (required from 2027.10).
    # Set the attribute rather than the IntentTool kwarg, which 2026.9 lacks.
    for tool in tools:
        tool.integration = DOMAIN
    manager = hass.data.get(DATA_MANAGER)
    prompt = PROMPT_TWELVE_HOUR if manager is not None and manager.twelve_hour else PROMPT
    target = get_target_for_device(hass, llm_context.device_id)
    if target is not None:
        prompt += (
            f" The user is speaking through the voice satellite '{target.display}'; alarms "
            "default to it unless another satellite is named."
        )
    else:
        prompt += (
            " The user is not speaking through a voice satellite, so ask which satellite an "
            "alarm should ring on (or pass target) if the tool asks for one."
        )
    return LLMTools(tools=tools, prompt=prompt)
