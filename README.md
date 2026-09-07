# Voice Alarms for Home Assistant

[![ci](https://git.imhof.cloud/julian/hass_alarm/actions/workflows/ci.yml/badge.svg?branch=main)](https://git.imhof.cloud/julian/hass_alarm/actions)

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Gamer92000&repository=hass_alarm&category=integration)
[![Open your Home Assistant instance and start setting up the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=voice_alarms)

Alarms and reminders that ring on your **Assist voice satellites** (Home Assistant Voice PE,
ESPHome satellites, Wyoming satellites, …), managed by voice through your LLM conversation
agent or through a panel in the Home Assistant UI.

**Requires Home Assistant 2026.9 or newer.** No older versions are supported: the
integration relies on the LLM tools platform introduced in 2026.8 and the current
`assist_satellite.announce` API.

## Features

- Unlimited alarms and reminders, one-time or repeating on chosen weekdays.
- Skip only the next occurrence of a repeating alarm (and reinstate it).
- Voice control through the Assist LLM API: set, list, change, skip, delete, dismiss and
  snooze. The satellite you are talking to is the default target; any other satellite can
  be named. Every voice action answers with exactly what changed.
- Web UI: a **Voice Alarms** sidebar panel to create, edit, enable/disable, skip and delete
  alarms; the target satellite must be chosen explicitly there.
- Services and entities for automations: per satellite a *Next alarm* sensor, a *Ringing*
  binary sensor and *Dismiss* / *Test* buttons; per alarm a switch to enable or disable it.
- Alarms ring for a configurable duration (default 5 minutes) and fade in over the first
  30 seconds (both configurable).
- Built-in bell sound; any URL or `media-source://` file can be used instead, globally or
  per alarm.
- Reminders are spoken (text-to-speech) instead of ringing, repeated a few times.
- Missed alarms (e.g. Home Assistant restarted at alarm time) still ring within a grace period.

## Installation

**HACS (recommended):** click the *Open in HACS* button above, or add
`https://github.com/Gamer92000/hass_alarm` in HACS as a custom repository of type
*Integration*. Install it, then restart Home Assistant.

**Manual:** copy `custom_components/voice_alarms` into your Home Assistant
`config/custom_components/` folder and restart Home Assistant.

Then:

1. *Settings → Devices & services → Add integration → Voice Alarms* (or click the *Add
   integration* button above). The dialog shows the options described below; everything can
   be changed later via *Configure*.
2. Open the **Voice Alarms** entry in the sidebar.

The GitHub repository is a read-only mirror kept for HACS. Development, issues and pull
requests live at <https://git.imhof.cloud/julian/hass_alarm>.

`ffmpeg` (present on Home Assistant OS / container) is only needed for the volume ramp on
*custom* sounds. The built-in sound never needs it.

## Voice control

The integration contributes tools to the Assist LLM API, so any LLM conversation agent
(OpenAI, Anthropic, Ollama, Google, …) that has *Assist* enabled as its API gets them
automatically. No extra configuration is needed. Examples:

| You say | What happens |
| --- | --- |
| "Wake me at 6:30" | One-time alarm on this satellite, tomorrow (or today if still ahead). |
| "Set an alarm for 7 on weekdays called work" | Repeating alarm Mon–Fri. |
| "Set an alarm for 8 tomorrow in the bedroom" | Target another satellite by name or area. |
| "Remind me at 5 pm to call mom" | Spoken reminder. |
| "Skip tomorrow's alarm" / "Don't wake me tomorrow" | Skips only the next occurrence. |
| "Move my work alarm to 6:45" / "Disable the work alarm" | Updates the alarm. |
| "What alarms do I have?" | Lists everything with the next ring time. |
| "Delete the 7 o'clock alarm" | Deletes it (asks if several match). |
| "Stop" / "Dismiss the alarm" / "Snooze for 10 minutes" | Stops (or snoozes) the ringing alarm. |

The tool responses are precise sentences such as
*"Created repeating alarm 'work' at 06:30 weekdays on Kitchen, next tomorrow (Tuesday 8
September) at 06:30 (in 20 hours and 12 minutes)."* and the LLM is instructed to relay them.

The built-in (non-LLM) Assist agent does not have sentences for these intents out of the
box. You can add your own under `custom_sentences/<lang>/voice_alarms.yaml` targeting the
intents `VoiceAlarmSet`, `VoiceAlarmList`, `VoiceAlarmDelete`, `VoiceAlarmSkipNext`,
`VoiceAlarmUpdate` and `VoiceAlarmDismiss`.

### Stopping an alarm on the device

On Home Assistant Voice PE the wake word, the built-in "stop" word and the button stop the
announcement on the device itself. By default the integration treats that as dismissing
the alarm. If you prefer "silence for a moment, then ring again unless dismissed", set
*resume ringing after* in the options to a number of seconds.

## How ringing works

At alarm time the integration calls `assist_satellite.announce` with a URL to an audio
stream it generates itself. The stream is a real-time paced WAV that loops the alarm sound
for the configured duration with the volume ramp applied in the audio, so it works on every
satellite type without depending on media-player volume control. Dismissing cuts the stream,
which stops playback within a couple of seconds. If the satellite has a media player
(Voice PE does), the satellite volume can additionally be set to a fixed level while ringing
and is restored afterwards.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| Ring duration | 300 s | How long an alarm rings before it stops by itself. Can be overridden per alarm. |
| Volume ramp-up time | 30 s | Time to reach full loudness. |
| Start level of the ramp | 10 % | Loudness at the beginning of the ramp. |
| Satellite volume while ringing | *(empty)* | If set, the satellite media player is set to this volume during the alarm and restored afterwards. |
| Alarm sound | built-in | URL, `/local/...` path or `media-source://media_source/local/file.mp3`. Can be overridden per alarm. |
| Reminder repeats / pause | 3 × 60 s | How often and how spaced a reminder is spoken. |
| Missed alarm grace | 600 s | An alarm that was missed by less than this (restart, downtime) still rings. |
| Resume ringing after device stop | 0 s | 0 = a stop on the device dismisses the alarm; otherwise the alarm pauses that many seconds and rings again. |

## Services

All services live in the `voice_alarms` domain and are documented in the UI
(*Developer tools → Actions*):

- `add_alarm` (target, time, date, weekdays, name, message, kind, duration, sound, enabled) → returns the alarm
- `update_alarm` (alarm_id + any of the above)
- `delete_alarm` (alarm_id)
- `skip_next` (alarm_id, undo)
- `dismiss` (target, optional)
- `snooze` (target, minutes)
- `list_alarms` → returns alarms and what is ringing
- `test_alarm` (target, duration, sound, message) — rings the sound (or speaks a reminder) now

Example automation call:

```yaml
action: voice_alarms.add_alarm
data:
  target: assist_satellite.home_assistant_voice_kitchen_assist_satellite
  time: "06:30"
  weekdays: [mon, tue, wed, thu, fri]
  name: Work
```

## Entities

Per satellite (grouped under a *Voice Alarms &lt;satellite&gt;* device):

- `sensor.<satellite>_next_alarm` — timestamp of the next alarm, with the full alarm list as attributes
- `binary_sensor.<satellite>_ringing` — on while ringing (attributes describe the session)
- `button.<satellite>_dismiss_alarm`, `button.<satellite>_test_alarm_sound`

Per alarm: `switch.<label>` to enable or disable it (attributes contain all alarm fields).

## Development

Python 3.14 is required (Home Assistant 2026.9 needs it). The pinned test
environment is in `requirements_test.txt`; CI runs exactly this:

```bash
uv venv .venv --python 3.14 && . .venv/bin/activate
uv pip install -r requirements_test.txt
ruff check custom_components tests tools && ruff format --check custom_components tests tools
pytest
```

The tests exercise scheduling (including DST-safe local times, skipping and missed-alarm
catch-up), the intents, the LLM tool exposure, the audio stream and the services.
