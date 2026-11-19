from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from src.web.assignments.expressions import current_project_report
from src.web.assignments.models import Assignment
from src.web.snapshots.models import Snapshot

from .projects_model import Project, ProjectSnapshot
from .schemas import ProjectFilters


class ProjectDAO:
    """Записывает постоянные идентификаторы объектов ИСУП."""

    @staticmethod
    async def get_history(session, oks_number, snapshot):
        """Читает сохранённые показатели объекта до выбранного снимка для построения графиков."""
        statement = (
            select(Snapshot.id, Snapshot.exported_on, ProjectSnapshot.report_data)
            .join(ProjectSnapshot, ProjectSnapshot.snapshot_id == Snapshot.id)
            .join(Project, Project.id == ProjectSnapshot.project_id)
            .where(
                Project.oks_number == oks_number,
                Snapshot.status.in_(("ready", "partial")),
                tuple_(Snapshot.exported_on, Snapshot.id) <= (snapshot.exported_on, snapshot.id),
            )
            .order_by(Snapshot.exported_on, Snapshot.id)
        )
        return (await session.execute(statement)).all()

    @staticmethod
    def upsert(session: Session, oks_number: int) -> int:
        statement = insert(Project).values(oks_number=oks_number)
        statement = statement.on_conflict_do_update(
            index_elements=[Project.oks_number],
            set_={"oks_number": statement.excluded.oks_number},
        ).returning(Project.id)
        return session.execute(statement).scalar_one()

    @staticmethod
    async def get_all(session: AsyncSession, snapshot_id: int, filters: ProjectFilters, scope: set[int] | None = None):
        """Применяет доступ, фильтры, сортировку и пагинацию в БД. Общий счётчик вычисляется до ограничения страницы."""
        report = current_project_report()
        statement = (
            select(Project.oks_number, report)
            .join(ProjectSnapshot, ProjectSnapshot.project_id == Project.id)
            .outerjoin(Assignment, Assignment.oks_number == Project.oks_number)
            .where(ProjectSnapshot.snapshot_id == snapshot_id)
        )
        if scope is not None:
            statement = statement.where(Project.oks_number.in_(scope))
        if filters.name and filters.name.strip():
            statement = statement.where(ProjectSnapshot.name.icontains(filters.name.strip(), autoescape=True))
        for field, value in (
            (ProjectSnapshot.stage, filters.stage),
            (ProjectSnapshot.state, filters.state),
            (ProjectSnapshot.customer, filters.customer),
            (ProjectSnapshot.status, filters.status),
        ):
            if value is not None:
                statement = statement.where(field == value)
        for label, value in (("Руководитель проекта", filters.manager), ("Строительный заместитель", filters.deputy)):
            if value and value.strip():
                statement = statement.where(report[label].astext.icontains(value.strip(), autoescape=True))
        if filters.no_exchange is not None:
            condition = ProjectSnapshot.operations_last_7_days == 0
            statement = statement.where(condition if filters.no_exchange else ProjectSnapshot.operations_last_7_days > 0)
        if filters.overdue is not None:
            statement = statement.where(ProjectSnapshot.overdue_days > 0 if filters.overdue else ProjectSnapshot.overdue_days == 0)
        sort_column = {
            "number": Project.oks_number, "progress": ProjectSnapshot.progress,
            "last_operation": ProjectSnapshot.last_operation_on, "inactive_days": ProjectSnapshot.days_without_exchange,
            "cost": ProjectSnapshot.contract_cost, "pir_end": ProjectSnapshot.pir_plan_end,
            "smr_end": ProjectSnapshot.smr_plan_end,
        }[filters.sort]
        ordering = []
        if filters.group != "none":
            label = "Руководитель проекта" if filters.group == "manager" else "Строительный заместитель"
            ordering.append(report[label].astext.asc().nulls_last())
        ordering.extend(((sort_column.desc() if filters.descending else sort_column.asc()).nulls_last(), Project.oks_number))
        # Считаем все доступные строки до применения пагинации.
        total = await session.scalar(select(func.count()).select_from(statement.subquery()))
        result = await session.execute(
            statement.order_by(*ordering).offset(filters.offset).limit(filters.limit)
        )
        return result.tuples().all(), total

    @staticmethod
    async def get_by_number(session: AsyncSession, snapshot_id: int, oks_number: int):
        """Читает отчёт одного объекта с учётом текущего справочника закреплений для последнего снимка."""
        statement = (
            select(current_project_report())
            .join(Project, Project.id == ProjectSnapshot.project_id)
            .outerjoin(Assignment, Assignment.oks_number == Project.oks_number)
            .where(ProjectSnapshot.snapshot_id == snapshot_id, Project.oks_number == oks_number)
        )
        return await session.scalar(statement)
