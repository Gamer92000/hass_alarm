/* Voice Alarms panel: a dependency-free web component served by the
 * voice_alarms integration and registered as a custom sidebar panel. */

const ICONS = {
  alarm:
    "M12,20A7,7 0 0,1 5,13A7,7 0 0,1 12,6A7,7 0 0,1 19,13A7,7 0 0,1 12,20M12,4A9,9 0 0,0 3,13A9,9 0 0,0 12,22A9,9 0 0,0 21,13A9,9 0 0,0 12,4M12.5,8H11V14L15.75,16.85L16.5,15.62L12.5,13.25V8M7.88,3.39L6.6,1.86L2,5.71L3.29,7.24L7.88,3.39M22,5.72L17.4,1.86L16.11,3.39L20.71,7.25L22,5.72Z",
  bell:
    "M21,19V20H3V19L5,17V11C5,7.9 7.03,5.17 10,4.29C10,4.19 10,4.1 10,4A2,2 0 0,1 12,2A2,2 0 0,1 14,4C14,4.1 14,4.19 14,4.29C16.97,5.17 19,7.9 19,11V17L21,19M14,21A2,2 0 0,1 12,23A2,2 0 0,1 10,21M19.75,3.19L18.33,4.61C20.04,6.3 21,8.6 21,11H23C23,8.07 21.84,5.25 19.75,3.19M1,11H3C3,8.6 3.96,6.3 5.67,4.61L4.25,3.19C2.16,5.25 1,8.07 1,11Z",
  plus: "M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z",
  menu: "M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z",
  del: "M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z",
  edit: "M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z",
  skip: "M16,18H18V6H16M6,18L14.5,12L6,6V18Z",
  undo: "M12.5,8C9.85,8 7.45,9 5.6,10.6L2,7V16H11L7.38,12.38C8.77,11.22 10.54,10.5 12.5,10.5C16.04,10.5 19.05,12.81 20.1,16L22.47,15.22C21.08,11.03 17.15,8 12.5,8Z",
  close: "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z",
  play: "M8,5.14V19.14L19,12.14L8,5.14Z",
  stop: "M18,18H6V6H18V18Z",
  speaker:
    "M12,3V9L9,6.5L6,9H2V15H6L9,17.5L12,15V21C12,21 15.5,20.2 17.9,17.8C20.3,15.4 21,12 21,12C21,12 20.3,8.6 17.9,6.2C15.5,3.8 12,3 12,3Z",
};

const DAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

