"""Строка листа «Объекты» по разделу 5.1 ТЗ."""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo


REPORT_TIMEZONE = ZoneInfo("Asia/Krasnoyarsk")
DATE_FIELDS = {
    "Начало ПИР, план": "pir_plan_start",
    "Окончание ПИР, план": "pir_plan_end",
    "Начало ПИР, факт": "pir_actual_start",
    "Окончание ПИР, факт": "pir_actual_end",
    "Начало СМР, план": "smr_plan_start",
    "Окончание СМР, план": "smr_plan_end",
    "Начало СМР, факт": "smr_actual_start",
    "Окончание СМР, факт": "smr_actual_end",
}


def parse_passport(text):
    """Извлекает состояние и финансовые показатели из текста паспорта объекта."""
    fields = {}
    # В этом блоке ИСУП выводит сначала подписи полей, затем их значения.
    state = re.search(
        r"^Состояние объекта\nСостояние площадки\nРазрешение на строительство\n"
        r"Описание объекта\n([^\n]+)",
        text,
        re.MULTILINE,
    )
    if state and state[1].strip() not in {"", "Значение не задано", "Эффект от реализации"}:
        fields["state"] = state[1].strip()

    # Приоритет у договорной суммы и поля «Освоено». Если их нет, берём плановую сумму и оплату.
    for label, key in (
        ("Законтрактовано", "contract_cost"),
        ("Стоимость объекта (плановая)", "contract_cost"),
        ("Освоено", "spent"),
        ("Оплачено", "spent"),
        ("Остаток", "reported_balance"),
    ):
        amount = re.search(
            rf"^[^\S\n]*{re.escape(label)}[^\S\n]*\n[^\S\n]*"
            r"(\d[\d \u00a0\u202f]*(?:[.,]\d+)?)(?:[ \u00a0\u202f]*\([^\n]*%\))?[^\S\n]*$",
            text,
            re.MULTILINE,
        )
        if amount and key not in fields:
            fields[key] = float("".join(amount[1].split()).replace(",", "."))
    return fields


def parse_date(value):
    """Приводит дату или отметку времени к календарной дате отчёта."""
    if isinstance(value, datetime):
        return value.astimezone(REPORT_TIMEZONE).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    if value:
        for pattern in ("%d.%m.%Y", "%d.%m.%Y, %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y, %I:%M:%S %p"):
            try:
                return datetime.strptime(value, pattern).date()
            except ValueError:
                continue
    return None


def display_date(value):
    """Форматирует дату для отчёта, сохраняя пустое значение как None."""
    return value.strftime("%d.%m.%Y") if value is not None else None


