"""LLM tools platform: exposes the Voice Alarms intents to the Assist API."""

from __future__ import annotations

from homeassistant.components.llm import LLMTools
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import intent
from homeassistant.helpers.llm import LLM_API_ASSIST, IntentTool, LLMContext, Tool

from .const import DOMAIN, INTENT_TYPES
from .targets import get_target_for_device

PROMPT = (
    "Alarms and reminders on voice satellites are managed with the voice_alarms__ tools "
    "(set, list, update, skip next, delete, dismiss). Always use them instead of timers for "
    "anything at a clock time or on a date; a duration like 'in 20 minutes' is a timer, not "
    "an alarm. Pass times as 24-hour HH:MM and dates as YYYY-MM-DD ('today', 'tomorrow' and "
    "weekday names are also accepted). Pick alarms with the time, name or date filters; there "
    "is no need to list first to get an id. When the user asks what rings on a particular day "
    "('when will you wake me tomorrow?', 'do I have an alarm on Friday?'), call the list tool "
    "with that date and answer with just the times it reports. After creating or changing an "
    "alarm, tell the user exactly what the tool reported: the time, the days, the date of the "
    "next ring and the satellite. If the tool reports an error or asks a question, relay it."
)


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
    prompt = PROMPT
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
