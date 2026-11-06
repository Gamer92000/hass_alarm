"""Portuguese responses, labels and input words (the English suite covers the wording there)."""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory

from custom_components.voice_alarms.const import (
    INTENT_DELETE,
    INTENT_DISMISS,
    INTENT_LIST,
    INTENT_SET,
    INTENT_SKIP_NEXT,
    INTENT_UPDATE,
    KIND_REMINDER,
)
from custom_components.voice_alarms.i18n import (
    default_language,
    format_clock,
    normalize_language,
    set_default_language,
)
from custom_components.voice_alarms.manager import AlarmError
from custom_components.voice_alarms.models import (
    Alarm,
    ParseError,
    parse_date,
    parse_time,
    parse_weekdays,
)
from custom_components.voice_alarms.speech import (
    describe_alarm,
    format_days,
    format_relative,
    format_when,
)
from homeassistant.components.assist_pipeline import async_get_pipeline, async_update_pipeline
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.util import dt as dt_util

from .conftest import slot

TZ = ZoneInfo("America/Sao_Paulo")
START = datetime(2026, 9, 7, 10, 0, tzinfo=TZ)  # Monday


@pytest.fixture(autouse=True)
def _reset_default_language():
    yield
    set_default_language("en")


@pytest.fixture
def local_tz():
    old = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(TZ)
    yield
    dt_util.set_default_time_zone(old)


@pytest.fixture
async def ready(hass: HomeAssistant, freezer: FrozenDateTimeFactory, setup_integration, manager):
    await hass.config.async_set_time_zone("America/Sao_Paulo")
    freezer.move_to(START)
    return manager


async def handle(
    hass: HomeAssistant,
    intent_type: str,
    device_id: str | None = None,
    language: str = "pt-BR",
    **slots,
):
    return await intent.async_handle(
        hass,
        "test",
        intent_type,
        {k: slot(v) for k, v in slots.items()},
        device_id=device_id,
        language=language,
    )


def speech(response: intent.IntentResponse) -> str:
    return response.speech["plain"]["speech"]


# ----------------------------------------------------------------- i18n table


@pytest.mark.parametrize(("tag", "expected"), [("pt", "pt"), ("pt-BR", "pt"), ("pt_BR", "pt")])
def test_normalize_language(tag: str, expected: str) -> None:
    assert normalize_language(tag) == expected


# --------------------------------------------------------------------- speech


def test_format_days_portuguese() -> None:
    assert format_days([0, 1, 2, 3, 4], "pt") == "nos dias úteis"
    assert format_days([5, 6], "pt") == "nos fins de semana"
    assert format_days([0, 1, 2, 3, 4, 5, 6], "pt") == "todos os dias"
    assert format_days([0, 2, 5], "pt") == "às segundas, às quartas e aos sábados"
    assert format_days([6], "pt") == "aos domingos"


@pytest.mark.parametrize(
    ("at", "said"),
    [
        (time(3, 0), "às três horas"),
        (time(3, 15), "às três horas e quinze minutos"),
        (time(3, 30), "às três e meia"),
        (time(15, 0), "às quinze horas"),
        (time(1, 0), "à uma hora"),
        (time(1, 1), "à uma hora e um minuto"),
        (time(2, 2), "às duas horas e dois minutos"),
        (time(21, 21), "às vinte e uma horas e vinte e um minutos"),
        (time(22, 0), "às vinte e duas horas"),
        (time(0, 0), "à meia-noite"),
        (time(0, 30), "à meia-noite e meia"),
        (time(12, 0), "ao meio-dia"),
        (time(12, 15), "ao meio-dia e quinze minutos"),
        (time(23, 59), "às vinte e três horas e cinquenta e nove minutos"),
    ],
)
def test_format_clock_portuguese(at: time, said: str) -> None:
    # Text-to-speech reads '03:00' as 'zero três zero zero'.
    assert format_clock(at, "pt", "at") == said
    assert format_clock(at, "pt") == said.split(" ", 1)[1]
    assert format_clock(at, "en", "at") == at.strftime("%H:%M")


def test_format_clock_portuguese_of() -> None:
    assert format_clock(time(1, 0), "pt", "of") == "da uma hora"
    assert format_clock(time(12, 0), "pt", "of") == "do meio-dia"
    assert format_clock(time(7, 0), "pt", "of") == "das sete horas"