// UI text. The language follows the user's Home Assistant profile (hass.locale); anything
// missing in a language falls back to English. Dates and weekday abbreviations come from
// Intl for the same locale.
const STRINGS = {
  en: {
    menu: "Sidebar",
    add: "Add",
    add_alarm: "Add alarm",
    add_reminder: "Add reminder",
    loading: "Loading…",
    not_loaded: "Voice Alarms is not loaded",
    alarm: "Alarm",
    reminder: "Reminder",
    ringing_on: "{kind} ringing on {target}",
    paused_on: "{kind} paused on {target}",
    snooze5: "Snooze 5 min",
    dismiss: "Dismiss",
    alarms: "Alarms",
    reminders: "Reminders",
    no_alarms: "No alarms yet. Add one here or say “set an alarm for 7” to a satellite.",
    no_reminders: "No reminders yet. Add one here or say “remind me at 6 to take out the trash” to a satellite.",
    satellites: "Satellites",
    no_satellites: "No assist satellites found. Add a Voice PE / Wyoming satellite first.",
    volume_via: "volume via {player}",
    no_media_player: "no media player (volume not controlled)",
    next: "Next: {label} {when}",
    no_upcoming: "No upcoming alarm",
    test: "Test",
    settings: "Settings",
    volume_ramp: "Volume ramp",
    edit_ramp: "Edit ramp",
    ring_duration: "Ring duration {seconds}s",
    satellite_volume: "satellite volume {percent}%",
    satellite_volume_unchanged: "satellite volume unchanged",
    sound: "sound: {sound}",
    built_in: "built-in",
    ffmpeg_missing: " (ffmpeg missing: no ramp)",
    change_hint: "Change these under Settings → Devices &amp; services → Voice Alarms → Configure.",
    preview_label: "Built-in sound preview:",
    disabled: "Disabled",
    next_skipped: "Next occurrence skipped",
    in_past: "In the past",
    unknown_satellite: "Unknown satellite",
    once: "once",
    enabled: "Enabled",
    reinstate_next: "Reinstate next occurrence",
    skip_next: "Skip next occurrence",
    edit: "Edit",
    delete: "Delete",
    confirm_delete: "Delete “{label}”?",
    ramp_help:
      "Drag the round handles to shape the curve and the knob on the left axis to set the start level. The ramp is baked into the alarm audio, so it works on every satellite.",
    ramp_seconds: "Ramp-up time (seconds)",
    ramp_start: "Start level (%)",
    preview_play: "Preview with the built-in sound",
    stop: "Stop",
    cancel: "Cancel",
    save: "Save",
    create: "Create",
    no_web_audio: "This browser has no Web Audio support.",
    preview_failed: "Preview failed: {error}",
    no_ramp: "No ramp: full volume from the start",
    ramp_summary: "From {start}% to 100% over {seconds} · {curve} curve",
    custom: "custom",
    preset_linear: "Linear",
    preset_ease_in: "Ease in",
    preset_ease_out: "Ease out",
    preset_ease_in_out: "Ease in-out",
    type: "Type",
    alarm_rings: "Alarm (rings)",
    reminder_spoken: "Reminder (spoken)",
    time: "Time",
    name: "Name",
    name_placeholder: "e.g. Work",
    message: "Message to speak",
    message_placeholder: "Take out the trash",
    satellite_required: "Satellite (required)",
    choose: "— choose —",
    one_time: "One time",
    repeat_weekly: "Repeat weekly",
    date: "Date",
    days: "Days",
    duration_minutes: "Ring duration (minutes, empty = default)",
    custom_sound: "Custom sound (URL / media-source id)",
    edit_alarm: "Edit alarm",
    new_alarm: "New alarm",
    edit_reminder: "Edit reminder",
    new_reminder: "New reminder",
    choose_satellite: "Choose a satellite.",
    pick_weekday: "Pick at least one weekday.",
    reminder_needs_message: "A reminder needs a message.",
    every_day: "Every day",
    weekdays: "Weekdays",
    weekends: "Weekends",
    rel_under_minute: "in less than a minute",
    rel_min: "in {m} min",
    rel_h: "in {h} h",
    rel_h_min: "in {h} h {m} min",
    rel_d_h: "in {d} d {h} h",
    today: "today",
    tomorrow: "tomorrow",
  },
  de: {
    menu: "Seitenleiste",
    add: "Hinzufügen",
    add_alarm: "Wecker hinzufügen",
    add_reminder: "Erinnerung hinzufügen",
    loading: "Lädt…",
    not_loaded: "Voice Alarms ist nicht geladen",
    alarm: "Wecker",
    reminder: "Erinnerung",
    ringing_on: "{kind} klingelt auf {target}",
    paused_on: "{kind} pausiert auf {target}",
    snooze5: "5 Min. schlummern",
    dismiss: "Beenden",
    alarms: "Wecker",
    reminders: "Erinnerungen",
    no_alarms: "Noch keine Wecker. Lege hier einen an oder sage „Stell einen Wecker auf 7“ zu einem Satelliten.",
    no_reminders: "Noch keine Erinnerungen. Lege hier eine an oder sage „Erinnere mich um 6, den Müll rauszubringen“ zu einem Satelliten.",
    satellites: "Satelliten",
    no_satellites: "Keine Assist-Satelliten gefunden. Richte zuerst einen Voice-PE- oder Wyoming-Satelliten ein.",
    volume_via: "Lautstärke über {player}",
    no_media_player: "kein Media Player (Lautstärke wird nicht gesteuert)",
    next: "Nächster: {label} {when}",
    no_upcoming: "Kein anstehender Wecker",
    test: "Testen",
    settings: "Einstellungen",
    volume_ramp: "Lautstärkerampe",
    edit_ramp: "Rampe bearbeiten",
    ring_duration: "Klingeldauer {seconds}s",
    satellite_volume: "Satellitenlautstärke {percent}%",
    satellite_volume_unchanged: "Satellitenlautstärke unverändert",
    sound: "Ton: {sound}",
    built_in: "eingebaut",
    ffmpeg_missing: " (ffmpeg fehlt: keine Rampe)",
    change_hint: "Ändern unter Einstellungen → Geräte &amp; Dienste → Voice Alarms → Konfigurieren.",
    preview_label: "Vorschau des eingebauten Tons:",
    disabled: "Deaktiviert",
    next_skipped: "Nächster Termin übersprungen",
    in_past: "In der Vergangenheit",
    unknown_satellite: "Unbekannter Satellit",
    once: "einmalig",
    enabled: "Aktiviert",
    reinstate_next: "Nächsten Termin wiederherstellen",
    skip_next: "Nächsten Termin überspringen",
    edit: "Bearbeiten",
    delete: "Löschen",
    confirm_delete: "„{label}“ löschen?",
    ramp_help:
      "Ziehe die runden Griffe, um die Kurve zu formen, und den Knopf an der linken Achse, um den Startpegel zu setzen. Die Rampe wird in das Weck-Audio eingerechnet und funktioniert daher auf jedem Satelliten.",
    ramp_seconds: "Anstiegszeit (Sekunden)",
    ramp_start: "Startpegel (%)",
    preview_play: "Vorschau mit dem eingebauten Ton",
    stop: "Stopp",
    cancel: "Abbrechen",
    save: "Speichern",
    create: "Erstellen",
    no_web_audio: "Dieser Browser unterstützt kein Web Audio.",
    preview_failed: "Vorschau fehlgeschlagen: {error}",
    no_ramp: "Keine Rampe: volle Lautstärke von Anfang an",
    ramp_summary: "Von {start}% auf 100% in {seconds} · Kurve: {curve}",
    custom: "eigene",
    preset_linear: "Linear",
    preset_ease_in: "Ease-in",
    preset_ease_out: "Ease-out",
    preset_ease_in_out: "Ease-in-out",
    type: "Art",
    alarm_rings: "Wecker (klingelt)",
    reminder_spoken: "Erinnerung (gesprochen)",
    time: "Uhrzeit",
    name: "Name",
    name_placeholder: "z. B. Arbeit",
    message: "Zu sprechende Nachricht",
    message_placeholder: "Müll rausbringen",
    satellite_required: "Satellit (erforderlich)",
    choose: "— auswählen —",
    one_time: "Einmalig",
    repeat_weekly: "Wöchentlich wiederholen",
    date: "Datum",
    days: "Tage",
    duration_minutes: "Klingeldauer (Minuten, leer = Standard)",
    custom_sound: "Eigener Ton (URL / media-source-ID)",
    edit_alarm: "Wecker bearbeiten",
    new_alarm: "Neuer Wecker",
    edit_reminder: "Erinnerung bearbeiten",
    new_reminder: "Neue Erinnerung",
    choose_satellite: "Wähle einen Satelliten.",
    pick_weekday: "Wähle mindestens einen Wochentag.",
    reminder_needs_message: "Eine Erinnerung braucht eine Nachricht.",
    every_day: "Täglich",
    weekdays: "Wochentags",
    weekends: "Am Wochenende",
    rel_under_minute: "in weniger als einer Minute",
    rel_min: "in {m} Min.",
    rel_h: "in {h} Std.",
    rel_h_min: "in {h} Std. {m} Min.",
    rel_d_h: "in {d} T. {h} Std.",
    today: "heute",
    tomorrow: "morgen",
  },
};
let LANG = "en";
let LOCALE = "en";
const t = (key, params) => {
  let text = STRINGS[LANG]?.[key] ?? STRINGS.en[key] ?? key;
  if (params) for (const [k, v] of Object.entries(params)) text = text.replaceAll(`{${k}}`, v);
  return text;
};
function setLanguage(locale) {
  LOCALE = locale || "en";
  const code = LOCALE.toLowerCase().split(/[-_]/)[0];
  LANG = code in STRINGS ? code : "en";
}
// Abbreviated weekday names for the locale (2024-01-01 was a Monday).
const dayShort = (i) => new Date(2024, 0, 1 + i).toLocaleDateString(LOCALE, { weekday: "short" });

// Volume ramp: the gain rises from the start level to 100% over ramp_seconds along
// a CSS style cubic-bezier(x1, y1, x2, y2) easing (same maths as audio.py).
const RAMP_PRESETS = [
  ["linear", [0, 0, 1, 1]],
  ["ease_in", [0.42, 0, 1, 1]],
  ["ease_out", [0, 0, 0.58, 1]],
  ["ease_in_out", [0.42, 0, 0.58, 1]],
];
const DEFAULT_RAMP_CURVE = RAMP_PRESETS[3][1];
// Ramp graph geometry in SVG user units: the plot area sits inside the paddings.
const G = { w: 400, h: 190, left: 44, right: 14, top: 16, bottom: 26 };
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const graphX = (x) => G.left + x * (G.w - G.left - G.right);
const graphY = (gain) => G.top + (1 - gain) * (G.h - G.top - G.bottom);

