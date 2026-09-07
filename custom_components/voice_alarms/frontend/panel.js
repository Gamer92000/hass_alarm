/* Voice Alarms panel: a dependency-free web component served by the
 * voice_alarms integration and registered as a custom sidebar panel. */

const ICONS = {
  alarm:
    "M12,20A7,7 0 0,1 5,13A7,7 0 0,1 12,6A7,7 0 0,1 19,13A7,7 0 0,1 12,20M12,4A9,9 0 0,0 3,13A9,9 0 0,0 12,22A9,9 0 0,0 21,13A9,9 0 0,0 12,4M12.5,8H11V14L15.75,16.85L16.5,15.62L12.5,13.25V8M7.88,3.39L6.6,1.86L2,5.71L3.29,7.24L7.88,3.39M22,5.72L17.4,1.86L16.11,3.39L20.71,7.25L22,5.72Z",
  bell:
    "M21,19V20H3V19L5,17V11C5,7.9 7.03,5.17 10,4.29C10,4.19 10,4.1 10,4A2,2 0 0,1 12,2A2,2 0 0,1 14,4C14,4.1 14,4.19 14,4.29C16.97,5.17 19,7.9 19,11V17L21,19M14,21A2,2 0 0,1 12,23A2,2 0 0,1 10,21M19.75,3.19L18.33,4.61C20.04,6.3 21,8.6 21,11H23C23,8.07 21.84,5.25 19.75,3.19M1,11H3C3,8.6 3.96,6.3 5.67,4.61L4.25,3.19C2.16,5.25 1,8.07 1,11Z",
  plus: "M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z",
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
const DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const STYLE = `
  :host { display: block; height: 100%; overflow: auto; color: var(--primary-text-color); background: var(--primary-background-color); }
  * { box-sizing: border-box; }
  .toolbar { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 12px; height: var(--header-height, 56px); padding: 0 16px; background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); }
  .toolbar h1 { font-size: 20px; font-weight: 400; margin: 0; flex: 1; }
  .toolbar svg { fill: currentColor; }
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
  @media (max-width: 600px) { .time { font-size: 28px; min-width: 80px; } .two { grid-template-columns: 1fr; } }
`;

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const icon = (name) => `<svg viewBox="0 0 24 24"><path d="${ICONS[name]}"/></svg>`;

function formatDays(days) {
  const set = new Set(days);
  if (set.size === 7) return "Every day";
  if (set.size === 5 && [0, 1, 2, 3, 4].every((d) => set.has(d))) return "Weekdays";
  if (set.size === 2 && set.has(5) && set.has(6)) return "Weekends";
  return days.map((d) => DAY_SHORT[d]).join(", ");
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
  if (diff < 60) rel = "in less than a minute";
  else if (diff < 3600) rel = `in ${Math.round(diff / 60)} min`;
  else if (diff < 86400) {
    const h = Math.floor(diff / 3600);
    const m = Math.round((diff % 3600) / 60);
    rel = `in ${h} h${m ? ` ${m} min` : ""}`;
  } else rel = `in ${Math.floor(diff / 86400)} d ${Math.round((diff % 86400) / 3600)} h`;
  const sameDay = target.toDateString() === now.toDateString();
  const tomorrow = new Date(now);
  tomorrow.setDate(now.getDate() + 1);
  let when;
  if (sameDay) when = "today";
  else if (target.toDateString() === tomorrow.toDateString()) when = "tomorrow";
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
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><div id="app"></div><dialog id="editor"></dialog>`;
    this.shadowRoot.getElementById("app").addEventListener("click", (e) => this._onClick(e));
    this.shadowRoot.getElementById("app").addEventListener("change", (e) => this._onChange(e));
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._subscribe();
  }
  get hass() {
    return this._hass;
  }
  set narrow(v) {
    this._narrow = v;
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
      this._error = err.message || "Voice Alarms is not loaded";
      this._render();
    });
  }

  get _locale() {
    return this._hass?.locale?.language || navigator.language;
  }

  _target(id) {
    return (this._state?.targets || []).find((t) => t.entity_id === id);
  }

  _render() {
    const app = this.shadowRoot.getElementById("app");
    const st = this._state;
    const now = new Date();
    const parts = [];
    parts.push(`<div class="toolbar">${icon("alarm")}<h1>Voice Alarms</h1>
      <button data-action="add" data-kind="alarm">${icon("plus")} Add alarm</button>
      <button data-action="add" data-kind="reminder">${icon("plus")} Add reminder</button></div><main>`);
    if (this._error) parts.push(`<div class="error">${esc(this._error)}</div>`);
    if (!st) {
      parts.push(`<div class="empty">Loading…</div></main>`);
      app.innerHTML = parts.join("");
      return;
    }
    for (const s of st.ringing) {
      parts.push(`<div class="card ringing"><div class="row">${icon("bell")}
        <div class="grow"><div class="label">${esc(s.kind === "reminder" ? "Reminder" : "Alarm")} ${s.state === "paused" ? "paused" : "ringing"} on ${esc(s.target_name)}</div>
        <div class="sub">${esc(s.label)}${s.message ? " — " + esc(s.message) : ""}</div></div>
        <div class="actions"><button class="ghost" data-action="snooze" data-target="${esc(s.target)}">Snooze 5 min</button>
        <button class="danger" data-action="dismiss" data-target="${esc(s.target)}">${icon("stop")} Dismiss</button></div></div></div>`);
    }
    const alarms = st.alarms.filter((a) => a.kind !== "reminder");
    const reminders = st.alarms.filter((a) => a.kind === "reminder");
    parts.push(`<h2>Alarms</h2>`);
    if (!alarms.length) {
      parts.push(`<div class="card empty">No alarms yet. Add one here or say “set an alarm for 7” to a satellite.</div>`);
    }
    for (const a of alarms) parts.push(this._renderAlarm(a, now));
    parts.push(`<h2>Reminders</h2>`);
    if (!reminders.length) {
      parts.push(`<div class="card empty">No reminders yet. Add one here or say “remind me at 6 to take out the trash” to a satellite.</div>`);
    }
    for (const a of reminders) parts.push(this._renderAlarm(a, now));
    parts.push(`<h2>Satellites</h2><div class="card">`);
    if (!st.targets.length) parts.push(`<div class="note">No assist satellites found. Add a Voice PE / Wyoming satellite first.</div>`);
    for (const t of st.targets) {
      const next = st.alarms.filter((a) => a.target === t.entity_id && a.enabled && a.next).sort((x, y) => x.next.localeCompare(y.next))[0];
      const ringing = st.ringing.find((s) => s.target === t.entity_id);
      parts.push(`<div class="sat">${icon("speaker")}<div class="grow"><div class="label">${esc(t.display)}</div>
        <div class="sub">${esc(t.entity_id)}${t.media_player ? " · volume via " + esc(t.media_player) : " · no media player (volume not controlled)"}</div>
        <div class="sub">${next ? "Next: " + esc(next.label) + " " + esc(formatNext(next.next, now, this._locale)) : "No upcoming alarm"}</div></div>
        <div class="actions">${ringing ? `<button class="danger" data-action="dismiss" data-target="${esc(t.entity_id)}">${icon("stop")} Dismiss</button>` : `<button class="ghost" data-action="test" data-target="${esc(t.entity_id)}">${icon("play")} Test</button>`}</div></div>`);
    }
    parts.push(`</div><h2>Settings</h2><div class="card"><div class="note">
      Ring duration ${st.config.default_duration}s · volume ramps from ${Math.round(st.config.ramp_start * 100)}% over ${st.config.ramp_seconds}s ·
      ${st.config.alarm_volume != null ? "satellite volume " + Math.round(st.config.alarm_volume * 100) + "%" : "satellite volume unchanged"} ·
      sound: ${st.config.default_sound ? esc(st.config.default_sound) : "built-in"}${st.config.default_sound && !st.config.ffmpeg ? " (ffmpeg missing: no ramp)" : ""}.
      Change these under Settings → Devices &amp; services → Voice Alarms → Configure.</div>
      <div class="note" style="margin-top:8px">Built-in sound preview:</div>
      <audio controls preload="none" src="/api/voice_alarms/sound/default.wav"></audio></div></main>`);
    app.innerHTML = parts.join("");
  }

  _renderAlarm(a, now) {
    const target = this._target(a.target);
    const reminder = a.kind === "reminder";
    const badges = [];
    if (!a.enabled) badges.push(`<span class="badge">Disabled</span>`);
    if (a.next_skipped) badges.push(`<span class="badge warn">Next occurrence skipped</span>`);
    if (a.enabled && !a.next) badges.push(`<span class="badge err">In the past</span>`);
    if (!target) badges.push(`<span class="badge err">Unknown satellite</span>`);
    const schedule = a.is_recurring ? formatDays(a.weekdays) : a.date ? formatDate(a.date, this._locale) : "once";
    const message = a.message && a.message !== a.label ? `<div class="message">“${esc(a.message)}”</div>` : "";
    return `<div class="card ${reminder ? "reminder" : ""} ${a.enabled ? "" : "disabled"}"><div class="row">
      <div class="time">${esc(a.time)}</div>
      <div class="grow"><div class="label">${esc(a.label)}</div>${message}
        <div class="sub">${esc(schedule)} · ${esc(target ? target.display : a.target)}</div>
        <div class="sub">${a.enabled ? esc(formatNext(a.next, now, this._locale)) : ""}</div>
        <div class="badges">${badges.join("")}</div></div>
      <div class="actions">
        <label class="switch" title="Enabled"><input type="checkbox" data-action="toggle" data-id="${esc(a.id)}" ${a.enabled ? "checked" : ""}><span></span></label>
        ${a.is_recurring ? `<button class="icon" title="${a.next_skipped ? "Reinstate next occurrence" : "Skip next occurrence"}" data-action="${a.next_skipped ? "unskip" : "skip"}" data-id="${esc(a.id)}">${icon(a.next_skipped ? "undo" : "skip")}</button>` : ""}
        <button class="icon" title="Edit" data-action="edit" data-id="${esc(a.id)}">${icon("edit")}</button>
        <button class="icon" title="Delete" data-action="delete" data-id="${esc(a.id)}">${icon("del")}</button>
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
      case "add":
        this._openEditor(null, kind || "alarm");
        break;
      case "edit":
        this._openEditor(alarm);
        break;
      case "delete":
        if (confirm(`Delete “${alarm.label}”?`)) await this._call("delete_alarm", { alarm_id: id }).catch(() => {});
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
      default:
        break;
    }
  }

  async _onChange(e) {
    const el = e.target;
    if (el.dataset.action !== "toggle") return;
    await this._call("update_alarm", { alarm_id: el.dataset.id, enabled: el.checked }).catch(() => {});
  }

  _openEditor(alarm, newKind = "alarm") {
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
        <label class="field">Type<select name="kind"><option value="alarm" ${a.kind === "alarm" ? "selected" : ""}>Alarm (rings)</option><option value="reminder" ${a.kind === "reminder" ? "selected" : ""}>Reminder (spoken)</option></select></label>
        <label class="field">Time<input type="time" name="time" required value="${esc(a.time)}"></label>
      </div>
      <label class="field">Name<input type="text" name="name" placeholder="e.g. Work" value="${esc(a.name || "")}"></label>
      <label class="field" data-only="reminder">Message to speak<input type="text" name="message" placeholder="Take out the trash" value="${esc(a.message || "")}"></label>
      <label class="field">Satellite (required)<select name="target" required><option value="">— choose —</option>${targets
        .map((t) => `<option value="${esc(t.entity_id)}" ${t.entity_id === a.target ? "selected" : ""}>${esc(t.display)}</option>`)
        .join("")}</select></label>
      <div class="radios"><label><input type="radio" name="repeat" value="once" ${!a.is_recurring ? "checked" : ""}> One time</label>
        <label><input type="radio" name="repeat" value="weekly" ${a.is_recurring ? "checked" : ""}> Repeat weekly</label></div>
      <label class="field" data-only="once">Date<input type="date" name="date" value="${esc(a.date || toIso(tomorrow))}"></label>
      <div class="field" data-only="weekly"><span>Days</span><div class="days">${DAY_CODES.map(
        (c, i) => `<label><input type="checkbox" name="wd" value="${c}" ${a.weekdays.includes(i) ? "checked" : ""}>${DAY_SHORT[i]}</label>`
      ).join("")}</div></div>
      <div class="two" data-only="alarm">
        <label class="field">Ring duration (minutes, empty = default)<input type="number" name="duration" min="1" max="1440" value="${a.duration ? Math.round(a.duration / 60) : ""}"></label>
        <label class="field">Custom sound (URL / media-source id)<input type="text" name="sound" value="${esc(a.sound || "")}"></label>
      </div>
      <label class="radios"><input type="checkbox" name="enabled" ${a.enabled ? "checked" : ""}> Enabled</label>
      <div class="error" id="form-error"></div>
      <div class="buttons"><button type="button" class="ghost" data-close>Cancel</button><button type="submit">${alarm ? "Save" : "Create"}</button></div>
    </form>`;
    const form = dialog.querySelector("form");
    const sync = () => {
      const kind = form.kind.value;
      const repeat = form.repeat.value;
      form.querySelector("#form-title").textContent = `${alarm ? "Edit" : "New"} ${kind}`;
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
        errorEl.textContent = "Choose a satellite.";
        return;
      }
      if (repeat === "weekly" && !weekdays.length) {
        errorEl.textContent = "Pick at least one weekday.";
        return;
      }
      if (data.kind === "reminder" && !data.message) {
        errorEl.textContent = "A reminder needs a message.";
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