def test_format_relative_portuguese() -> None:
    assert format_relative(START + timedelta(hours=20, minutes=5), START, "pt") == (
        "em 20 horas e 5 minutos"
    )
    assert format_relative(START + timedelta(minutes=1), START, "pt") == "em 1 minuto"
    assert format_relative(START + timedelta(hours=1), START, "pt") == "em 1 hora"
    assert format_relative(START + timedelta(days=2, hours=3), START, "pt") == (
        "em 2 dias e 3 horas"
    )
    assert format_relative(START + timedelta(days=1), START, "pt") == "em 1 dia"
    assert format_relative(START - timedelta(seconds=1), START, "pt") == (
        "assim que o satélite voltar"
    )
    assert format_relative(START + timedelta(seconds=30), START, "pt") == "em menos de um minuto"


def test_format_when_portuguese(local_tz) -> None:
    assert format_when(START.replace(hour=18), START, "pt") == "hoje às dezoito horas"
    assert format_when(START + timedelta(days=1, hours=-4, minutes=30), START, "pt") == (
        "amanhã (terça-feira, 8 de setembro) às seis e meia"
    )
    assert format_when(START + timedelta(days=4), START, "pt") == (
        "sexta-feira, 11 de setembro às dez horas"
    )
    assert format_when(datetime(2027, 1, 8, 7, 0, tzinfo=TZ), START, "pt") == (
        "sexta-feira, 8 de janeiro de 2027 às sete horas"
    )


def test_describe_alarm_portuguese(local_tz) -> None:
    alarm = Alarm(
        target="assist_satellite.x", time=time(6, 30), weekdays=[0, 1, 2, 3, 4], name="Trabalho"
    )
    alarm.created = START
    assert describe_alarm(alarm, None, START, language="pt") == (
        "alarme recorrente 'Trabalho' às seis e meia nos dias úteis em assist_satellite.x, "
        "próxima vez amanhã (terça-feira, 8 de setembro) às seis e meia (em 20 horas e 30 minutos)"
    )
    reminder = Alarm(
        target="assist_satellite.x",
        time=time(17, 0),
        date=START.date(),
        kind=KIND_REMINDER,
        name="Ligação",
        message="Ligar para a mãe",
        enabled=False,
    )
    assert describe_alarm(reminder, None, START, language="pt") == (
        "lembrete único 'Ligação' às dezessete horas de segunda-feira, 7 de setembro com a mensagem "
        "'Ligar para a mãe' em assist_satellite.x (desativado)"
    )


# -------------------------------------------------------------------- parsing


def test_parse_portuguese_words(local_tz) -> None:
    assert parse_weekdays("segunda, quarta e sexta") == [0, 2, 4]
    assert parse_weekdays("segunda-feira e quarta-feira") == [0, 2]
    assert parse_weekdays("segunda feira") == [0]
    assert parse_weekdays("às segundas, às quartas e aos sábados") == [0, 2, 5]
    assert parse_weekdays("segundas-feiras e sextas-feiras") == [0, 4]
    assert parse_weekdays("dias úteis") == [0, 1, 2, 3, 4]
    assert parse_weekdays("de segunda a sexta") == [0, 1, 2, 3, 4]
    assert parse_weekdays("todos os dias") == [0, 1, 2, 3, 4, 5, 6]
    assert parse_weekdays("nos fins de semana") == [5, 6]
    assert parse_weekdays(["Seg", "Ter", "Sáb"]) == [0, 1, 5]
    assert parse_weekdays("domingos") == [6]
    assert parse_date("hoje", START) == START.date()
    assert parse_date("amanhã", START) == START.date() + timedelta(days=1)
    assert parse_date("depois de amanhã", START) == START.date() + timedelta(days=2)
    assert parse_date("+3 dias", START) == START.date() + timedelta(days=3)
    assert parse_date("sexta", START).isoformat() == "2026-09-11"
    assert parse_date("sexta-feira", START).isoformat() == "2026-09-11"
    assert parse_date("na sexta", START).isoformat() == "2026-09-11"
    assert parse_date("próxima segunda", START).isoformat() == "2026-09-14"
    assert parse_date("na próxima segunda-feira", START).isoformat() == "2026-09-14"
    assert parse_date("segunda", START).isoformat() == "2026-09-07"
    assert parse_time("7h") == time(7, 0)
    assert parse_time("7h30") == time(7, 30)
    assert parse_time("18 horas") == time(18, 0)
    assert parse_time("às 7") == time(7, 0)
    assert parse_time("7 da manhã") == time(7, 0)
    assert parse_time("2 da madrugada") == time(2, 0)
    assert parse_time("3 da tarde") == time(15, 0)
    assert parse_time("às 9 da noite") == time(21, 0)
    assert parse_time("meio-dia") == time(12, 0)
    assert parse_time("à meia-noite") == time(0, 0)


