# Voice Alarms for Home Assistant

<img src="custom_components/voice_alarms/brand/icon.png" alt="Voice Alarms icon" width="96" align="right">

[![ci](https://github.com/Gamer92000/hass_alarm/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Gamer92000/hass_alarm/actions/workflows/ci.yml)

<!-- ha-marketplace:exclude-start -->
[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Gamer92000&repository=hass_alarm&category=integration)
<!-- ha-marketplace:exclude-end -->
[![Open your Home Assistant instance and start setting up the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=voice_alarms)

Alarms and reminders that ring on your **Assist voice satellites** (Home Assistant Voice PE,
ESPHome satellites, Wyoming satellites, …), managed by voice through your LLM conversation
agent or through a panel in the Home Assistant UI.

**Requires Home Assistant 2026.11 or newer.** It is installed through the Marketplace
that Home Assistant 2026.11 has built in (the successor of HACS); older versions are not
supported.

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
  An alarm whose satellite is offline (unavailable in Home Assistant, and its media player too)
  waits for it within that period. Satellites that do not report being offline, such as
  Wyoming ones, cannot be waited for.
- English and German throughout: panel, config flow, entities, services and the spoken
  responses.

## Installation

<!-- ha-marketplace:exclude-start -->
**Marketplace (recommended):** click the *Open in Marketplace* button above, or go to
*Settings → Marketplace → Add from link* and enter `Gamer92000/hass_alarm`. Then install
it. Updates arrive through the Marketplace as well and need a restart of Home Assistant.

**Manual:** copy `custom_components/voice_alarms` into your Home Assistant
`config/custom_components/` folder and restart Home Assistant.
<!-- ha-marketplace:exclude-end -->

Then:

1. *Settings → Devices & services → Add integration → Voice Alarms* (or click the *Add
   integration* button above). The dialog shows the options described below; everything can
   be changed later via *Configure*.
2. Open the **Voice Alarms** entry in the sidebar.

`ffmpeg` (present on Home Assistant OS / container) is only needed for the volume ramp on
*custom* sounds. The built-in sound never needs it.

## Voice control

The integration contributes tools to the Assist LLM API, so any LLM conversation agent
(OpenAI, Anthropic, Ollama, Google, …) that has *Assist* enabled as its API gets them
automatically. No extra configuration is needed. Examples:

| You say | What happens |
| --- | --- |
| "Wake me at 6:30" | One-time alarm on this satellite, tomorrow (or today if still ahead). |
| "Wake me at 8" | At 08:00, tomorrow or today. With the option *time without morning or evening*, at 08:00 or 20:00, whichever comes first. |
| "Set an alarm for 7 on weekdays called work" | Repeating alarm Mon–Fri. |
| "Set an alarm for 8 tomorrow in the bedroom" | Target another satellite by name or area. |
| "Remind me at 5 pm to call mom" | Spoken reminder. |
| "Skip tomorrow's alarm" / "Don't wake me tomorrow" | Skips only the next occurrence (all alarms of that wake-up if you have several). |
| "Move my work alarm to 6:45" / "Disable all my alarms" | Updates the alarm(s). |
| "What alarms do I have?" | Lists everything with the next ring time. |
| "When will you wake me tomorrow?" | Just the times that ring that day, e.g. *"08:45, 08:50 and 09:00"*. |
| "Delete the 7 o'clock alarm" | Deletes it (asks if several match). |
| "Stop" / "Dismiss the alarm" / "Snooze for 10 minutes" | Stops (or snoozes) the ringing alarm. |

The tool responses are precise sentences such as
*"Created repeating alarm 'work' at 06:30 weekdays on Kitchen, next tomorrow (Tuesday 8
September) at 06:30 (in 20 hours and 12 minutes)."* and the LLM is instructed to relay them.

Responses are given in the language of the conversation. English and German are built in;
any other language gets English, which the LLM translates. The parsers also understand
German words (*morgen*, *übermorgen*, *wochentags*, *montag*, *7 Uhr*, …). Everything tied
to the instance rather than to a conversation follows the Home Assistant language setting:
the default alarm labels ("Wecker 07:00"), the spoken *Erinnerung:* prefix of reminders,
snooze names and service errors.

The built-in (non-LLM) Assist agent does not have sentences for these intents out of the
box. You can add your own under `custom_sentences/<lang>/voice_alarms.yaml` targeting the
intents `VoiceAlarmSet`, `VoiceAlarmList`, `VoiceAlarmDelete`, `VoiceAlarmSkipNext`,
`VoiceAlarmUpdate` and `VoiceAlarmDismiss`.

### Stopping an alarm on the device

On Home Assistant Voice PE the wake word, the built-in "stop" word and the button stop the
announcement on the device itself. By default the integration treats that as dismissing
the alarm. If you prefer "silence for a moment, then ring again unless dismissed", set
*resume ringing after* in the options to a number of seconds. Playback that ends within
1.5 s of the satellite fetching the sound counts as a playback error, not a stop, and the
alarm rings again 5 s later.

## How ringing works

At alarm time the integration calls `assist_satellite.announce` with a URL to an audio
stream it generates itself. The stream is a real-time paced FLAC stream (the format Voice PE
decodes natively) that loops the alarm sound for the configured duration with the volume ramp
applied in the audio, so it works on every satellite type without depending on media-player
volume control. The ramp follows a cubic bezier easing curve, so it starts and ends gently
instead of kinking; ffmpeg gets it as a piecewise-linear `volume` expression. Dismissing cuts the stream,
which stops playback within a couple of seconds. If the satellite has a media player
(Voice PE does), the satellite volume can additionally be set to a fixed level while ringing
and is restored afterwards.

When several things are due on one satellite at once, alarms that fire while an alarm rings
join it, and reminders join a reminder that is being spoken. A reminder due while an alarm
rings is spoken once the alarm is over; an alarm due while a reminder is spoken takes over,
and the reminder is repeated after it. A test ring never interrupts anything and is
interrupted by anything that is due.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| Ring duration | 300 s | How long an alarm rings before it stops by itself. Can be overridden per alarm. |
| Volume ramp-up time | 30 s | Time to reach full loudness. |
| Start level of the ramp | 10 % | Loudness at the beginning of the ramp. |
| Ramp curve | ease in-out | Shape of the ramp as a cubic bezier easing (like CSS `cubic-bezier`). Edited graphically in the panel: *Settings → Edit ramp*, with drag handles, presets and an audible preview. |
| Satellite volume while ringing | *(empty)* | If set, the satellite media player is set to this volume during the alarm and restored afterwards. |
| Alarm sound | built-in | http(s) URL, `/local/...` path or `media-source://media_source/local/file.mp3` (also for the per-alarm sound; downloads for ffmpeg are capped at 20 MB). Can be overridden per alarm. |
| Reminder repeats / pause | 3 × 60 s | How often and how spaced a reminder is spoken. |
| Missed alarm grace | 600 s | An alarm that was missed by less than this (restart, downtime, satellite offline) still rings. With 0, only alarms on time ring. |
| Resume ringing after device stop | 0 s | 0 = a stop on the device dismisses the alarm; otherwise the alarm pauses that many seconds and rings again. |
| Time without morning or evening | off | Off: "at 8" is 08:00. On: a time from 1 to 12 o'clock said without morning, evening, am or pm ("at 8", "at 10:30", "um 8 Uhr", "às 7h30") rings at whichever of the morning and the evening time comes first, so "wake me at 8" said at 10:00 rings at 20:00. A day ("tomorrow at 8") or repeat days keep the morning, and so does a time with a leading zero ("08:00"). The same holds for moving an alarm to a new time, and "my alarm at 8" finds the alarm at 08:00 and the one at 20:00. |

## Services

All services live in the `voice_alarms` domain and are documented in the UI
(*Developer tools → Actions*):

- `add_alarm` (target, time, date, weekdays, name, message, kind, duration, sound, enabled) → returns the alarm
- `update_alarm` (alarm_id + any of the above; `duration: 0` goes back to the default)
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

Python 3.14 is required (Home Assistant needs >= 3.14.2). The pinned test
environment is in `requirements_test.txt`; CI runs exactly this:

```bash
uv venv .venv --python 3.14 && . .venv/bin/activate
uv pip install -r requirements_test.txt
ruff check custom_components tests tools && ruff format --check custom_components tests tools
pytest
```

The tests exercise scheduling (including DST-safe local times, skipping and missed-alarm
catch-up), the intents, the LLM tool exposure, the audio stream and the services.

## License

MIT, see [LICENSE](LICENSE). The panel's icon paths come from
[Material Design Icons](https://pictogrammers.com/library/mdi/) (Apache-2.0).
