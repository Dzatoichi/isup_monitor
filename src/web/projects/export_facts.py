"""Готовит проверяемые факты и действия для руководителя и анализа в Алисе."""

from src.web.analytics.monitoring import project_monitoring, ROLE_LABELS
from src.web.regulations.schemas import TrafficRules


CONTROL_ROLES = ("CUSTOMER", "GENERAL_CONTRACTOR", "CONTRACTOR", "GENERAL_DESIGNER",
                 "DESIGNER", "AUTHOR_SUPERVISION", "BUILD_CONTROL")


def document_presence(documents, kind, source):
    items = [doc for doc in documents if doc.kind == kind]
    if any(doc.source_data.get("documentFileId") for doc in items):
        return "Загружена"
    if (source.get("sections_read", {}).get("pir_documents") and not source.get("pir_error")
            and all("documentFileId" in doc.source_data for doc in items)):
        return "Не загружена"
    return "Не удалось проверить"


def role_fact(items, known):
    if not items:
        return ("Не добавлена" if known else "Не удалось проверить", "Не применимо" if known else "Не удалось проверить")
    names = "; ".join(item["name"] for item in items)
    signatures = []
    for item in items:
        if not item["known"]:
            state = "Не удалось проверить"
        elif not item["total"]:
            state = "Команда не заведена"
        else:
            state = f"Подписали {item['signed']} из {item['total']}"
            if item["unknown"]:
                state += f"; неизвестно {item['unknown']}"
        signatures.append(f"{item['name']}: {state}")
    summary = "; ".join(signatures)
    # Длинные перечни остаются в подробных листах, чтобы одна строка сводки не занимала экран.
    if len(names) > 180:
        names = f"Добавлено организаций: {len(items)}. Полный список — лист «Организации по данным ИСУП»"
    if len(summary) > 220:
        known_items = [item for item in items if item["known"]]
        summary = (f"Участников подтверждено: {sum(item['total'] for item in known_items)}; "
                   f"подписали: {sum(item['signed'] for item in known_items)}; "
                   f"без подписи: {sum(item['unsigned'] for item in known_items)}; "
                   f"подпись неизвестна: {sum(item['unknown'] for item in known_items)}; "
                   f"пустых команд: {sum(not item['total'] for item in known_items)}; "
                   f"организаций без данных: {len(items) - len(known_items)}")
    return names, summary


