"""Преобразует сохранённые поля отчёта в типы колонок снимка."""

from decimal import Decimal
from typing import Any

from src.parser.report import parse_date


REPORT_COLUMNS = {
    "name": ("Объект", "text"),
    "stage": ("Стадия", "text"),
    "state": ("Состояние", "text"),
    "customer": ("Заказчик", "text"),
    "status": ("Статус", "text"),
    "conclusion": ("Вывод", "text"),
    "progress": ("Готовность, %", "int"),
    "organization_count": ("Организаций-участников", "int"),
    "organizations_without_team": ("Организаций без команды", "int"),
    "participant_count": ("Участников", "int"),
    "unsigned_count": ("Из них без подписи", "int"),
    "operation_count": ("Операций всего", "int"),
    "operations_last_7_days": ("Операций за период (последние 7 дн.)", "int"),
    "days_without_exchange": ("Дней без обмена", "int"),
    "overdue_days": ("Просрочка этапа, дн.", "int"),
    "last_operation_on": ("Последняя операция", "date"),
    "pir_plan_start": ("Начало ПИР, план", "date"),
    "pir_plan_end": ("Окончание ПИР, план", "date"),
    "pir_actual_start": ("Начало ПИР, факт", "date"),
    "pir_actual_end": ("Окончание ПИР, факт", "date"),
    "smr_plan_start": ("Начало СМР, план", "date"),
    "smr_plan_end": ("Окончание СМР, план", "date"),
    "smr_actual_start": ("Начало СМР, факт", "date"),
    "smr_actual_end": ("Окончание СМР, факт", "date"),
    "contract_cost": ("Стоимость по договорам, руб.", "money"),
    "spent": ("Освоено, руб.", "money"),
    "balance": ("Остаток, руб.", "money"),
}


def project_snapshot_values(report: dict[str, Any]) -> dict[str, Any]:
    values = {}
    for column, (label, kind) in REPORT_COLUMNS.items():
        value = report.get(label)
        if kind == "date":
            value = parse_date(value) if isinstance(value, str) else None
        elif kind == "money":
            value = Decimal(str(value)) if type(value) in (int, float) else None
        elif kind == "int":
            value = value if type(value) is int and 0 <= value <= (100 if column == "progress" else 2147483647) else None
        else:
            value = value if isinstance(value, str) else None
        values[column] = value
    return values