function bezierAt(u, a, b) {
  const v = 1 - u;
  return 3 * v * v * u * a + 3 * v * u * u * b + u * u * u;
}

function bezierEase(x, [x1, y1, x2, y2]) {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  let u = x;
  for (let i = 0; i < 8; i++) {
    const error = bezierAt(u, x1, x2) - x;
    if (Math.abs(error) < 1e-9) break;
    const v = 1 - u;
    const slope = 3 * v * v * x1 + 6 * v * u * (x2 - x1) + 3 * u * u * (1 - x2);
    if (slope < 1e-6) break;
    u -= error / slope;
  }
  if (!(u >= 0 && u <= 1) || Math.abs(bezierAt(u, x1, x2) - x) > 1e-9) {
    let low = 0;
    let high = 1;
    for (let i = 0; i < 50; i++) {
      u = (low + high) / 2;
      if (bezierAt(u, x1, x2) < x) low = u;
      else high = u;
    }
  }
  return bezierAt(u, y1, y2);
}

function rampGain(ramp, t) {
  if (ramp.seconds <= 0 || t >= ramp.seconds) return 1;
  if (t <= 0) return ramp.start;
  return clamp(ramp.start + (1 - ramp.start) * bezierEase(t / ramp.seconds, ramp.curve), 0, 1);
}

function rampFromConfig(config) {
  return {
    seconds: Number(config.ramp_seconds) || 0,
    start: clamp(Number(config.ramp_start) || 0, 0, 1),
    curve: [...(config.ramp_curve || DEFAULT_RAMP_CURVE)],
  };
}

function presetName(curve) {
  const hit = RAMP_PRESETS.find(([, c]) => c.every((v, i) => Math.abs(v - curve[i]) < 0.005));
  return hit ? hit[0] : "";
}

function formatSeconds(s) {
  return `${Math.round(s * 10) / 10} s`;
}

function rampSummary(ramp) {
  if (ramp.seconds <= 0) return t("no_ramp");
  const name = presetName(ramp.curve);
  const curve = name ? t(`preset_${name}`) : t("custom");
  return t("ramp_summary", {
    start: Math.round(ramp.start * 100),
    seconds: formatSeconds(ramp.seconds),
    curve: LANG === "en" ? curve.toLowerCase() : curve,
  });
}

function rampPoints(ramp) {
  const s = ramp.start;
  const [x1, y1, x2, y2] = ramp.curve;
  return {
    p0: [graphX(0), graphY(s)],
    p1: [graphX(x1), graphY(s + (1 - s) * y1)],
    p2: [graphX(x2), graphY(s + (1 - s) * y2)],
    p3: [graphX(1), graphY(1)],
  };
}

function curvePath(ramp) {
  const { p0, p1, p2, p3 } = rampPoints(ramp);
  if (ramp.seconds <= 0) return `M${p0[0]},${p3[1]} L${p3[0]},${p3[1]}`;
  return `M${p0[0]},${p0[1]} C${p1[0]},${p1[1]} ${p2[0]},${p2[1]} ${p3[0]},${p3[1]}`;
}

function rampSvg(ramp, editable) {
  const x0 = graphX(0);
  const x1 = graphX(1);
  const y0 = graphY(0);
  const grid = [0.25, 0.5, 0.75, 1]
    .map((g) => `<line class="grid" x1="${x0}" x2="${x1}" y1="${graphY(g)}" y2="${graphY(g)}"/>`)
    .join("");
  const ticks = [0, 0.25, 0.5, 0.75, 1]
    .map(
      (x) =>
        `<line class="grid" x1="${graphX(x)}" x2="${graphX(x)}" y1="${y0}" y2="${y0 + 4}"/><text x="${graphX(x)}" y="${G.h - 8}" text-anchor="middle" data-tick="${x}">${formatSeconds(x * ramp.seconds)}</text>`
    )
    .join("");
  const labels = [0, 1].map((g) => `<text x="${x0 - 6}" y="${graphY(g) + 4}" text-anchor="end">${g * 100}%</text>`).join("");
  const path = curvePath(ramp);
  const handles = editable
    ? `<line class="arm" data-arm="p1"/><line class="arm" data-arm="p2"/>
      <text class="start-label" x="${x0 + 6}" data-start-label></text>
      <rect class="handle start" width="12" height="12" rx="2" data-handle="p0" data-ox="-17" data-oy="-6"/>
      <circle class="handle" r="8" data-handle="p1"/><circle class="hit" r="18" data-handle="p1"/>
      <circle class="handle" r="8" data-handle="p2"/><circle class="hit" r="18" data-handle="p2"/>
      <rect class="hit start" width="40" height="36" data-handle="p0" data-ox="-42" data-oy="-18"/>
      <line class="playhead" y1="${graphY(1)}" y2="${y0}" style="display:none"/>`
    : "";
  return `<svg class="graph${ramp.seconds <= 0 ? " flat" : ""}" viewBox="0 0 ${G.w} ${G.h}" aria-label="Volume ramp">
    <line class="axis" x1="${x0}" x2="${x1}" y1="${y0}" y2="${y0}"/><line class="axis" x1="${x0}" x2="${x0}" y1="${graphY(1)}" y2="${y0}"/>
    ${grid}${ticks}${labels}<path class="fill" d="${path} L${x1},${y0} L${x0},${y0} Z"/><path class="curve" d="${path}"/>${handles}</svg>`;
}

