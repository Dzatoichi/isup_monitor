"""Формирует Excel-выгрузку опубликованных данных снимка."""

from collections import Counter, defaultdict
from io import BytesIO
from textwrap import wrap

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select, tuple_

from src.web.assignments.expressions import current_project_report
from src.web.assignments.models import Assignment
from src.parser.report import REPORT_FIELDS, parse_date
from src.web.pir.models import PirDocumentSnapshot
from src.web.documents.models import DocumentOperationSnapshot
from src.web.organizations.models import ProjectOrganizationSnapshot
from src.web.participants.models import ProjectParticipantSnapshot

from .projects_model import Project, ProjectSnapshot
from .export_facts import management_facts, CONTROL_ROLES
from src.web.analytics.monitoring import ROLE_LABELS
from src.web.snapshots.models import Snapshot
from src.web.ingestions.models import IngestionRun
from src.web.events.models import ProjectEvent
from src.web.regulations.models import Regulation
from src.web.views import event_value
from src.parser.report import REPORT_TIMEZONE


HEADERS = {
    "Сводка объектов": (
        "Номер в ИСУП", "Объект", "Стадия", "Состояние", "Архивный", "Заказчик",
        "Руководитель проекта", "Строительный заместитель",
        *(column for role in CONTROL_ROLES for column in (ROLE_LABELS[role], f"Команда и подписи: {ROLE_LABELS[role]}")),
        "ПД загружена", "РД загружена", "ИД загружена", "ОЖР в ГСН", "Номер регистрации ОЖР", "Дата регистрации ОЖР",
        "Просрочка этапа, дн.", "Последняя дата документа", "Дней с даты документа",
        "Подтверждённых проблем", "Фактов для проверки", "Проверок без данных", "Проблемы и действия",
    ),
    "Проблемы": (
        "Номер в ИСУП", "Объект", "Код проверки", "Категория", "Оценка",
        "Подтверждающий факт", "Требуемое действие", "Организация", "Участник",
        "Руководитель проекта", "Строительный заместитель", "Источник",
    ),
    "Описание выгрузки": ("Параметр", "Значение"),
    "Изменения объектов": (
        "Номер в ИСУП", "Объект", "Снимок события", "Дата обнаружения", "Категория", "Показатель", "Было", "Стало",
    ),
    "Объекты": REPORT_FIELDS,
    "Полнота данных": ("Номер в ИСУП", "Объект", "Замечание"),
    "Участники и подписи": (
        "Номер в ИСУП", "Объект", "Организация", "ID организации", "Роль организации", "ID участника", "ФИО", "Должность", "Роль участника", "Подпись",
    ),
    "Операции обмена": (
        "Номер в ИСУП", "Объект", "Дата документа", "Номер документа", "Название", "Тип документа", "Статус", "Автор", "Раздел",
    ),
    "Документы ПД и РД": (
        "Номер в ИСУП", "Объект", "ID документа", "Файл загружен", "Вид", "Шифр", "Название", "Раздел", "Версия", "Статус",
        "Дата создания", "Дата согласования", "План согласования", "Передано заказчику",
        "Выдано в работу", "Замечаний", "Просрочка, дн.",
    ),
    "Исполнительная документация": (
        "Номер в ИСУП", "Объект", "ID акта", "Номер акта", "Дата акта", "Вид акта", "Название",
        "Описание работ", "Раздел проекта", "Статус", "Текущий исполнитель", "Дата отправки",
        "Версия", "Замечаний", "Файл PDF есть", "Файл XML есть",
    ),
    "Обмен по месяцам": ("Номер в ИСУП", "Объект", "Месяц по дате документа", "Операций"),
    "Организации по данным ИСУП": ("Номер в ИСУП", "Объект", "Организация", "ID организации", "Роль", "ИНН", "КПП", "ОГРН", "Источник"),
}
DATE_COLUMNS = frozenset({
    "Дата регистрации ОЖР", "Последняя операция", "Последняя дата документа", "Дата обнаружения", "Дата выгрузки", "Дата документа", "Дата создания", "Дата согласования", "Дата акта", "Дата отправки",
    "План согласования", "Передано заказчику", "Выдано в работу",
    *(field for field in REPORT_FIELDS if field.startswith(("Начало ", "Окончание "))),
})


