"""Формирует Excel-выгрузку опубликованных данных снимка."""

from collections import Counter
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select

from src.web.assignments.expressions import current_project_report
from src.web.assignments.models import Assignment
from src.parser.report import REPORT_FIELDS, parse_date
from src.web.pir.models import PirDocumentSnapshot
from src.web.documents.models import DocumentOperationSnapshot
from src.web.organizations.models import ProjectOrganizationSnapshot
from src.web.participants.models import ProjectParticipantSnapshot

from .projects_model import Project, ProjectSnapshot


HEADERS = {
    "Объекты": REPORT_FIELDS,
    "Полнота данных": ("Номер в ИСУП", "Объект", "Замечание"),
    "Участники и подписи": (
        "Номер в ИСУП", "Объект", "Организация", "ФИО", "Должность", "Роль", "Подпись",
    ),
    "Операции обмена": (
        "Номер в ИСУП", "Объект", "Дата документа", "Номер документа", "Название", "Тип документа", "Статус", "Автор", "Раздел",
    ),
    "Документы ПД и РД": (
        "Номер в ИСУП", "Объект", "Вид", "Шифр", "Название", "Раздел", "Версия", "Статус",
        "Дата создания", "Дата согласования", "План согласования", "Передано заказчику",
        "Выдано в работу", "Замечаний", "Просрочка, дн.",
    ),
    "Обмен по месяцам": ("Номер в ИСУП", "Объект", "Месяц по дате документа", "Операций"),
    "Организации по данным ИСУП": ("Номер в ИСУП", "Объект", "Организация", "Роль", "ИНН", "КПП", "ОГРН", "Источник"),
}
DATE_COLUMNS = frozenset({
    "Последняя операция", "Дата документа", "Дата создания", "Дата согласования",
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

    organizations = {}
    for org in await related(ProjectOrganizationSnapshot):
        if org.external_id:
            organizations.setdefault((org.project_id, org.external_id), org.name)
        rows["Организации по данным ИСУП"].append((
            *labels[org.project_id], org.name, org.role, org.inn, org.kpp, org.ogrn, org.source,
        ))
    for person in await related(ProjectParticipantSnapshot):
        signed = None if person.signed is None else "Подписан" if person.signed else "Без подписи"
        row = (
            *labels[person.project_id], organizations.get((person.project_id, person.organization_external_id)),
            person.full_name, person.position, person.role, signed,
        )
        rows["Участники и подписи"].append(row + (person.email, person.phone) if show_contacts else row)

    for doc in await related(PirDocumentSnapshot):
        rows["Документы ПД и РД"].append((
            *labels[doc.project_id], doc.kind, doc.cipher, doc.name, doc.section, doc.version, doc.status,
            doc.created_on, doc.approved_on, doc.expected_approval_on, doc.transferred_on, doc.issued_on,
            doc.remark_count, doc.delay_days,
        ))
    monthly = Counter()
    for doc in await related(DocumentOperationSnapshot):
        rows["Операции обмена"].append((
            *labels[doc.project_id], doc.document_on, doc.document_number, doc.name, doc.document_type, doc.status, doc.author, doc.section,
        ))
        if doc.document_on:
            monthly[doc.project_id, doc.document_on.strftime("%Y-%m")] += 1
    for (project_id, month), count in sorted(monthly.items(), key=lambda item: (labels[item[0][0]][0], item[0][1])):
        rows["Обмен по месяцам"].append((*labels[project_id], month, count))
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
        sheet = workbook.create_sheet(name)
        sheet.append(columns)
        for cell in sheet[1]:
            cell.fill = heading
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            width = 54 if cell.value == "Объект" else min(36, max(15, len(cell.value) + 3))
            sheet.column_dimensions[get_column_letter(cell.column)].width = width
        sheet.row_dimensions[1].height = 32
        for row_number, values in enumerate(rows[name], start=2):
            for index, (column, value) in enumerate(zip(columns, values, strict=True), start=1):
                if isinstance(value, list):
                    value = ", ".join(map(str, value))
                if column in DATE_COLUMNS and isinstance(value, str):
                    value = parse_date(value) or value
                cell = sheet.cell(row_number, index, value)
                if isinstance(value, str):
                    # Текст ИСУП должен оставаться текстом, даже если начинается со знака равенства.
                    cell.data_type = "s"
                if value is None or isinstance(value, str) and not value.strip():
                    cell.fill = missing
                elif column in DATE_COLUMNS and not isinstance(value, str):
                    cell.number_format = "dd.mm.yyyy"
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
