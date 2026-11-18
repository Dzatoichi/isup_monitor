from collections import defaultdict
from datetime import timedelta
from statistics import mean

from .dao import AnalyticsDAO


def is_missing(value):
    return value is None or isinstance(value, str) and not value.strip()


def week_start(day):
    return day - timedelta(days=day.weekday())


def metrics(reports):
    progress = [row["Готовность, %"] for row in reports if row.get("Готовность, %") is not None]
    operations = [row["Операций за период (последние 7 дн.)"] for row in reports
                  if row.get("Операций за период (последние 7 дн.)") is not None]
    unsigned = [row["Из них без подписи"] for row in reports if row.get("Из них без подписи") is not None]
    return {
        "objects": len(reports),
        "pir": sum(row.get("Стадия") == "ПИР" for row in reports),
        "smr": sum(row.get("Стадия") == "СМР" for row in reports),
        "red": sum(row.get("Статус") == "красный" for row in reports),
        "yellow": sum(row.get("Статус") == "жёлтый" for row in reports),
        "green": sum(row.get("Статус") == "зелёный" for row in reports),
        "with_exchange": sum(value > 0 for value in operations),
        "without_exchange": sum(value == 0 for value in operations),
        "operation_count": sum(operations) if operations else None,
        "operation_coverage": len(operations),
        "unsigned": sum(unsigned) if unsigned else None,
        "overdue": sum((row.get("Просрочка этапа, дн.") or 0) > 0 for row in reports),
        "progress": round(mean(progress), 1) if progress else None,
    }


class AnalyticsService:
    @staticmethod
    async def summary(session, snapshot, scope):
        current_week = week_start(snapshot.exported_on)
        since = current_week - timedelta(weeks=7)
        snapshots = await AnalyticsDAO.get_snapshots(session, snapshot, since)
        by_week = {week_start(item.exported_on): item for item in snapshots}
        by_week[current_week] = snapshot
        reports = defaultdict(list)
        for identifier, _, report in await AnalyticsDAO.get_reports(
            session, [item.id for item in by_week.values()], scope
        ):
            reports[identifier].append(report)
        weeks = []
        previous = None
        for index in range(8):
            day = since + timedelta(weeks=index)
            item = by_week.get(day)
            values = metrics(reports[item.id]) if item else None
            delta = values["objects"] - previous["objects"] if values is not None and previous is not None else None
            weeks.append((day, item, values, delta))
            previous = values
        return metrics(reports[snapshot.id]), weeks

    @staticmethod
    async def completeness(session, snapshot, scope):
        reports = await AnalyticsDAO.get_reports(session, [snapshot.id], scope)
        entries = []
        for _, number, row in reports:
            stage = row.get("Стадия")
            fields = ["Объект", "Стадия", "Состояние", "Готовность, %", "Заказчик",
                      "Строительный заместитель", "Руководитель проекта", "Стоимость по договорам, руб."]
            if stage in {"ПИР", "СМР"}:
                fields.extend((f"Начало {stage}, план", f"Окончание {stage}, план"))
            missing = [field for field in fields if is_missing(row.get(field))]
            if missing:
                entries.append((number, row, missing))
        return entries

    @staticmethod
    async def problems(session, snapshot, scope):
        reports = await AnalyticsDAO.get_reports(session, [snapshot.id], scope)
        problems = {number: row for _, number, row in reports if row.get("Статус") in {"красный", "жёлтый"}}
        if not problems:
            return []
        periods = {}
        for number, day, status in await AnalyticsDAO.get_latest_status_changes(session, list(problems), snapshot):
            if number not in periods or periods[number][0] != status:
                periods[number] = (status, day)
        result = []
        for number, row in problems.items():
            status, day = periods.get(number, (None, snapshot.exported_on))
            duration = (snapshot.exported_on - day).days if status == row["Статус"] else 0
            result.append((number, row, duration))
        return sorted(result, key=lambda entry: (entry[1]["Статус"] != "красный", -entry[2], entry[0]))