def make_object_report(project, *, exported_on, exchange_threshold=7):
    """Формирует 34 поля отчёта из данных одного объекта и рассчитывает показатели."""
    # Текущий список participants содержит организации. Для подсчёта людей нужны отдельные данные.
    organizations = project.get("participants")
    organization_count = project.get("edo_organization_count")
    customer = project.get("customer")
    if organizations is not None:
        # Одна организация может встречаться в нескольких ролях. Сопоставляем по ИНН или названию.
        if organization_count is None:
            organization_count = len({
                row.get("inn") or " ".join(row["organization"].casefold().split())
                for row in organizations
            })
        if not customer:
            customers = dict.fromkeys(
                row["organization"] for row in organizations
                if row["role"].strip().casefold() == "заказчик"
            )
            customer = "; ".join(customers) or None

    dates = {field: parse_date(project.get(key)) for field, key in DATE_FIELDS.items()}
    stage = project.get("stage")
    # Просрочка относится к текущей стадии и считается до её фактического завершения.
    overdue = None
    if stage in {"ПИР", "СМР"}:
        planned_end = dates[f"Окончание {stage}, план"]
        actual_end = dates[f"Окончание {stage}, факт"]
        if actual_end is not None:
            overdue = 0
        elif planned_end is not None:
            overdue = max(0, (exported_on - planned_end).days)

    operations = project.get("operation_dates")
    total = recent = last = inactive_days = None
    # Пустой список означает отсутствие операций. None означает, что данных об операциях нет.
    if operations is not None:
        total = len(operations)
        operation_dates = [parse_date(value) for value in operations]
        if all(day is not None and day <= exported_on for day in operation_dates):
            # Семь календарных дней включают дату выгрузки.
            cutoff = exported_on - timedelta(days=6)
            recent = sum(day >= cutoff for day in operation_dates)
            last = max(operation_dates, default=None)
            if last is not None:
                inactive_days = (exported_on - last).days

    tracked = project.get("exchange_tracked")
    if "приостанов" in (project.get("state") or "").casefold():
        tracked = False
    without_team = project.get("organizations_without_team")
    people = project.get("person_count")
    unsigned = project.get("unsigned_count")
    stagnation = project.get("progress_stalled_8_weeks") if stage == "СМР" else (
        False if stage else None
    )
    required_missing = project.get("required_fields_missing")
    too_many_unsigned = (
        unsigned * 2 > people if people is not None and unsigned is not None else None
    )
    status = None
    reasons = []
    # Серый статус применяется к объектам, по которым обмен не отслеживается.
    if tracked is False:
        status = "серый"
        reasons.append("обмен не отслеживается")
    else:
        if total == 0:
            reasons.append("событий не зафиксировано")
        elif inactive_days is not None and inactive_days > exchange_threshold:
            reasons.append(f"нет обмена более {exchange_threshold} дней")
        if overdue:
            reasons.append("просрочка этапа")

        # None означает, что условие нельзя проверить. Красный имеет приоритет над жёлтым.
        red = (
            inactive_days > 14 if inactive_days is not None else False if total == 0 else None,
            overdue > 30 if overdue is not None else None,
            stagnation,
            too_many_unsigned,
        )
        yellow = (
            inactive_days >= 8 if inactive_days is not None else False if total == 0 else None,
            overdue > 0 if overdue is not None else None,
            without_team > 0 if without_team is not None else None,
            required_missing,
        )
        if tracked is True:
            if any(red):
                status = "красный"
            elif all(value is False for value in red):
                if any(yellow):
                    status = "жёлтый"
                elif all(value is False for value in yellow):
                    status = "зелёный"
        if status == "зелёный" and not reasons:
            reasons.append("нет проблем")

    progress = project.get("progress")
    number = project.get("oks_number")
    external_id = project.get("external_id")
    contract_cost = project.get("contract_cost")
    spent = project.get("spent")
    balance = project.get("reported_balance")
    if contract_cost is not None and spent is not None:
        # Вычитаем суммы в десятичном виде, чтобы избежать погрешности двоичной арифметики.
        balance = float(Decimal(str(contract_cost)) - Decimal(str(spent)))

    return {
        "Объект": project.get("name"),
        "Стадия": stage,
        "Состояние": project.get("state"),
        "Готовность, %": progress if type(progress) is int and 0 <= progress <= 100 else None,
        "Информационная система": "ИСУП",
        "Подключённые модули": project.get("modules"),
        "Организаций-участников": organization_count,
        "Организаций без команды": without_team,
        "Участников": people,
        "Из них без подписи": unsigned,
        "Операций всего": total,
        "Операций за период (последние 7 дн.)": recent,
        "Последняя операция": display_date(last),
        "Дней без обмена": inactive_days,
        "Вывод": "; ".join(reasons) or None,
        "Статус": status,
        "Заказчик": customer,
        "Номер в ИСУП": int(number) if number is not None and str(number).isdigit() else None,
        "Идентификатор в ВИС": external_id if re.fullmatch(r"[0-9a-fA-F]{24}", external_id or "") else None,
        "Строительный заместитель": project.get("construction_deputy"),
        "Руководитель проекта": project.get("project_manager"),
        **{field: display_date(value) for field, value in dates.items()},
        "Просрочка этапа, дн.": overdue,
        "Стоимость по договорам, руб.": contract_cost,
        "Освоено, руб.": spent,
        "Остаток, руб.": balance,
        "Риски": project.get("risks"),
    }


# Единый порядок полей для JSON парсера и ответа API после чтения из JSONB.
REPORT_FIELDS = tuple(make_object_report({}, exported_on=date.min))