def management_facts(number, report, source, organizations, people, documents, rules):
    """Возвращает факты и замечания; обязательность берётся из версии правил снимка."""
    monitor = project_monitoring(number, report, source, organizations, people, documents)
    rules = TrafficRules.model_validate(rules or {})
    required = set(rules.required_roles_by_stage.get(report.get("Стадия"), []))
    issues = []

    def issue(code, category, level, fact, action, organization=None, participant=None):
        issues.append({"code": code, "category": category, "level": level, "fact": fact,
                       "action": action, "organization": organization, "participant": participant})

    facts = {}
    for role in CONTROL_ROLES:
        items = [item for item in monitor["organizations"] if item["role"] == role]
        facts[role] = role_fact(items, monitor["edo_read"])
        if not items and monitor["edo_read"]:
            issue(f"ROLE_ABSENT:{role}", "Организации", "Подтверждённая проблема" if role in required else "Факт для проверки",
                  f"Роль «{ROLE_LABELS[role]}» отсутствует",
                  "Добавить организацию с обязательной ролью" if role in required else "Уточнить применимость роли к объекту")
        for item in items:
            if item["known"] and not item["total"]:
                issue(f"EMPTY_TEAM:{role}", "Участники", "Подтверждённая проблема",
                      f"У организации с ролью «{item['label']}» нет участников",
                      "Завести команду организации либо уточнить актуальность её участия", item["name"])
    org_names = {}
    for org in organizations:
        if org.external_id:
            org_names.setdefault(org.external_id, org.name)
    seen = set()
    for person in people:
        key = (person.organization_external_id, person.external_id)
        if key in seen:
            continue
        seen.add(key)
        if person.signed is False:
            issue("UNSIGNED_PARTICIPANT", "Подписи", "Подтверждённая проблема",
                  "Участник не подписал приказ", "Обеспечить подписание приказа участником",
                  org_names.get(person.organization_external_id), person.full_name)
        elif person.signed is None:
            issue("SIGNATURE_UNKNOWN", "Качество данных", "Не удалось проверить",
                  "Статус подписи участника неизвестен", "Повторить проверку статуса подписи",
                  org_names.get(person.organization_external_id), person.full_name)
    for kind in ("ПД", "РД"):
        state = document_presence(documents, kind, source)
        facts[kind] = state
        if state == "Не загружена":
            required_document = kind in rules.required_documents_by_stage.get(report.get("Стадия"), [])
            issue(f"NO_FILES:{kind}", "Документация", "Подтверждённая проблема" if required_document else "Факт для проверки",
                  f"Файлы {kind} не загружены", "Загрузить документацию" if required_document else "Уточнить необходимость загрузки документации")
    facts["gsn"] = monitor["gsn_status"]
    if facts["gsn"] == "ОЖР не зарегистрирован в ГСН":
        gsn_required = report.get("Стадия") in rules.gsn_required_stages
        issue("GSN_NOT_REGISTERED", "ОЖР", "Подтверждённая проблема" if gsn_required else "Факт для проверки",
              facts["gsn"], "Зарегистрировать ОЖР в ГСН" if gsn_required else "Уточнить необходимость регистрации ОЖР; при необходимости зарегистрировать")
    overdue = report.get("Просрочка этапа, дн.")
    if overdue and overdue > 0:
        issue("STAGE_OVERDUE", "Сроки", "Подтверждённая проблема", f"Просрочка этапа: {overdue} дн.",
              "Получить у РП причину просрочки и план дальнейших действий")
    for field, title in (("Руководитель проекта", "РП"), ("Строительный заместитель", "заместитель")):
        if not report.get(field):
            issue(f"ASSIGNMENT_MISSING:{title}", "Ответственные", "Факт для проверки",
                  f"Не указан {title}", "Проверить карточку и справочник закреплений")
    for key, value in source.items():
        if key.endswith("_error"):
            issue(f"SOURCE_ERROR:{key}", "Качество данных", "Не удалось проверить", str(value), "Проверить доступ к источнику и повторить сбор")
    itd_acts = source.get("itd_acts")
    if isinstance(itd_acts, list) and source.get("sections_read", {}).get("itd_acts"):
        facts["ИТД"] = "Есть акты" if itd_acts else "Акты не найдены"
        if not itd_acts:
            issue("ITD_EMPTY", "Исполнительная документация", "Факт для проверки",
                  "Запрос ИСУП вернул пустой список актов ИТД",
                  "Сверить наличие исполнительной документации в модуле ЭДО")
    else:
        facts["ИТД"] = "Не удалось проверить"
        issue("ITD_UNAVAILABLE", "Качество данных", "Не удалось проверить",
              str(source.get("itd_error") or "Ответ по ИТД не сохранён в снимке"),
              "Повторить чтение списка актов ИТД")
    for code, fact in (("WORKFLOW_UNAVAILABLE", "История движения документов не подключена"),):
        issue(code, "Качество данных", "Не удалось проверить", fact, "Подключить и проверить сетевой источник")
    if not monitor["edo_read"] and not source.get("edo_error"):
        issue("EDO_UNKNOWN", "Качество данных", "Не удалось проверить", "Состав организаций ЭДО не подтверждён", "Повторить сбор состава ЭДО")
    if facts["ПД"] == "Не удалось проверить" or facts["РД"] == "Не удалось проверить":
        issue("PIR_UNKNOWN", "Качество данных", "Не удалось проверить", "Наличие файлов ПД/РД не подтверждено", "Повторить сбор ПД/РД")
    if facts["gsn"] == "Нет данных":
        issue("GSN_UNKNOWN", "Качество данных", "Не удалось проверить", "Регистрация ОЖР не подтверждена", "Проверить источник статуса ОЖР")
    return facts, issues