const STYLE = `
  :host { display: block; height: 100%; overflow: auto; color: var(--primary-text-color); background: var(--primary-background-color); }
  * { box-sizing: border-box; }
  .toolbar { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 12px; height: var(--header-height, 56px); padding: 0 16px; background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); }
  .toolbar h1 { font-size: 20px; font-weight: 400; margin: 0; flex: 1; }
  .toolbar svg { fill: currentColor; }
  .toolbar .menu { flex: none; background: transparent; color: inherit; padding: 8px; margin: 0 4px 0 -8px; border-radius: 50%; }
  .toolbar .menu:hover { background: rgba(255, 255, 255, .15); }
  .fab { position: fixed; right: 16px; bottom: calc(16px + env(safe-area-inset-bottom, 0px)); z-index: 3; height: 48px; padding: 0 20px 0 16px; border-radius: 24px; background: var(--accent-color, #ff9800); color: var(--text-accent-color, var(--text-primary-color, #fff)); box-shadow: 0 3px 5px -1px rgba(0,0,0,.2), 0 6px 10px 0 rgba(0,0,0,.14), 0 1px 18px 0 rgba(0,0,0,.12); }
  .fab svg { fill: currentColor; }
  main.narrow { padding-bottom: 88px; }
  main { max-width: 960px; margin: 0 auto; padding: 16px; }
  .card { background: var(--card-background-color, #fff); border-radius: var(--ha-card-border-radius, 12px); box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,.15)); border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0)); padding: 16px; margin-bottom: 12px; }
  .card.ringing { border-color: var(--error-color, #db4437); background: color-mix(in srgb, var(--error-color, #db4437) 10%, var(--card-background-color, #fff)); }
  .card.disabled { opacity: .6; }
  h2 { font-size: 16px; font-weight: 500; margin: 20px 0 8px; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .5px; }
  .row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .time { font-size: 34px; font-weight: 300; line-height: 1; min-width: 96px; }
  .grow { flex: 1 1 160px; min-width: 0; overflow-wrap: anywhere; }
  .label { font-size: 16px; font-weight: 500; }
  .sub { color: var(--secondary-text-color); font-size: 14px; margin-top: 2px; }
  .message { font-size: 15px; font-style: italic; margin-top: 2px; }
  .card.reminder .time { color: var(--primary-color); }
  .badges { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
  .badge { font-size: 12px; padding: 2px 8px; border-radius: 10px; background: var(--secondary-background-color, #eee); color: var(--secondary-text-color); }
  .badge.warn { background: var(--warning-color, #ffa600); color: #000; }
  .badge.err { background: var(--error-color, #db4437); color: #fff; }
  .badge.info { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .actions { display: flex; gap: 4px; align-items: center; flex: none; }
  button { font: inherit; cursor: pointer; border: none; border-radius: 8px; padding: 8px 12px; background: var(--primary-color); color: var(--text-primary-color, #fff); display: inline-flex; align-items: center; gap: 6px; }
  button.icon { background: transparent; color: var(--secondary-text-color); padding: 6px; border-radius: 50%; }
  button.icon:hover { background: var(--secondary-background-color, #eee); color: var(--primary-text-color); }
  button.danger { background: var(--error-color, #db4437); }
  button.ghost { background: transparent; color: var(--primary-color); border: 1px solid var(--primary-color); }
  button:disabled { opacity: .5; cursor: default; }
  svg { width: 22px; height: 22px; fill: currentColor; }
  .switch { position: relative; width: 44px; height: 24px; flex: none; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .switch span { position: absolute; inset: 0; background: var(--switch-unchecked-track-color, #9e9e9e); border-radius: 12px; transition: .2s; }
  .switch span::before { content: ""; position: absolute; width: 18px; height: 18px; left: 3px; top: 3px; background: var(--switch-unchecked-button-color, #fff); border-radius: 50%; transition: .2s; }
  .switch input:checked + span { background: var(--switch-checked-track-color, var(--primary-color)); }
  .switch input:checked + span::before { transform: translateX(20px); background: var(--switch-checked-button-color, #fff); }
  .empty { text-align: center; padding: 32px; color: var(--secondary-text-color); }
  .error { color: var(--error-color, #db4437); margin: 8px 0; }
  dialog { border: none; border-radius: 12px; padding: 0; width: min(520px, calc(100vw - 32px)); background: var(--card-background-color, #fff); color: var(--primary-text-color); box-shadow: 0 8px 32px rgba(0,0,0,.35); }
  dialog::backdrop { background: rgba(0,0,0,.5); }
  form { padding: 20px; display: grid; gap: 14px; }
  form h3 { margin: 0; font-weight: 500; }
  label.field { display: grid; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
  input[type=text], input[type=time], input[type=date], input[type=number], select, textarea { font: inherit; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--divider-color, #ccc); background: var(--primary-background-color, #fafafa); color: var(--primary-text-color); width: 100%; }
  .days { display: flex; gap: 6px; flex-wrap: wrap; }
  .days label { display: inline-flex; align-items: center; gap: 4px; padding: 6px 10px; border-radius: 16px; border: 1px solid var(--divider-color, #ccc); cursor: pointer; font-size: 13px; }
  .days label:has(input:checked) { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  .days input { display: none; }
  .radios { display: flex; gap: 16px; }
  .radios label { display: inline-flex; align-items: center; gap: 6px; }
  .buttons { display: flex; justify-content: flex-end; gap: 8px; }
  .sat { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--divider-color, #eee); }
  .sat:last-child { border-bottom: none; }
  .note { color: var(--secondary-text-color); font-size: 13px; }
  audio { width: 100%; margin-top: 8px; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .graph { display: block; width: 100%; height: auto; touch-action: none; user-select: none; -webkit-user-select: none; }
  .ramp-preview { margin: 8px 0 12px; }
  .ramp-preview .graph { max-width: 380px; }
  .graph .axis { stroke: var(--secondary-text-color); stroke-width: 1; }
  .graph .grid { stroke: var(--divider-color, #ddd); stroke-width: 1; }
  .graph .fill { fill: var(--primary-color); opacity: .12; }
  .graph .curve { fill: none; stroke: var(--primary-color); stroke-width: 3; stroke-linecap: round; }
  .graph .arm { stroke: var(--secondary-text-color); stroke-width: 1.5; stroke-dasharray: 4 3; }
  .graph .handle { fill: var(--card-background-color, #fff); stroke: var(--primary-color); stroke-width: 3; }
  .graph .handle.start { fill: var(--secondary-text-color); stroke: none; }
  .graph .hit { fill: transparent; pointer-events: all; cursor: grab; }
  .graph .hit:active { cursor: grabbing; }
  .graph .hit.start { cursor: ns-resize; }
  .graph.flat .hit, .graph.flat .handle, .graph.flat .arm, .graph.flat .start-label { display: none; }
  .graph text { font-size: 11px; fill: var(--secondary-text-color); }
  .graph .start-label { font-weight: 500; fill: var(--primary-text-color); }
  .graph .playhead { stroke: var(--error-color, #db4437); stroke-width: 2; }
  .presets { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  .presets button { background: transparent; color: var(--primary-color); border: 1px solid var(--primary-color); padding: 5px 10px; border-radius: 16px; font-size: 13px; }
  .presets button.active { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  #ramp { width: min(600px, calc(100vw - 32px)); }
  @media (max-width: 600px) { .time { font-size: 28px; min-width: 80px; } .two { grid-template-columns: 1fr; } }
`;

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const icon = (name) => `<svg viewBox="0 0 24 24"><path d="${ICONS[name]}"/></svg>`;