async def load_export_rows(session, snapshot_id, scope, *, show_contacts):
    # Все дочерние записи выбираются только для объектов, доступных пользователю.
    """Выбирает данные снимка только по доступным объектам. Контакты добавляются по правам пользователя."""
    query = (select(Project.id, Project.oks_number, current_project_report(), ProjectSnapshot.source_data)
             .join(ProjectSnapshot, ProjectSnapshot.project_id == Project.id)
             .outerjoin(Assignment, Assignment.oks_number == Project.oks_number)
             .where(ProjectSnapshot.snapshot_id == snapshot_id).order_by(Project.oks_number))
    if scope is not None:
        query = query.where(Project.oks_number.in_(scope))
    projects = (await session.execute(query)).all()
    rows = {name: [] for name in HEADERS}
    snapshot = await session.get(Snapshot, snapshot_id)
    run = await session.get(IngestionRun, snapshot.run_id)
    regulation = await session.get(Regulation, snapshot.regulation_id) if snapshot.regulation_id else None
    rule_values = regulation.rules if regulation else {}
    labels = {}
    for project_id, number, report, source in projects:
        labels[project_id] = (number, report.get("Объект"))
        rows["Объекты"].append(tuple(report.get(field) for field in REPORT_FIELDS))
        for key, value in source.items():
            if key.endswith("_error"):
                rows["Полнота данных"].append((number, report.get("Объект"), str(value)))
        if source.get("operation_dates") is not None:
            rows["Полнота данных"].append((
                number, report.get("Объект"), "Дата поступления не подтверждена; используется дата документа",
            ))

    async def related(model):
        if not labels:
            return []
        statement = select(model).where(
            model.snapshot_id == snapshot_id, model.project_id.in_(labels),
        ).order_by(model.project_id, model.row_number)
        return (await session.scalars(statement)).all()

    organization_rows = await related(ProjectOrganizationSnapshot)
    people_rows = await related(ProjectParticipantSnapshot)
    document_rows = await related(PirDocumentSnapshot)
    organizations = {}
    organization_roles = defaultdict(list)
    groups = [defaultdict(list) for _ in range(3)]
    for group, records in zip(groups, (organization_rows, people_rows, document_rows)):
        for item in records:
            group[item.project_id].append(item)
    for org in organization_rows:
        if org.external_id:
            key = (org.project_id, org.external_id)
            organizations.setdefault(key, org.name)
            label = ROLE_LABELS.get(org.role, org.role or "Роль не указана")
            if label not in organization_roles[key]:
                organization_roles[key].append(label)
        rows["Организации по данным ИСУП"].append((
            *labels[org.project_id], org.name, org.external_id, ROLE_LABELS.get(org.role, org.role),
            org.inn, org.kpp, org.ogrn, org.source,
        ))
    for person in people_rows:
        signed = "Не удалось проверить" if person.signed is None else "Подписан" if person.signed else "Без подписи"
        key = (person.project_id, person.organization_external_id)
        row = (
            *labels[person.project_id], organizations.get(key), person.organization_external_id,
            "; ".join(organization_roles[key]) or "Роль не указана", person.external_id,
            person.full_name, person.position, person.role, signed,
        )
        rows["Участники и подписи"].append(row + (person.email, person.phone) if show_contacts else row)
    for doc in document_rows:
        file_state = "Да" if doc.source_data.get("documentFileId") else "Нет" if "documentFileId" in doc.source_data else "Не удалось проверить"
        rows["Документы ПД и РД"].append((
            *labels[doc.project_id], doc.external_id, file_state, doc.kind, doc.cipher, doc.name, doc.section, doc.version, doc.status,
            doc.created_on, doc.approved_on, doc.expected_approval_on, doc.transferred_on, doc.issued_on,
            doc.remark_count, doc.delay_days,
        ))
    for project_id, number, report, source in projects:
        facts, issues = management_facts(number, report, source, *(group[project_id] for group in groups), rule_values)
        counts = Counter(item["level"] for item in issues)
        archive = source.get("archived")
        rows["Сводка объектов"].append((
            number, report.get("Объект"), report.get("Стадия"), report.get("Состояние"),
            "Да" if archive is True else "Нет" if archive is False else "Не удалось проверить",
            report.get("Заказчик"), report.get("Руководитель проекта"), report.get("Строительный заместитель"),
            *(value for role in CONTROL_ROLES for value in facts[role]),
            facts["ПД"], facts["РД"], facts["ИТД"], facts["gsn"], (source.get("general_journal_registration") or {}).get("number"), (source.get("general_journal_registration") or {}).get("registration_date"),
            report.get("Просрочка этапа, дн."), report.get("Последняя операция"), report.get("Дней без обмена"),
            counts["Подтверждённая проблема"], counts["Факт для проверки"], counts["Не удалось проверить"],
            "\n".join([*(f"{item['level']}: {item['fact']}" for item in issues[:3]), "Подробности и действия — на листе «Проблемы»"]),
        ))
        for item in issues:
            rows["Проблемы"].append((number, report.get("Объект"), item["code"], item["category"], item["level"],
                item["fact"], item["action"], item["organization"], item["participant"],
                report.get("Руководитель проекта"), report.get("Строительный заместитель"),
                "Сохранённый снимок ИСУП / ЭДО; правило: " + (regulation.version if regulation else "не задано")))
        itd_acts = source.get("itd_acts")
        if isinstance(itd_acts, list):
            for act in itd_acts:
                rows["Исполнительная документация"].append((
                    number, report.get("Объект"), act.get("id"), act.get("actNum"), act.get("actDate"),
                    act.get("docType"), act.get("actName"), act.get("description"), act.get("sectionName"),
                    act.get("documentStatus"), act.get("currentExecutor"), act.get("sendDate"),
                    act.get("version"), act.get("commentsCount"), bool(act.get("pdfFileId")),
                    bool((act.get("xmlInfo") or {}).get("xmlFileId")) if isinstance(act.get("xmlInfo"), dict) else False,
                ))
    # История относится только к доступным объектам и не выходит за выбранный снимок.
    if labels:
        statement = (select(ProjectEvent, Snapshot.exported_on)
                     .join(Snapshot, Snapshot.id == ProjectEvent.snapshot_id)
                     .where(ProjectEvent.project_id.in_(labels), Snapshot.status.in_(("ready", "partial")),
                            tuple_(Snapshot.exported_on, Snapshot.id) <= (snapshot.exported_on, snapshot.id))
                     .order_by(Snapshot.exported_on, Snapshot.id, ProjectEvent.id))
        for event, _ in (await session.execute(statement)).all():
            rows["Изменения объектов"].append((*labels[event.project_id], event.snapshot_id, event.observed_on,
                                              event.category, event.field, event_value(event.before), event_value(event.after)))
    rows["Описание выгрузки"] = [
        ("Номер снимка", snapshot.id), ("Дата среза", snapshot.exported_on.isoformat()),
        ("Начало сбора", run.started_at.astimezone(REPORT_TIMEZONE).isoformat()),
        ("Окончание сбора", run.finished_at.astimezone(REPORT_TIMEZONE).isoformat() if run.finished_at else "Не завершено"),
        ("Часовой пояс", "Asia/Krasnoyarsk"), ("Статус снимка", snapshot.status),
        ("Рабочих объектов подтверждено", sum(source.get("archived") is False for _, _, _, source in projects)),
        ("Архивных объектов подтверждено", sum(source.get("archived") is True for _, _, _, source in projects)),
        ("Архивность неизвестна", sum(type(source.get("archived")) is not bool for _, _, _, source in projects)),
        ("Режимы реестра", ", ".join(sorted({source.get("registry_mode") or "Не указан в старом снимке" for _, _, _, source in projects}))),
        ("Объектов в файле", len(projects)), ("Объектов обработано в запуске", run.processed_count),
        ("Область доступа", "Все доступные" if scope is None else "Ограничена правами или выборкой; файл не представляет весь реестр"),
        ("Данные", "Сохранённые факты ИСУП и ЭДО; ФИО могут дополняться текущими закреплениями в последнем снимке"),
        ("Обязательные роли по стадиям", str(rule_values.get("required_roles_by_stage", {}))),
        ("Обязательные документы по стадиям", str(rule_values.get("required_documents_by_stage", {}))),
        ("Обязательная регистрация ОЖР", ", ".join(rule_values.get("gsn_required_stages", [])) or "Не согласована"),
        ("Подпись", "Статус подписания приказа участника, не независимая проверка КЭП"),
        ("ПД / РД загружена", "Есть хотя бы один документ с documentFileId. Это не проверка комплектности документации"),
        ("ОЖР", "buildingInfo: signed=true, номер и дата подтверждают регистрацию; signed=false без реквизитов — не зарегистрирован. target-solution не используется"),
        ("Нет данных", "Не удалось проверить. Не означает отсутствие организации, документа или регистрации"),
        ("Факт для проверки", "Факт подтверждён, но обязательность требования для объекта не установлена"),
        ("Операции обмена", "Документы по дате документа. Их количество не равно числу транзакций или движений"),
        ("Исполнительная документация", "Список актов ИТД читается из /api/itd-service/act/sets; пустой список означает только, что endpoint не вернул актов"),
        ("Движение документов", "Источник переходов и текущего исполнителя не подключён; не назначать виновного"),
        ("История", "Дата обнаружения изменения в снимке, а не точное время события в ИСУП; пропуски чтения не подтверждают удаление"),
        ("Инструкция Алисе", "Используй только факты файла. Разделяй проблемы, факты для проверки и неизвестные данные. Указывай объект, дату среза, организацию и подтверждающую строку. Не придумывай причины задержки, исполнителей и сроки. Письма готовь как проекты для проверки человеком."),
    ]
    monthly = Counter()
    for doc in await related(DocumentOperationSnapshot):
        rows["Операции обмена"].append((
            *labels[doc.project_id], doc.document_on, doc.document_number, doc.name, doc.document_type, doc.status, doc.author, doc.section,
        ))
        if doc.document_on:
            monthly[doc.project_id, doc.document_on.strftime("%Y-%m")] += 1
    for (project_id, month), count in sorted(monthly.items(), key=lambda item: (labels[item[0][0]][0], item[0][1])):
        rows["Обмен по месяцам"].append((*labels[project_id], month, count))
    # Метаданные повторены в строках: их смысл сохраняется при разделении книги на листы.
    for name in rows:
        if name != "Описание выгрузки":
            rows[name] = [(*values, snapshot.id, snapshot.exported_on) for values in rows[name]]
    return rows


