"""Languages for spoken responses, labels and user facing errors.

Everything the integration says or shows outside Home Assistant's own translation
system (``translations/*.json``) comes from the tables below. Intent responses use
the language of the conversation (``intent.language``); the default label of an
alarm, the spoken "Reminder:" prefix and service errors use the instance language
(``hass.config.language``), which ``set_default_language`` records at setup.
"""

from __future__ import annotations

from typing import Any, Final

DEFAULT_LANGUAGE: Final = "en"

WEEKDAYS: Final[dict[str, list[str]]] = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
}

MONTHS: Final[dict[str, list[str]]] = {
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
    "de": [
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ],
}

# Every key exists in English; other languages fall back to it per key.
STRINGS: Final[dict[str, dict[str, str]]] = {
    "en": {
        # -- building blocks (speech.py)
        "and": " and ",
        "days_every_day": "every day",
        "days_weekdays": "weekdays",
        "days_weekends": "weekends",
        "days_every": "every {days}",
        "rel_past": "in the past",
        "rel_under_minute": "in less than a minute",
        "rel_in": "in {a}",
        "rel_in_two": "in {a} and {b}",
        "unit_day": "{n} day",
        "unit_days": "{n} days",
        "unit_hour": "{n} hour",
        "unit_hours": "{n} hours",
        "unit_minute": "{n} minute",
        "unit_minutes": "{n} minutes",
        "unit_seconds": "{n} seconds",
        "long_day": "{weekday} {day} {month}",
        "long_day_year": "{weekday} {day} {month} {year}",
        "day_today": "today",
        "day_tomorrow": "tomorrow ({day})",
        "day_on": "on {day}",
        "when_at": "{day} at {time}",
        "schedule_recurring": "{time} {days}",
        "schedule_date": "{time} on {day}",
        "kind_alarm": "alarm",
        "kind_reminder": "reminder",
        "kind_alarm_repeating": "repeating alarm",
        "kind_alarm_once": "one-time alarm",
        "kind_reminder_repeating": "repeating reminder",
        "kind_reminder_once": "one-time reminder",
        "the_alarm": "the alarm",
        "the_reminder": "the reminder",
        "The_alarm": "The alarm",
        "The_reminder": "The reminder",
        "label_alarm": "Alarm",
        "label_reminder": "Reminder",
        "spoken_reminder": "Reminder: {text}",
        "snoozed_name": "{label} (snoozed)",
        "alarm_desc": "{kind} '{label}' at {schedule}",
        "alarm_desc_saying": " saying '{message}'",
        "alarm_desc_on": " on {where}",
        "alarm_desc_disabled": " (disabled)",
        "alarm_desc_skipping": ", skipping {when}",
        "alarm_desc_next": ", next {when} ({relative})",
        "alarm_desc_past": " (already in the past)",
        "brief_reminder": "a reminder '{label}' at {time}",
        "brief_skipped": "skipped",
        "paused": " (paused)",
        "session": "{kind} '{label}' on {target}{state}",
        # -- intents
        "none_configured": "none configured",
        "id_suffix": " [id {alarm_id}]",
        "err_unknown_satellite": (
            "I don't know a voice satellite called '{query}'. Available satellites: {names}."
        ),
        "err_ambiguous_satellite": "'{query}' matches several satellites: {names}. Which one?",
        "err_no_current_satellite": (
            "I can't tell which voice satellite you are using, please name the target "
            "satellite. Available satellites: {names}."
        ),
        "err_no_alarm_id": "There is no alarm with id {alarm_id}.",
        "err_none_configured": "There are no alarms or reminders configured.",
        "err_no_match": "No alarm matches. Configured: {all}.",
        "err_which_one": "{count} alarms match, which one should I {verb}? {all}.",
        "verb_delete": "delete",
        "verb_skip": "skip",
        "verb_reinstate": "reinstate",
        "verb_change": "change",
        "err_invalid_input": "Invalid input: {error}",
        "err_date_and_weekdays": (
            "An alarm either repeats on weekdays or rings once on a date, not both. Drop "
            "the date; a repeating alarm starts with its next occurrence."
        ),
        "created": "Created {alarm}.",
        "repeats_once": "once",
        "scope_on": " on {names}",
        "list_none": "There are no alarms or reminders configured{scope}.",
        "list_have": "You have {count} {noun}{scope}: {listing}.",
        "noun_alarm": "alarm",
        "noun_alarms": "alarms",
        "list_ringing": "Currently ringing: {list}.",
        "day_none": "There are no alarms or reminders {when}{scope}.",
        "day_next": " The next one is the {alarm}.",
        "day_have": "{when} you have {count} {noun}{scope}: {segments}.",
        "segment_on": "{items} on {target}",
        "err_delete_none": "There are no alarms to delete.",
        "err_delete_which": (
            "There are {count} alarms, which one should I delete? {all}. Say all=true to "
            "delete all of them."
        ),
        "deleted": "Deleted {list}.",
        "rings_next": "'{label}' rings next {when}",
        "err_skip_only_next": "I can only skip the very next ring: {later}.",
        "err_no_skipped": "The alarm '{label}' on {where} has no skipped occurrence.",
        "reinstated": "Reinstated the alarm '{label}' on {where}{when}",
        "rings_next_clause": "; it rings next {when} ({relative})",
        "err_already_skipped": "The alarm '{label}' on {where} {when} is already skipped{next}.",
        "skipping": "Skipping the alarm '{label}' on {where}{when}",
        "rings_next_sentence": ". It rings next {when} ({relative})",
        "err_none_skipped": "None of the matching alarms has a skipped occurrence.",
        "skip_segment": "{items} on {where} {day}",
        "skip_many": "Skipping {count} alarms: {segments}.",
        "reinstate_many": "Reinstated {count} alarms: {segments}.",
        "next_ring": " The next ring is {when} ({relative}).",
        "err_update_none": "There are no alarms to change.",
        "change_time": "time to {time}",
        "change_once": "repeat to one-time",
        "change_repeat": "repeat to {days}",
        "change_date": "date to {date}",
        "change_name": "name to '{name}'",
        "change_message": "message to '{message}'",
        "change_target": "satellite to {target}",
        "change_enabled": "enabled it",
        "change_disabled": "disabled it",
        "change_duration": "ring duration to {minutes} minutes",
        "err_nothing_to_change": (
            "Nothing to change: give a new time, days, name, target or enabled flag."
        ),
        "changed_one": "Changed {changes}. It is now {alarm}.",
        "changed_many": "Changed {changes} for {count} alarms. They are now: {alarms}.",
        "err_nothing_ringing_on": "Nothing is ringing on {target}.",
        "err_nothing_ringing_recent": "Nothing is ringing right now. {kind} '{label}' on {target} {how}.",
        "how_device": "was stopped on the device {ago} seconds ago",
        "how_user": "was already dismissed {ago} seconds ago",
        "how_snooze": "was snoozed {ago} seconds ago",
        "how_other": "already stopped {ago} seconds ago",
        "err_nothing_ringing": "Nothing is ringing right now.",
        "snooze_at": " at {time} ({relative})",
        "snooze_item": "{session}, rings again{when}",
        "snoozed": "Snoozed {list}.",
        "stopped": "Stopped {list}.",
        # -- manager (AlarmError)
        "err_unknown_target": "Unknown voice satellite '{target}'",
        "err_time_past": "That time is already in the past",
        "err_duration": "Duration must be at least 1 second",
        "err_no_such_alarm": "No alarm with id {alarm_id}",
        "err_unknown_field": "Unknown field {field}",
        "err_skip_not_recurring": (
            "Only repeating alarms can skip an occurrence; delete it instead"
        ),
        "err_snooze_minutes": "Snooze must be at least 1 minute",
        # -- parsing (ParseError)
        "err_time_format": "'{text}' is not a valid time, use 24-hour HH:MM",
        "err_time_invalid": "'{text}' is not a valid time",
        "err_weekday": "'{text}' is not a weekday",
        "err_weekday_int": "'{text}' is not a weekday (use 0=Monday .. 6=Sunday)",
        "err_date_invalid": "'{text}' is not a valid date",
        "err_date_format": "'{text}' is not a valid date, use YYYY-MM-DD",
    },
    "de": {
        "and": " und ",
        "days_every_day": "täglich",
        "days_weekdays": "wochentags",
        "days_weekends": "am Wochenende",
        "days_every": "jeden {days}",
        "rel_past": "in der Vergangenheit",
        "rel_under_minute": "in weniger als einer Minute",
        "rel_in": "in {a}",
        "rel_in_two": "in {a} und {b}",
        "unit_day": "{n} Tag",
        "unit_days": "{n} Tagen",
        "unit_hour": "{n} Stunde",
        "unit_hours": "{n} Stunden",
        "unit_minute": "{n} Minute",
        "unit_minutes": "{n} Minuten",
        "unit_seconds": "{n} Sekunden",
        "long_day": "{weekday}, {day}. {month}",
        "long_day_year": "{weekday}, {day}. {month} {year}",
        "day_today": "heute",
        "day_tomorrow": "morgen ({day})",
        "day_on": "am {day}",
        "when_at": "{day} um {time}",
        "schedule_recurring": "{time} {days}",
        "schedule_date": "{time} am {day}",
        "kind_alarm": "Wecker",
        "kind_reminder": "Erinnerung",
        "kind_alarm_repeating": "wiederkehrender Wecker",
        "kind_alarm_once": "einmaliger Wecker",
        "kind_reminder_repeating": "wiederkehrende Erinnerung",
        "kind_reminder_once": "einmalige Erinnerung",
        "the_alarm": "der Wecker",
        "the_reminder": "die Erinnerung",
        "The_alarm": "Der Wecker",
        "The_reminder": "Die Erinnerung",
        "label_alarm": "Wecker",
        "label_reminder": "Erinnerung",
        "spoken_reminder": "Erinnerung: {text}",
        "snoozed_name": "{label} (Schlummern)",
        "alarm_desc": "{kind} '{label}' um {schedule}",
        "alarm_desc_saying": " mit dem Text '{message}'",
        "alarm_desc_on": " auf {where}",
        "alarm_desc_disabled": " (deaktiviert)",
        "alarm_desc_skipping": ", {when} wird übersprungen",
        "alarm_desc_next": ", nächstes Mal {when} ({relative})",
        "alarm_desc_past": " (liegt bereits in der Vergangenheit)",
        "brief_reminder": "eine Erinnerung '{label}' um {time}",
        "brief_skipped": "übersprungen",
        "paused": " (pausiert)",
        "session": "{kind} '{label}' auf {target}{state}",
        "none_configured": "keine konfiguriert",
        "id_suffix": " [ID {alarm_id}]",
        "err_unknown_satellite": (
            "Ich kenne keinen Sprachsatelliten namens '{query}'. Verfügbare Satelliten: {names}."
        ),
        "err_ambiguous_satellite": "'{query}' passt auf mehrere Satelliten: {names}. Welcher?",
        "err_no_current_satellite": (
            "Ich kann nicht erkennen, welchen Sprachsatelliten du benutzt, bitte nenne den "
            "Zielsatelliten. Verfügbare Satelliten: {names}."
        ),
        "err_no_alarm_id": "Es gibt keinen Wecker mit der ID {alarm_id}.",
        "err_none_configured": "Es sind keine Wecker oder Erinnerungen eingerichtet.",
        "err_no_match": "Kein Wecker passt. Eingerichtet: {all}.",
        "err_which_one": "{count} Wecker passen, welchen soll ich {verb}? {all}.",
        "verb_delete": "löschen",
        "verb_skip": "überspringen",
        "verb_reinstate": "wiederherstellen",
        "verb_change": "ändern",
        "err_invalid_input": "Ungültige Eingabe: {error}",
        "err_date_and_weekdays": (
            "Ein Wecker wiederholt sich entweder an Wochentagen oder klingelt einmal an einem "
            "Datum, nicht beides. Lass das Datum weg; ein wiederkehrender Wecker beginnt mit "
            "seinem nächsten Termin."
        ),
        "created": "Erstellt: {alarm}.",
        "repeats_once": "einmalig",
        "scope_on": " auf {names}",
        "list_none": "Es sind keine Wecker oder Erinnerungen eingerichtet{scope}.",
        "list_have": "Du hast {count} {noun}{scope}: {listing}.",
        "noun_alarm": "Wecker",
        "noun_alarms": "Wecker",
        "list_ringing": "Klingelt gerade: {list}.",
        "day_none": "{when} gibt es keine Wecker oder Erinnerungen{scope}.",
        "day_next": " Als Nächstes: {alarm}.",
        "day_have": "{when} hast du {count} {noun}{scope}: {segments}.",
        "segment_on": "{items} auf {target}",
        "err_delete_none": "Es gibt keine Wecker zum Löschen.",
        "err_delete_which": (
            "Es gibt {count} Wecker, welchen soll ich löschen? {all}. Mit all=true werden alle "
            "gelöscht."
        ),
        "deleted": "Gelöscht: {list}.",
        "rings_next": "'{label}' klingelt als Nächstes {when}",
        "err_skip_only_next": "Ich kann nur den allernächsten Termin überspringen: {later}.",
        "err_no_skipped": "Der Wecker '{label}' auf {where} hat keinen übersprungenen Termin.",
        "reinstated": "Wecker '{label}' auf {where}{when} wiederhergestellt",
        "rings_next_clause": "; er klingelt als Nächstes {when} ({relative})",
        "err_already_skipped": "Der Wecker '{label}' auf {where} {when} ist bereits übersprungen{next}.",
        "skipping": "Wecker '{label}' auf {where}{when} wird übersprungen",
        "rings_next_sentence": ". Er klingelt als Nächstes {when} ({relative})",
        "err_none_skipped": "Keiner der passenden Wecker hat einen übersprungenen Termin.",
        "skip_segment": "{items} auf {where} {day}",
        "skip_many": "{count} Wecker werden übersprungen: {segments}.",
        "reinstate_many": "{count} Wecker wiederhergestellt: {segments}.",
        "next_ring": " Der nächste Termin ist {when} ({relative}).",
        "err_update_none": "Es gibt keine Wecker zum Ändern.",
        "change_time": "Uhrzeit auf {time}",
        "change_once": "Wiederholung auf einmalig",
        "change_repeat": "Wiederholung auf {days}",
        "change_date": "Datum auf {date}",
        "change_name": "Name auf '{name}'",
        "change_message": "Nachricht auf '{message}'",
        "change_target": "Satellit auf {target}",
        "change_enabled": "aktiviert",
        "change_disabled": "deaktiviert",
        "change_duration": "Klingeldauer auf {minutes} Minuten",
        "err_nothing_to_change": (
            "Nichts zu ändern: gib eine neue Uhrzeit, neue Tage, einen neuen Namen, ein neues "
            "Ziel oder enabled an."
        ),
        "changed_one": "Geändert: {changes}. Jetzt: {alarm}.",
        "changed_many": "Geändert: {changes} für {count} Wecker. Jetzt: {alarms}.",
        "err_nothing_ringing_on": "Auf {target} klingelt nichts.",
        "err_nothing_ringing_recent": "Gerade klingelt nichts. {kind} '{label}' auf {target} {how}.",
        "how_device": "wurde vor {ago} Sekunden am Gerät gestoppt",
        "how_user": "wurde vor {ago} Sekunden bereits beendet",
        "how_snooze": "wurde vor {ago} Sekunden auf Schlummern gestellt",
        "how_other": "ist seit {ago} Sekunden beendet",
        "err_nothing_ringing": "Gerade klingelt nichts.",
        "snooze_at": " um {time} ({relative})",
        "snooze_item": "{session}, klingelt wieder{when}",
        "snoozed": "Auf Schlummern gestellt: {list}.",
        "stopped": "Gestoppt: {list}.",
        "err_unknown_target": "Unbekannter Sprachsatellit '{target}'",
        "err_time_past": "Dieser Zeitpunkt liegt bereits in der Vergangenheit",
        "err_duration": "Die Dauer muss mindestens 1 Sekunde betragen",
        "err_no_such_alarm": "Kein Wecker mit der ID {alarm_id}",
        "err_unknown_field": "Unbekanntes Feld {field}",
        "err_skip_not_recurring": (
            "Nur wiederkehrende Wecker können einen Termin überspringen; lösche ihn stattdessen"
        ),
        "err_snooze_minutes": "Schlummern muss mindestens 1 Minute dauern",
        "err_time_format": "'{text}' ist keine gültige Uhrzeit, verwende HH:MM (24-Stunden-Format)",
        "err_time_invalid": "'{text}' ist keine gültige Uhrzeit",
        "err_weekday": "'{text}' ist kein Wochentag",
        "err_weekday_int": "'{text}' ist kein Wochentag (verwende 0=Montag .. 6=Sonntag)",
        "err_date_invalid": "'{text}' ist kein gültiges Datum",
        "err_date_format": "'{text}' ist kein gültiges Datum, verwende JJJJ-MM-TT",
    },
}