def test_parse_errors_are_localized() -> None:
    with pytest.raises(ParseError) as info:
        parse_date("algum dia", START)
    assert str(info.value) == "'algum dia' is not a valid date, use YYYY-MM-DD"
    assert info.value.localized("pt") == "'algum dia' não é uma data válida, use AAAA-MM-DD"
    with pytest.raises(ParseError) as info:
        parse_weekdays("ontem")
    assert info.value.localized("pt") == "'ontem' não é um dia da semana"


# -------------------------------------------------------------------- intents


async def test_set_repeating_portuguese(hass: HomeAssistant, ready, satellites) -> None:
    response = await handle(
        hass,
        INTENT_SET,
        satellites["kitchen"]["device_id"],
        time="07:00",
        weekdays="dias úteis",
        name="Trabalho",
    )
    assert response.response_type == intent.IntentResponseType.ACTION_DONE
    assert speech(response) == (
        "Criado: alarme recorrente 'Trabalho' às sete horas nos dias úteis em Voice PE Kitchen, "
        "próxima vez amanhã (terça-feira, 8 de setembro) às sete horas (em 21 horas)."
    )
    assert response.speech_slots["repeats"] == "nos dias úteis"


async def test_set_reminder_portuguese(hass: HomeAssistant, ready, satellites) -> None:
    response = await handle(
        hass,
        INTENT_SET,
        satellites["kitchen"]["device_id"],
        time="17:00",
        message="Ligar para a mãe",
    )
    assert speech(response) == (
        "Criado: lembrete único 'Ligar para a mãe' às dezessete horas de segunda-feira, 7 de setembro "
        "em Voice PE Kitchen, próxima vez hoje às dezessete horas (em 7 horas)."
    )
    assert response.speech_slots["repeats"] == "uma vez"


async def test_unnamed_alarm_label_in_conversation_language(
    hass: HomeAssistant, ready, satellites
) -> None:
    # The instance stays English; the default label follows the conversation.
    response = await handle(hass, INTENT_SET, satellites["kitchen"]["device_id"], time="17:00")
    assert speech(response).startswith("Criado: alarme único às dezessete horas")
    alarm = ready.get_alarm(response.speech_slots["alarm_id"])
    assert alarm.label == "Alarm 17:00"  # the panel keeps the instance language and digits
    assert alarm.label_in("pt") == "Alarme das dezessete horas"


