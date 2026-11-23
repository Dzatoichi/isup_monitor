"""Показатели контроля по объекту без подмены неизвестных данных отрицательным ответом."""

from src.parser.general_journal import registration_state


ROLE_LABELS = {
    "CUSTOMER": "Заказчик",
    "TECHNICAL_CUSTOMER": "Технический заказчик",
    "GENERAL_DESIGNER": "Генеральный проектировщик",
    "DESIGNER": "Проектировщик",
    "GENERAL_CONTRACTOR": "Генеральный подрядчик",
    "CONTRACTOR": "Подрядчик",
    "AUTHOR_SUPERVISION": "Авторский надзор",
    "BUILD_CONTROL": "Строительный контроль",
    "ANOTHER_PERSON": "Иное лицо",
}


def paginate_monitoring(rows, page, page_size=10, search=""):
    """Делит таблицу на страницы, сохраняя показатели по всему доступному снимку."""
    search = " ".join(search.split())
    needle = search.casefold()
    matching = [row for row in rows if needle in " ".join(row.get("name", "").split()).casefold()
                or needle in str(row.get("number", ""))] if needle else rows
    total = len(matching)
    page_count = max(1, (total + page_size - 1) // page_size)
    page = min(page, page_count)
    offset = (page - 1) * page_size
    return {
        "monitoring": matching[offset:offset + page_size],
        "search": search, "unfiltered_total": len(rows),
        "monitoring_totals": {
            "author_supervision": sum(bool(row["author_supervision"]) for row in rows),
            "build_control": sum(bool(row["build_control"]) for row in rows),
            "rd_uploaded": sum(row["rd_status"] == "Загружена" for row in rows),
            "rd_missing": sum(row["rd_status"] == "Не загружена" for row in rows),
            "rd_unknown": sum(row["rd_status"] == "Нет данных" for row in rows),
        },
        "page": page, "page_count": page_count, "page_size": page_size,
        "total": total, "first": offset + 1 if total else 0,
        "last": min(offset + page_size, total),
    }


def project_monitoring(number, report, source, organizations, people, documents):
    """Связывает подписи людей с организацией; наличие РД подтверждает файл документа."""
    sections = source.get("sections_read", {})
    edo_read = sections.get("organizations", source.get("edo_organization_count") is not None)
    people_read = sections.get("people", source.get("person_count") is not None)
    edo_read = edo_read and not source.get("edo_error")
    people_read = people_read and not source.get("edo_error")
    by_organization = {}
    for person in people:
        # Один человек может повториться в составе организации с несколькими ролями.
        by_organization.setdefault(person.organization_external_id, {})[person.external_id] = person.signed
    roles = []
    seen = set()
    for org in organizations:
        key = (org.source, org.external_id, org.name, org.role)
        if key in seen:
            continue
        seen.add(key)
        signatures = list(by_organization.get(org.external_id, {}).values()) if org.external_id else []
        roles.append({
            "name": org.name or "Организация без названия", "role": org.role,
            "label": ROLE_LABELS.get(org.role, org.role or "Роль не указана"),
            "known": bool(org.external_id) and org.source == "edo" and people_read,
            "total": len(signatures), "signed": sum(value is True for value in signatures),
            "unsigned": sum(value is False for value in signatures),
            "unknown": sum(value is None for value in signatures),
        })
    rd = [item for item in documents if item.kind == "РД"]
    rd_files = sum(bool(item.source_data.get("documentFileId")) for item in rd)
    rd_read = sections.get("pir_documents", False) and not source.get("pir_error")
    # Карточка РД без прикреплённого файла ещё не означает загруженную документацию.
    rd_status = "Загружена" if rd_files else (
        "Не загружена" if rd_read and all("documentFileId" in item.source_data for item in rd) else "Нет данных"
    )
    return {
        "number": number, "name": report.get("Объект") or str(number),
        "customer": report.get("Заказчик"), "organizations": roles,
        "edo_read": bool(edo_read),
        "author_supervision": [org for org in roles if org["role"] == "AUTHOR_SUPERVISION"],
        "build_control": [org for org in roles if org["role"] == "BUILD_CONTROL"],
        "rd_status": rd_status, "rd_count": len(rd), "rd_files": rd_files,
        "gsn_status": {True: "ОЖР зарегистрирован в ГСН", False: "ОЖР не зарегистрирован в ГСН"}.get(registration_state(source), "Нет данных"),
        "gsn_number": (source.get("general_journal_registration") or {}).get("number"),
        "gsn_date": (source.get("general_journal_registration") or {}).get("registration_date"),
    }
