from pydantic_core import to_jsonable_python
from src.web.pir.models import PirDocumentSnapshot

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert

from src.web.projects.projects_model import Project, ProjectSnapshot
from src.web.snapshots.models import Snapshot
from src.web.participants.models import ProjectParticipantSnapshot
from src.web.organizations.models import ProjectOrganizationSnapshot
from src.web.documents.models import DocumentOperationSnapshot

from .models import ProjectEvent


FIELD_GROUPS = {
    "Характеристики": ("Стадия", "Состояние", "Готовность, %", "Риски"),
    "Сроки": tuple(f"{edge} {stage}, {mode}" for stage in ("ПИР", "СМР")
                    for mode in ("план", "факт") for edge in ("Начало", "Окончание")),
    "Финансы": ("Стоимость по договорам, руб.", "Освоено, руб.", "Остаток, руб."),
    "Ответственные": ("Строительный заместитель", "Руководитель проекта"),
    "Светофор": ("Статус", "Вывод"),
    "ПД и РД": (), "Участники": (), "Организации": (), "Документы": (), "Выгрузки": (),
}


def report_changes(before, after):
    """Находит изменения заполненных показателей. Пропуск нового значения не превращает в подтверждённое изменение."""
    for category, fields in FIELD_GROUPS.items():
        for field in fields:
            old, new = before.get(field), after.get(field)
            # Заполняющиеся значения являются событием, пропуск после ошибки чтения — нет.
            if new is not None and new != old:
                yield category, field, old, new


class EventDAO:
    @staticmethod
    def section_read(source, marker):
        """Определяет, был ли раздел действительно прочитан, чтобы сбой запроса не считался удалением данных."""
        if "sections_read" in source:
            return source["sections_read"].get(marker, False)
        if marker == "pir_documents":
            return False
        if marker == "documents":
            return source.get("operation_dates") is not None and not source.get("documents_error")
        if marker == "people":
            return source.get("person_count") is not None and not source.get("edo_error")
        return (source.get("edo_organization_count") is not None or source.get("participants") is not None) and not source.get("edo_error")

    @staticmethod
    def capture(session, snapshot_id):
        """Добавляет события атомарно с публикацией. Повторная публикация идемпотентна."""
        session.flush()
        current = session.get_one(Snapshot, snapshot_id)
        projects = session.scalars(select(ProjectSnapshot).where(ProjectSnapshot.snapshot_id == snapshot_id)).all()
        for project in projects:
            previous = session.scalar(
                select(ProjectSnapshot)
                .join(Snapshot, Snapshot.id == ProjectSnapshot.snapshot_id)
                .where(ProjectSnapshot.project_id == project.project_id,
                       Snapshot.status.in_(("ready", "partial")),
                       tuple_(Snapshot.exported_on, Snapshot.id) < (current.exported_on, current.id))
                .order_by(Snapshot.exported_on.desc(), Snapshot.id.desc()).limit(1)
            )
            if previous is None:
                continue
            events = list(report_changes(previous.report_data, project.report_data))
            previous_snapshot = session.get_one(Snapshot, previous.snapshot_id)
            gap = (current.exported_on - previous_snapshot.exported_on).days
            if gap > 1:
                events.append(("Выгрузки", "Пропуск наблюдений", None, gap - 1))

            for model, category, marker, key, fields in (
                (PirDocumentSnapshot, "ПД и РД", "pir_documents", ("kind", "external_id"),
                 ("name", "status", "version", "remark_count", "approved_on", "transferred_on", "issued_on")),
                (ProjectParticipantSnapshot, "Участники", "people", ("organization_external_id", "external_id"), ("full_name", "position", "role", "signed")),
                (ProjectOrganizationSnapshot, "Организации", "organizations", ("source", "external_id", "name"), ("name", "role")),
                (DocumentOperationSnapshot, "Документы", "documents", ("external_id", "document_number", "name", "document_on"), ("status", "document_type")),
            ):
                if not EventDAO.section_read(project.source_data, marker):
                    continue
                if not EventDAO.section_read(previous.source_data, marker):
                    continue
                def records(identifier):
                    return session.scalars(select(model).where(
                        model.snapshot_id == identifier, model.project_id == project.project_id
                    )).all()
                old_items = records(previous.snapshot_id)
                new_items = records(snapshot_id)
                effective_key = key
                if model is DocumentOperationSnapshot and not all(
                    item.external_id for item in [*old_items, *new_items]
                ):
                    effective_key = key[1:]

                def values(items):
                    return {str(tuple(str(getattr(item, k)) for k in effective_key)):
                            {name: getattr(item, name) for name in fields} for item in items}
                before, after = values(old_items), values(new_items)
                for identifier in sorted(before.keys() | after.keys()):
                    if before.get(identifier) != after.get(identifier):
                        events.append((category, identifier, before.get(identifier), after.get(identifier)))
            for category, field, before, after in events:
                statement = insert(ProjectEvent).values(
                    snapshot_id=snapshot_id, project_id=project.project_id,
                    observed_on=current.exported_on, category=category, field=field, before=to_jsonable_python(before), after=to_jsonable_python(after),
                )
                session.execute(statement.on_conflict_do_nothing(
                    index_elements=["snapshot_id", "project_id", "category", "field"]
                ))

    @staticmethod
    async def get_history(session, oks_number, snapshot, category, since=None, until=None):
        statement = (
            select(ProjectEvent.snapshot_id, ProjectEvent.observed_on, ProjectEvent.field,
                   ProjectEvent.before, ProjectEvent.after)
            .join(Project, Project.id == ProjectEvent.project_id)
            .join(Snapshot, Snapshot.id == ProjectEvent.snapshot_id)
            .where(Project.oks_number == oks_number, Snapshot.status.in_(("ready", "partial")),
                   tuple_(Snapshot.exported_on, Snapshot.id) <= (snapshot.exported_on, snapshot.id))
            .order_by(ProjectEvent.observed_on.desc(), ProjectEvent.id.desc())
        )
        if since:
            statement = statement.where(ProjectEvent.observed_on >= since)
        if until:
            statement = statement.where(ProjectEvent.observed_on <= until)
        if category:
            statement = statement.where(ProjectEvent.category == category)
        return (await session.execute(statement)).all()