async def test_list_day_portuguese(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["device_id"]
    await handle(hass, INTENT_SET, kitchen, time="07:00", weekdays="dias úteis", name="Trabalho")
    await handle(hass, INTENT_SET, kitchen, time="07:10", weekdays="dias úteis")
    response = await handle(hass, INTENT_LIST, kitchen, date="amanhã")
    assert speech(response) == (
        "Para amanhã (terça-feira, 8 de setembro) você tem 2 alarmes: sete horas (Trabalho) e sete horas e dez minutos."
    )
    response = await handle(hass, INTENT_LIST, kitchen, date="domingo")
    assert speech(response).startswith(
        "Não há alarmes nem lembretes para domingo, 13 de setembro. O próximo é o alarme "
        "recorrente 'Trabalho' às sete horas nos dias úteis em Voice PE Kitchen"
    )
    response = await handle(hass, INTENT_LIST, kitchen)
    assert speech(response).startswith("Você tem 2 alarmes: 1. alarme recorrente 'Trabalho'")


async def test_skip_and_update_portuguese(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["device_id"]
    await handle(hass, INTENT_SET, kitchen, time="07:00", weekdays="dias úteis", name="Trabalho")
    response = await handle(hass, INTENT_SKIP_NEXT, kitchen, name="Trabalho")
    assert speech(response) == (
        "Vou pular o alarme 'Trabalho' em Voice PE Kitchen amanhã (terça-feira, 8 de setembro) "
        "às sete horas. O próximo toque é quarta-feira, 9 de setembro às sete horas "
        "(em 1 dia e 21 horas)."
    )
    response = await handle(hass, INTENT_SKIP_NEXT, kitchen, name="Trabalho")
    assert response.response_type == intent.IntentResponseType.ERROR
    assert speech(response) == (
        "O alarme 'Trabalho' em Voice PE Kitchen amanhã (terça-feira, 8 de setembro) às sete horas "
        "já está pulado; o próximo toque é quarta-feira, 9 de setembro às sete horas "
        "(em 1 dia e 21 horas)."
    )
    response = await handle(hass, INTENT_SKIP_NEXT, kitchen, name="Trabalho", undo=True)
    assert speech(response) == (
        "Restaurei o alarme 'Trabalho' em Voice PE Kitchen amanhã (terça-feira, 8 de setembro) "
        "às sete horas; o próximo toque é amanhã (terça-feira, 8 de setembro) às sete horas "
        "(em 21 horas)."
    )
    response = await handle(
        hass, INTENT_UPDATE, kitchen, name="Trabalho", new_time="06:45", new_weekdays="seg, qua"
    )
    assert speech(response) == (
        "Pronto: horário alterado para seis horas e quarenta e cinco minutos e agora toca às segundas e às quartas. Ficou "
        "assim: alarme recorrente 'Trabalho' às seis horas e quarenta e cinco minutos às segundas e às quartas em Voice PE "
        "Kitchen, próxima vez quarta-feira, 9 de setembro às seis horas e quarenta e cinco minutos (em 1 dia e 20 horas)."
    )
    response = await handle(hass, INTENT_UPDATE, kitchen, name="Trabalho", new_weekdays="uma vez")
    assert speech(response).startswith("Pronto: agora toca uma vez só. Ficou assim: alarme único")


async def test_errors_portuguese(hass: HomeAssistant, ready, satellites) -> None:
    kitchen = satellites["kitchen"]["device_id"]
    response = await handle(hass, INTENT_DELETE, kitchen)
    assert response.response_type == intent.IntentResponseType.ERROR
    assert speech(response) == "Não há alarmes nem lembretes configurados."
    response = await handle(hass, INTENT_DISMISS, kitchen)
    assert speech(response) == "Nada está tocando agora."
    response = await handle(hass, INTENT_SET, kitchen, time="abc")
    assert speech(response) == "'abc' não é um horário válido, use HH:MM no formato 24 horas"
    response = await handle(hass, INTENT_SET, kitchen, time="09:00", date="hoje")
    assert speech(response) == "Esse horário já passou"
    response = await handle(hass, INTENT_SET, kitchen, time="09:00", target="Garagem")
    assert speech(response) == (
        "Não conheço nenhum satélite de voz chamado 'Garagem'. Satélites disponíveis: "
        "Voice PE Bedroom e Voice PE Kitchen."
    )


# ----------------------------------------------------------- instance language


async def test_instance_language_follows_core_config(hass: HomeAssistant, ready) -> None:
    await hass.config.async_update(language="pt-BR")
    await hass.async_block_till_done()
    assert default_language() == "pt"
    assert Alarm(target="assist_satellite.x", time=time(7, 0)).label == "Alarme 07:00"
    assert Alarm(target="assist_satellite.x", time=time(7, 0), kind=KIND_REMINDER).label == (
        "Lembrete 07:00"
    )
    with pytest.raises(AlarmError) as info:
        await ready.async_delete_alarm("nope")
    assert info.value.localized("pt") == "Nenhum alarme com o id nope"
    await hass.config.async_update(language="en")
    await hass.async_block_till_done()
    assert default_language() == "en"


async def test_reminder_spoken_in_portuguese(
    hass: HomeAssistant, ready, satellites, announce_calls
) -> None:
    # The satellite speaks in its pipeline's language, whatever the instance language is.
    await async_update_pipeline(hass, async_get_pipeline(hass), language="pt", tts_language="pt_BR")
    target = ready.target(satellites["kitchen"]["satellite"])
    session = await ready.async_ring(
        target, kind=KIND_REMINDER, message="Levar o lixo para fora", label="Teste", origin="test"
    )
    for _ in range(10):
        if announce_calls:
            break
        await asyncio.sleep(0)
    assert announce_calls[0].data["message"] == "Lembrete: Levar o lixo para fora"
    session.dismiss()
    await session.wait_finished()


async def test_snoozed_name_in_portuguese(
    hass: HomeAssistant, ready, satellites, announce_calls
) -> None:
    set_default_language("pt-BR")
    target = ready.target(satellites["kitchen"]["satellite"])
    session = await ready.async_ring(target, label="Cochilo", duration=5, origin="test")
    snoozed = await ready.async_snooze(session, 5)
    await session.wait_finished()
    assert snoozed.name == "Cochilo (soneca)"


async def test_service_error_in_instance_language(hass: HomeAssistant, ready) -> None:
    from homeassistant.exceptions import ServiceValidationError

    set_default_language("pt-BR")
    with pytest.raises(ServiceValidationError) as info:
        await hass.services.async_call(
            "voice_alarms", "delete_alarm", {"alarm_id": "nope"}, blocking=True
        )
    assert str(info.value) == "Nenhum alarme com o id nope"
