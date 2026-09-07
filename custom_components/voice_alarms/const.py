"""Constants for the Voice Alarms integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "voice_alarms"

PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

STORAGE_KEY: Final = f"{DOMAIN}.alarms"
STORAGE_VERSION: Final = 1

# Options (all stored in the config entry options)
CONF_DEFAULT_DURATION: Final = "default_duration"  # seconds
CONF_RAMP_SECONDS: Final = "ramp_seconds"
CONF_RAMP_START: Final = "ramp_start"  # percent of full level at t=0
CONF_ALARM_VOLUME: Final = "alarm_volume"  # percent, optional
CONF_DEFAULT_SOUND: Final = "default_sound"  # url / media-source id, "" = built-in
CONF_REMINDER_REPEATS: Final = "reminder_repeats"
CONF_REMINDER_INTERVAL: Final = "reminder_interval"  # seconds
CONF_MISSED_GRACE: Final = "missed_grace"  # seconds
CONF_DEVICE_STOP_PAUSE: Final = "device_stop_pause"  # seconds, 0 = dismiss

DEFAULT_DURATION: Final = 300
DEFAULT_RAMP_SECONDS: Final = 30
DEFAULT_RAMP_START: Final = 10
DEFAULT_REMINDER_REPEATS: Final = 3
DEFAULT_REMINDER_INTERVAL: Final = 60
DEFAULT_MISSED_GRACE: Final = 600
DEFAULT_DEVICE_STOP_PAUSE: Final = 0
DEFAULT_TEST_DURATION: Final = 20

# Alarm kinds
KIND_ALARM: Final = "alarm"
KIND_REMINDER: Final = "reminder"
KINDS: Final = [KIND_ALARM, KIND_REMINDER]

WEEKDAY_CODES: Final = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAY_NAMES: Final = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

# Audio
SAMPLE_RATE: Final = 44100
# Samples per FLAC frame of the streamed alarm audio.
FLAC_BLOCK_SIZE: Final = 4096
STREAM_CHUNK_SECONDS: Final = 0.25
STREAM_LEAD_SECONDS: Final = 2.0
# ESPHome waits at most 5 minutes for an announcement, so keep segments shorter.
MAX_SEGMENT_SECONDS: Final = 240
# Announcements that end faster than this after the stream was opened are
# treated as playback errors rather than a deliberate stop on the device.
MIN_PLAYBACK_FOR_DEVICE_STOP: Final = 3.0
ANNOUNCE_RETRY_SECONDS: Final = 5.0
RECENTLY_DISMISSED_SECONDS: Final = 180

# Dispatcher signals
SIGNAL_ALARMS_UPDATED: Final = f"{DOMAIN}_alarms_updated"
SIGNAL_TARGETS_UPDATED: Final = f"{DOMAIN}_targets_updated"
SIGNAL_RINGING_UPDATED: Final = f"{DOMAIN}_ringing_updated"

# HTTP
STREAM_URL_BASE: Final = f"/api/{DOMAIN}/stream"
DEFAULT_SOUND_URL: Final = f"/api/{DOMAIN}/sound/default.wav"
PANEL_URL_PATH: Final = "voice-alarms"
PANEL_STATIC_URL: Final = f"/{DOMAIN}_panel"

# Intents
INTENT_SET: Final = "VoiceAlarmSet"
INTENT_LIST: Final = "VoiceAlarmList"
INTENT_DELETE: Final = "VoiceAlarmDelete"
INTENT_SKIP_NEXT: Final = "VoiceAlarmSkipNext"
INTENT_UPDATE: Final = "VoiceAlarmUpdate"
INTENT_DISMISS: Final = "VoiceAlarmDismiss"
INTENT_TYPES: Final = [
    INTENT_SET,
    INTENT_LIST,
    INTENT_DELETE,
    INTENT_SKIP_NEXT,
    INTENT_UPDATE,
    INTENT_DISMISS,
]

# Services
SERVICE_ADD_ALARM: Final = "add_alarm"
SERVICE_UPDATE_ALARM: Final = "update_alarm"
SERVICE_DELETE_ALARM: Final = "delete_alarm"
SERVICE_SKIP_NEXT: Final = "skip_next"
SERVICE_DISMISS: Final = "dismiss"
SERVICE_SNOOZE: Final = "snooze"
SERVICE_LIST_ALARMS: Final = "list_alarms"
SERVICE_TEST_ALARM: Final = "test_alarm"

ATTR_ALARM_ID: Final = "alarm_id"
ATTR_TARGET: Final = "target"
ATTR_TIME: Final = "time"
ATTR_DATE: Final = "date"
ATTR_WEEKDAYS: Final = "weekdays"
ATTR_NAME: Final = "name"
ATTR_MESSAGE: Final = "message"
ATTR_DURATION: Final = "duration"
ATTR_SOUND: Final = "sound"
ATTR_ENABLED: Final = "enabled"
ATTR_UNDO: Final = "undo"
ATTR_MINUTES: Final = "minutes"