function formatDays(days) {
  const set = new Set(days);
  if (set.size === 7) return t("every_day");
  if (set.size === 5 && [0, 1, 2, 3, 4].every((d) => set.has(d))) return t("weekdays");
  if (set.size === 2 && set.has(5) && set.has(6)) return t("weekends");
  return days.map((d) => dayShort(d)).join(", ");
}

function formatDate(iso, locale) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(locale, { weekday: "short", day: "numeric", month: "short" });
}

function formatNext(iso, now, locale) {
  if (!iso) return "";
  const target = new Date(iso);
  const diff = (target - now) / 1000;
  let rel;
  if (diff < 60) rel = t("rel_under_minute");
  else if (diff < 3600) rel = t("rel_min", { m: Math.round(diff / 60) });
  else if (diff < 86400) {
    const h = Math.floor(diff / 3600);
    const m = Math.round((diff % 3600) / 60);
    rel = m ? t("rel_h_min", { h, m }) : t("rel_h", { h });
  } else rel = t("rel_d_h", { d: Math.floor(diff / 86400), h: Math.round((diff % 86400) / 3600) });
  const sameDay = target.toDateString() === now.toDateString();
  const tomorrow = new Date(now);
  tomorrow.setDate(now.getDate() + 1);
  let when;
  if (sameDay) when = t("today");
  else if (target.toDateString() === tomorrow.toDateString()) when = t("tomorrow");
  else when = target.toLocaleDateString(locale, { weekday: "short", day: "numeric", month: "short" });
  return `${when} ${target.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })} · ${rel}`;
}

class VoiceAlarmsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._state = null;
    this._error = "";
    this._unsub = null;
    this._editing = null;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><div id="app"></div><dialog id="editor"></dialog><dialog id="ramp"></dialog>`;
    this.shadowRoot.getElementById("app").addEventListener("click", (e) => this._onClick(e));
    this.shadowRoot.getElementById("app").addEventListener("change", (e) => this._onChange(e));
  }

  set hass(hass) {
    const first = !this._hass;
    const dockChanged = !first && hass?.dockedSidebar !== this._hass.dockedSidebar;
    this._hass = hass;
    if (dockChanged) this._render();
    const locale = hass?.locale?.language || hass?.language || navigator.language;
    if (locale !== LOCALE) {
      setLanguage(locale);
      if (!first) this._render();
    }
    if (first) this._subscribe();
  }
  get hass() {
    return this._hass;
  }
  set narrow(v) {
    const changed = !!v !== !!this._narrow;
    this._narrow = v;
    if (changed) this._render();
  }
  set panel(p) {
    this._panel = p;
  }

  connectedCallback() {
    this._render();
    this._timer = setInterval(() => this._render(), 30000);
  }
  disconnectedCallback() {
    clearInterval(this._timer);
    if (this._unsub) {
      this._unsub.then((u) => u()).catch(() => {});
      this._unsub = null;
    }
  }

  _subscribe() {
    this._unsub = this._hass.connection.subscribeMessage(
      (msg) => {
        this._state = msg;
        this._render();
      },
      { type: "voice_alarms/subscribe" }
    );
    this._unsub.catch((err) => {
      this._error = err.message || t("not_loaded");
      this._render();
    });
  }

  get _locale() {
    return LOCALE;
  }

  _target(id) {
    return (this._state?.targets || []).find((t) => t.entity_id === id);
  }

  _render() {
    const app = this.shadowRoot.getElementById("app");
    const st = this._state;
    const now = new Date();
    const parts = [];
    // Like HA's ha-menu-button: custom panels draw their own toolbar, so the
    // sidebar toggle only exists if we render it (narrow layout or sidebar
    // set to "always hidden").
    const narrow = !!this._narrow;
    const menu =
      narrow || this._hass?.dockedSidebar === "always_hidden"
        ? `<button class="menu" data-action="menu" aria-label="${t("menu")}" title="${t("menu")}">${icon("menu")}</button>`
        : "";
    // Narrow layout has no room for two labelled buttons in the toolbar: one
    // floating action button instead, the editor's type select picks reminder.
    const add = narrow
      ? `<button class="fab" data-action="add" data-kind="alarm">${icon("plus")} ${t("add")}</button>`
      : `<button data-action="add" data-kind="alarm">${icon("plus")} ${t("add_alarm")}</button>
      <button data-action="add" data-kind="reminder">${icon("plus")} ${t("add_reminder")}</button>`;
    parts.push(`<div class="toolbar">${menu}${icon("alarm")}<h1>Voice Alarms</h1>${narrow ? "" : add}</div>${narrow ? add : ""}<main class="${narrow ? "narrow" : ""}">`);
    if (this._error) parts.push(`<div class="error">${esc(this._error)}</div>`);
    if (!st) {
      parts.push(`<div class="empty">${t("loading")}</div></main>`);
      app.innerHTML = parts.join("");
      return;
    }
    for (const s of st.ringing) {
      parts.push(`<div class="card ringing"><div class="row">${icon("bell")}
        <div class="grow"><div class="label">${esc(t(s.state === "paused" ? "paused_on" : "ringing_on", { kind: t(s.kind === "reminder" ? "reminder" : "alarm"), target: s.target_name }))}</div>
        <div class="sub">${esc(s.label)}${s.message ? " — " + esc(s.message) : ""}</div></div>
        <div class="actions"><button class="ghost" data-action="snooze" data-target="${esc(s.target)}">${t("snooze5")}</button>
        <button class="danger" data-action="dismiss" data-target="${esc(s.target)}">${icon("stop")} ${t("dismiss")}</button></div></div></div>`);
    }
    const alarms = st.alarms.filter((a) => a.kind !== "reminder");
    const reminders = st.alarms.filter((a) => a.kind === "reminder");
    parts.push(`<h2>${t("alarms")}</h2>`);
    if (!alarms.length) {
      parts.push(`<div class="card empty">${t("no_alarms")}</div>`);
    }
    for (const a of alarms) parts.push(this._renderAlarm(a, now));
    parts.push(`<h2>${t("reminders")}</h2>`);
    if (!reminders.length) {
      parts.push(`<div class="card empty">${t("no_reminders")}</div>`);
    }
    for (const a of reminders) parts.push(this._renderAlarm(a, now));
    parts.push(`<h2>${t("satellites")}</h2><div class="card">`);
    if (!st.targets.length) parts.push(`<div class="note">${t("no_satellites")}</div>`);
    for (const sat of st.targets) {
      const next = st.alarms.filter((a) => a.target === sat.entity_id && a.enabled && a.next).sort((x, y) => x.next.localeCompare(y.next))[0];
      const ringing = st.ringing.find((s) => s.target === sat.entity_id);
      parts.push(`<div class="sat">${icon("speaker")}<div class="grow"><div class="label">${esc(sat.display)}</div>
        <div class="sub">${esc(sat.entity_id)} · ${sat.media_player ? esc(t("volume_via", { player: sat.media_player })) : t("no_media_player")}</div>
        <div class="sub">${next ? esc(t("next", { label: next.label, when: formatNext(next.next, now, this._locale) })) : t("no_upcoming")}</div></div>
        <div class="actions">${ringing ? `<button class="danger" data-action="dismiss" data-target="${esc(sat.entity_id)}">${icon("stop")} ${t("dismiss")}</button>` : `<button class="ghost" data-action="test" data-target="${esc(sat.entity_id)}">${icon("play")} ${t("test")}</button>`}</div></div>`);
    }
    const ramp = rampFromConfig(st.config);
    const admin = !!this._hass?.user?.is_admin;
    parts.push(`</div><h2>${t("settings")}</h2><div class="card">
      <div class="row"><div class="grow"><div class="label">${t("volume_ramp")}</div><div class="sub">${esc(rampSummary(ramp))}</div></div>
        ${admin ? `<div class="actions"><button class="ghost" data-action="ramp">${icon("edit")} ${t("edit_ramp")}</button></div>` : ""}</div>
      <div class="ramp-preview">${rampSvg(ramp, false)}</div>
      <div class="note">
      ${t("ring_duration", { seconds: st.config.default_duration })} ·
      ${st.config.alarm_volume != null ? t("satellite_volume", { percent: Math.round(st.config.alarm_volume * 100) }) : t("satellite_volume_unchanged")} ·
      ${t("sound", { sound: st.config.default_sound ? esc(st.config.default_sound) : t("built_in") })}${st.config.default_sound && !st.config.ffmpeg ? t("ffmpeg_missing") : ""}.
      ${t("change_hint")}</div>
      <div class="note" style="margin-top:8px">${t("preview_label")}</div>
      <audio controls preload="none" src="/api/voice_alarms/sound/default.wav"></audio></div></main>`);
    app.innerHTML = parts.join("");
  }

  _renderAlarm(a, now) {
    const target = this._target(a.target);
    const reminder = a.kind === "reminder";
    const badges = [];
    if (!a.enabled) badges.push(`<span class="badge">${t("disabled")}</span>`);
    if (a.next_skipped) badges.push(`<span class="badge warn">${t("next_skipped")}</span>`);
    if (a.enabled && !a.next) badges.push(`<span class="badge err">${t("in_past")}</span>`);
    if (!target) badges.push(`<span class="badge err">${t("unknown_satellite")}</span>`);
    const schedule = a.is_recurring ? formatDays(a.weekdays) : a.date ? formatDate(a.date, this._locale) : t("once");
    const message = a.message && a.message !== a.label ? `<div class="message">“${esc(a.message)}”</div>` : "";
    return `<div class="card ${reminder ? "reminder" : ""} ${a.enabled ? "" : "disabled"}"><div class="row">
      <div class="time">${esc(a.time)}</div>
      <div class="grow"><div class="label">${esc(a.label)}</div>${message}
        <div class="sub">${esc(schedule)} · ${esc(target ? target.display : a.target)}</div>
        <div class="sub">${a.enabled ? esc(formatNext(a.next, now, this._locale)) : ""}</div>
        <div class="badges">${badges.join("")}</div></div>
      <div class="actions">
        <label class="switch" title="${t("enabled")}"><input type="checkbox" data-action="toggle" data-id="${esc(a.id)}" ${a.enabled ? "checked" : ""}><span></span></label>
        ${a.is_recurring ? `<button class="icon" title="${t(a.next_skipped ? "reinstate_next" : "skip_next")}" data-action="${a.next_skipped ? "unskip" : "skip"}" data-id="${esc(a.id)}">${icon(a.next_skipped ? "undo" : "skip")}</button>` : ""}
        <button class="icon" title="${t("edit")}" data-action="edit" data-id="${esc(a.id)}">${icon("edit")}</button>
        <button class="icon" title="${t("delete")}" data-action="delete" data-id="${esc(a.id)}">${icon("del")}</button>
      </div></div></div>`;
  }

  async _call(service, data, returnResponse = false) {
    this._error = "";
    try {
      return await this._hass.callService("voice_alarms", service, data, undefined, true, returnResponse);
    } catch (err) {
      this._error = err?.message || String(err);
      this._render();
      throw err;
    }
  }

  async _onClick(e) {
    const el = e.target.closest("[data-action]");
    if (!el || el.tagName === "INPUT") return;
    const { action, id, target, kind } = el.dataset;
    const alarm = id && this._state.alarms.find((a) => a.id === id);
    switch (action) {
      case "menu":
        // Handled by home-assistant-main; bubbles + composed so it leaves the shadow root.
        this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
        break;
      case "add":
        this._openEditor(null, kind || "alarm");
        break;
      case "edit":
        this._openEditor(alarm);
        break;
      case "delete":
        if (confirm(t("confirm_delete", { label: alarm.label }))) await this._call("delete_alarm", { alarm_id: id }).catch(() => {});
        break;
      case "skip":
        await this._call("skip_next", { alarm_id: id }).catch(() => {});
        break;
      case "unskip":
        await this._call("skip_next", { alarm_id: id, undo: true }).catch(() => {});
        break;
      case "dismiss":
        await this._call("dismiss", { target }).catch(() => {});
        break;
      case "snooze":
        await this._call("snooze", { target, minutes: 5 }).catch(() => {});
        break;
      case "test":
        await this._call("test_alarm", { target, duration: 20 }).catch(() => {});
        break;
      case "ramp":
        this._openRampEditor();
        break;
      default:
        break;
    }
  }

  async _onChange(e) {
    const el = e.target;
    if (el.dataset.action !== "toggle") return;
    await this._call("update_alarm", { alarm_id: el.dataset.id, enabled: el.checked }).catch(() => {});
  }

  _openRampEditor() {
    const dialog = this.shadowRoot.getElementById("ramp");
    const ramp = rampFromConfig(this._state.config);
    dialog.innerHTML = `<form method="dialog">
      <h3>${t("volume_ramp")}</h3>
      <div class="note">${t("ramp_help")}</div>
      ${rampSvg(ramp, true)}
      <div class="presets">${RAMP_PRESETS.map(([name]) => `<button type="button" data-preset="${esc(name)}">${esc(t(`preset_${name}`))}</button>`).join("")}<span class="note" id="ramp-curve"></span></div>
      <div class="two">
        <label class="field">${t("ramp_seconds")}<input type="number" name="seconds" min="0" max="300" step="1" value="${ramp.seconds}"></label>
        <label class="field">${t("ramp_start")}<input type="number" name="start" min="0" max="100" step="1" value="${Math.round(ramp.start * 100)}"></label>
      </div>
      <div class="row"><button type="button" class="ghost" id="ramp-play">${icon("play")} ${t("preview_play")}</button><span class="note" id="ramp-time"></span></div>
      <div class="error" id="ramp-error"></div>
      <div class="buttons"><button type="button" class="ghost" data-close>${t("cancel")}</button><button type="submit">${t("save")}</button></div>
    </form>`;
    const form = dialog.querySelector("form");
    const svg = dialog.querySelector("svg");
    const curveInfo = dialog.querySelector("#ramp-curve");
    const timeInfo = dialog.querySelector("#ramp-time");
    const errorEl = dialog.querySelector("#ramp-error");
    const playButton = dialog.querySelector("#ramp-play");
    const playhead = svg.querySelector(".playhead");
    const startLabel = svg.querySelector("[data-start-label]");

    const place = (el, [x, y]) => {
      if (el.tagName === "rect") {
        el.setAttribute("x", x + Number(el.dataset.ox));
        el.setAttribute("y", y + Number(el.dataset.oy));
      } else {
        el.setAttribute("cx", x);
        el.setAttribute("cy", y);
      }
    };
    const update = () => {
      const path = curvePath(ramp);
      const pts = rampPoints(ramp);
      svg.querySelector(".curve").setAttribute("d", path);
      svg.querySelector(".fill").setAttribute("d", `${path} L${graphX(1)},${graphY(0)} L${graphX(0)},${graphY(0)} Z`);
      for (const el of svg.querySelectorAll("[data-handle]")) place(el, pts[el.dataset.handle]);
      for (const el of svg.querySelectorAll("[data-arm]")) {
        const [from, to] = el.dataset.arm === "p1" ? [pts.p0, pts.p1] : [pts.p3, pts.p2];
        el.setAttribute("x1", from[0]);
        el.setAttribute("y1", from[1]);
        el.setAttribute("x2", to[0]);
        el.setAttribute("y2", to[1]);
      }
      for (const el of svg.querySelectorAll("[data-tick]")) el.textContent = formatSeconds(Number(el.dataset.tick) * ramp.seconds);
      startLabel.setAttribute("y", pts.p0[1] - 8);
      startLabel.textContent = `${Math.round(ramp.start * 100)}%`;
      startLabel.style.display = ramp.start > 0.9 ? "none" : "";
      svg.classList.toggle("flat", ramp.seconds <= 0);
      const name = presetName(ramp.curve);
      for (const b of dialog.querySelectorAll("[data-preset]")) b.classList.toggle("active", b.dataset.preset === name);
      curveInfo.textContent =
        ramp.seconds <= 0
          ? t("no_ramp")
          : `cubic-bezier(${ramp.curve.map((v) => Math.round(v * 100) / 100).join(", ")})${name ? "" : ` · ${t("custom")}`}`;
    };
    update();

    // Dragging: pointer position in SVG units, mapped to time fraction (x) and gain (y).
    let dragging = null;
    svg.addEventListener("pointerdown", (e) => {
      const el = e.target.closest("[data-handle]");
      if (!el || ramp.seconds <= 0) return;
      dragging = el.dataset.handle;
      svg.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    svg.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM().inverse());
      const x = clamp((pt.x - G.left) / (G.w - G.left - G.right), 0, 1);
      const gain = clamp(1 - (pt.y - G.top) / (G.h - G.top - G.bottom), 0, 1);
      if (dragging === "p0") {
        ramp.start = Math.round(gain * 100) / 100;
        form.start.value = Math.round(ramp.start * 100);
      } else {
        const y = ramp.start >= 1 ? 1 : clamp((gain - ramp.start) / (1 - ramp.start), 0, 1);
        const i = dragging === "p1" ? 0 : 2;
        ramp.curve[i] = Math.round(x * 100) / 100;
        ramp.curve[i + 1] = Math.round(y * 100) / 100;
      }
      update();
    });
    const endDrag = () => {
      dragging = null;
    };
    svg.addEventListener("pointerup", endDrag);
    svg.addEventListener("pointercancel", endDrag);

    dialog.querySelector(".presets").addEventListener("click", (e) => {
      const button = e.target.closest("[data-preset]");
      if (!button) return;
      ramp.curve = [...RAMP_PRESETS.find(([name]) => name === button.dataset.preset)[1]];
      update();
    });
    form.addEventListener("input", (e) => {
      if (e.target.name === "seconds") ramp.seconds = clamp(Number(e.target.value) || 0, 0, 300);
      else if (e.target.name === "start") ramp.start = clamp((Number(e.target.value) || 0) / 100, 0, 1);
      else return;
      update();
    });

    // Preview: the built-in loop through a Web Audio gain node that follows the ramp.
    let preview = null;
    const stopPreview = () => {
      if (!preview) return;
      cancelAnimationFrame(preview.frame);
      try {
        preview.source.stop();
      } catch (err) {
        // already stopped
      }
      preview.context.close();
      preview = null;
      playhead.style.display = "none";
      timeInfo.textContent = "";
      playButton.innerHTML = `${icon("play")} ${t("preview_play")}`;
    };
    const startPreview = async () => {
      const Context = window.AudioContext || window.webkitAudioContext;
      if (!Context) {
        errorEl.textContent = t("no_web_audio");
        return;
      }
      errorEl.textContent = "";
      playButton.disabled = true;
      const context = new Context();
      try {
        const resp = await fetch("/api/voice_alarms/sound/default.wav");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const buffer = await context.decodeAudioData(await resp.arrayBuffer());
        const snapshot = { seconds: ramp.seconds, start: ramp.start, curve: [...ramp.curve] };
        const source = context.createBufferSource();
        source.buffer = buffer;
        source.loop = true;
        const gain = context.createGain();
        const t0 = context.currentTime + 0.1;
        if (snapshot.seconds > 0) {
          const steps = 512;
          const values = new Float32Array(steps);
          for (let i = 0; i < steps; i++) values[i] = rampGain(snapshot, (i / (steps - 1)) * snapshot.seconds);
          gain.gain.value = snapshot.start;
          gain.gain.setValueCurveAtTime(values, t0, snapshot.seconds);
        } else {
          gain.gain.value = 1;
        }
        source.connect(gain);
        gain.connect(context.destination);
        source.start(t0);
        preview = { context, source, frame: 0 };
        const total = snapshot.seconds + 3;
        const tick = () => {
          if (!preview) return;
          const elapsed = context.currentTime - t0;
          if (elapsed >= total) {
            stopPreview();
            return;
          }
          const x = graphX(snapshot.seconds > 0 ? clamp(elapsed / snapshot.seconds, 0, 1) : 1);
          playhead.setAttribute("x1", x);
          playhead.setAttribute("x2", x);
          playhead.style.display = "";
          timeInfo.textContent = `${Math.max(0, elapsed).toFixed(1)} s · ${Math.round(rampGain(snapshot, elapsed) * 100)}%`;
          preview.frame = requestAnimationFrame(tick);
        };
        tick();
        playButton.innerHTML = `${icon("stop")} ${t("stop")}`;
      } catch (err) {
        errorEl.textContent = t("preview_failed", { error: err?.message || err });
        context.close();
      }
      playButton.disabled = false;
    };
    playButton.addEventListener("click", () => (preview ? stopPreview() : startPreview()));

    dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", stopPreview, { once: true });
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      try {
        await this._hass.callWS({ type: "voice_alarms/set_ramp", seconds: ramp.seconds, start: ramp.start, curve: ramp.curve });
        dialog.close();
      } catch (err) {
        errorEl.textContent = err?.message || String(err);
      }
    });
    dialog.showModal();
  }

  _openEditor(alarm, newKind = "alarm") {
    if (!this._state) return;
    const dialog = this.shadowRoot.getElementById("editor");
    const targets = this._state.targets;
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(today.getDate() + 1);
    const toIso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const a = alarm || {
      kind: newKind,
      name: "",
      message: "",
      time: "07:00",
      weekdays: [],
      date: toIso(tomorrow),
      target: targets.length === 1 ? targets[0].entity_id : "",
      duration: null,
      sound: "",
      enabled: true,
      is_recurring: false,
    };
    dialog.innerHTML = `<form method="dialog">
      <h3 id="form-title"></h3>
      <div class="two">
        <label class="field">${t("type")}<select name="kind"><option value="alarm" ${a.kind === "alarm" ? "selected" : ""}>${t("alarm_rings")}</option><option value="reminder" ${a.kind === "reminder" ? "selected" : ""}>${t("reminder_spoken")}</option></select></label>
        <label class="field">${t("time")}<input type="time" name="time" required value="${esc(a.time)}"></label>
      </div>
      <label class="field">${t("name")}<input type="text" name="name" placeholder="${esc(t("name_placeholder"))}" value="${esc(a.name || "")}"></label>
      <label class="field" data-only="reminder">${t("message")}<input type="text" name="message" placeholder="${esc(t("message_placeholder"))}" value="${esc(a.message || "")}"></label>
      <label class="field">${t("satellite_required")}<select name="target" required><option value="">${t("choose")}</option>${targets
        .map((t) => `<option value="${esc(t.entity_id)}" ${t.entity_id === a.target ? "selected" : ""}>${esc(t.display)}</option>`)
        .join("")}</select></label>
      <div class="radios"><label><input type="radio" name="repeat" value="once" ${!a.is_recurring ? "checked" : ""}> ${t("one_time")}</label>
        <label><input type="radio" name="repeat" value="weekly" ${a.is_recurring ? "checked" : ""}> ${t("repeat_weekly")}</label></div>
      <label class="field" data-only="once">${t("date")}<input type="date" name="date" value="${esc(a.date || toIso(tomorrow))}"></label>
      <div class="field" data-only="weekly"><span>${t("days")}</span><div class="days">${DAY_CODES.map(
        (c, i) => `<label><input type="checkbox" name="wd" value="${c}" ${a.weekdays.includes(i) ? "checked" : ""}>${esc(dayShort(i))}</label>`
      ).join("")}</div></div>
      <div class="two" data-only="alarm">
        <label class="field">${t("duration_minutes")}<input type="number" name="duration" min="1" max="1440" value="${a.duration ? Math.round(a.duration / 60) : ""}"></label>
        <label class="field">${t("custom_sound")}<input type="text" name="sound" value="${esc(a.sound || "")}"></label>
      </div>
      <label class="radios"><input type="checkbox" name="enabled" ${a.enabled ? "checked" : ""}> ${t("enabled")}</label>
      <div class="error" id="form-error"></div>
      <div class="buttons"><button type="button" class="ghost" data-close>${t("cancel")}</button><button type="submit">${t(alarm ? "save" : "create")}</button></div>
    </form>`;
    const form = dialog.querySelector("form");
    const sync = () => {
      const kind = form.kind.value;
      const repeat = form.repeat.value;
      form.querySelector("#form-title").textContent = t(`${alarm ? "edit" : "new"}_${kind}`);
      for (const el of form.querySelectorAll("[data-only]")) {
        const only = el.dataset.only;
        el.style.display = only === kind || only === repeat ? "" : "none";
      }
    };
    form.addEventListener("change", sync);
    sync();
    dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const weekdays = [...form.querySelectorAll("input[name=wd]:checked")].map((i) => i.value);
      const repeat = form.repeat.value;
      const data = {
        target: form.target.value,
        time: form.time.value,
        name: form.name.value.trim(),
        message: form.kind.value === "reminder" ? form.message.value.trim() : "",
        kind: form.kind.value,
        enabled: form.enabled.checked,
        sound: form.sound.value.trim(),
        weekdays: repeat === "weekly" ? weekdays : [],
      };
      if (repeat === "once") data.date = form.date.value;
      if (form.duration.value) data.duration = Number(form.duration.value) * 60;
      const errorEl = form.querySelector("#form-error");
      if (!data.target) {
        errorEl.textContent = t("choose_satellite");
        return;
      }
      if (repeat === "weekly" && !weekdays.length) {
        errorEl.textContent = t("pick_weekday");
        return;
      }
      if (data.kind === "reminder" && !data.message) {
        errorEl.textContent = t("reminder_needs_message");
        return;
      }
      try {
        if (alarm) await this._hass.callService("voice_alarms", "update_alarm", { alarm_id: alarm.id, ...data });
        else await this._hass.callService("voice_alarms", "add_alarm", data);
        dialog.close();
      } catch (err) {
        errorEl.textContent = err?.message || String(err);
      }
    });
    dialog.showModal();
  }
}

customElements.define("voice-alarms-panel", VoiceAlarmsPanel);