SUPPORTED_LANGUAGES: Final = tuple(STRINGS)

_default_language = DEFAULT_LANGUAGE


def normalize_language(language: str | None) -> str:
    """Map a language tag such as 'de-CH' to a supported language, else English."""
    if not language:
        return DEFAULT_LANGUAGE
    code = language.replace("_", "-").split("-", 1)[0].lower()
    return code if code in STRINGS else DEFAULT_LANGUAGE


def set_default_language(language: str | None) -> None:
    """Record the instance language (used where no conversation language exists)."""
    global _default_language  # noqa: PLW0603
    _default_language = normalize_language(language)


def default_language() -> str:
    """The instance language."""
    return _default_language


def tr(language: str, key: str, **params: Any) -> str:
    """Render a string in ``language`` (falling back to English per key)."""
    table = STRINGS.get(language) or STRINGS[DEFAULT_LANGUAGE]
    template = table.get(key)
    if template is None:
        template = STRINGS[DEFAULT_LANGUAGE][key]
    return template.format(**params) if params else template


class LocalizedError(Exception):
    """An error whose message can be rendered in any supported language."""

    def __init__(self, key: str, **params: Any) -> None:
        self.key = key
        self.params = params
        super().__init__(tr(DEFAULT_LANGUAGE, key, **params))

    def localized(self, language: str) -> str:
        """The message in ``language``."""
        return tr(language, self.key, **self.params)