def build_workbook(rows, *, show_contacts):
    """Создаёт листы XLSX, форматирует даты и подсвечивает пустые значения. Текст источника сохраняется как текст ячейки."""
    workbook = Workbook()
    workbook.remove(workbook.active) # type: ignore
    missing = PatternFill("solid", fgColor="FFF0CC")
    heading = PatternFill("solid", fgColor="142641")
    for name, columns in HEADERS.items():
        if name == "Участники и подписи" and show_contacts:
            columns += ("Email", "Телефон")
        if name != "Описание выгрузки":
            columns += ("Номер снимка", "Дата выгрузки")
        sheet = workbook.create_sheet(name)
        sheet.append(columns)
        for cell in sheet[1]:
            cell.fill = heading
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            width = 54 if cell.value == "Объект" else min(42, max(23, len(cell.value) + 3))
            sheet.column_dimensions[get_column_letter(cell.column)].width = width
        sheet.row_dimensions[1].height = 62
        for row_number, values in enumerate(rows.get(name, []), start=2):
            for index, (column, value) in enumerate(zip(columns, values, strict=True), start=1):
                if isinstance(value, list):
                    value = ", ".join(map(str, value))
                if column in DATE_COLUMNS and isinstance(value, str):
                    value = parse_date(value) or value
                cell = sheet.cell(row_number, index, value)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                if isinstance(value, str):
                    # Текст ИСУП должен оставаться текстом, даже если начинается со знака равенства.
                    cell.data_type = "s"
                if value is None or isinstance(value, str) and not value.strip():
                    cell.fill = missing
                elif column in DATE_COLUMNS and not isinstance(value, str):
                    cell.number_format = "dd.mm.yyyy"
        if name in {"Сводка объектов", "Проблемы"}:
            sheet.freeze_panes = "C2"
        else:
            sheet.freeze_panes = "A2"
        for key in ("Подтверждающий факт", "Требуемое действие", "Проблемы и действия", "Значение"):
            if key in columns:
                sheet.column_dimensions[get_column_letter(columns.index(key) + 1)].width = 65
        for label, width in (("Состояние", 36), ("Заказчик", 45), ("Организация", 45),
                             ("Код проверки", 44), ("ID документа", 30), ("ID участника", 38)):
            if label in columns:
                sheet.column_dimensions[get_column_letter(columns.index(label) + 1)].width = width
        # Excel не подбирает высоту строк при серверном сохранении: рассчитываем её по переносу.
        for cells in sheet.iter_rows(min_row=2):
            line_count = 1
            for cell in cells:
                if cell.value is None:
                    continue
                width = max(8, int(sheet.column_dimensions[cell.column_letter].width * .9))
                lines = sum(max(1, len(wrap(part, width=width))) for part in str(cell.value).split("\n"))
                line_count = max(line_count, lines)
            sheet.row_dimensions[cells[0].row].height = min(409, max(22, 16 * line_count + 5))
        sheet.sheet_view.zoomScale = 85
        sheet.print_options.horizontalCentered = False
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.print_title_rows = "1:1"
        # Отдельная колонка оценки остаётся читаемой без цвета и при анализе нейросетью.
        if name == "Проблемы":
            assessment = columns.index("Оценка") + 1
            colors = {"Подтверждённая проблема": "FCE4D6", "Факт для проверки": "FFF2CC", "Не удалось проверить": "E7E6E6"}
            for row in sheet.iter_rows(min_row=2):
                row[assessment - 1].fill = PatternFill("solid", fgColor=colors.get(row[assessment - 1].value, "FFFFFF"))
        sheet.auto_filter.ref = sheet.dimensions

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
