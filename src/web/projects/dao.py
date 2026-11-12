from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .projects_model import Project, ProjectSnapshot
from .schemas import ProjectFilters


class ProjectDAO:
    """Записывает постоянные идентификаторы объектов ИСУП."""

    @staticmethod
    def upsert(session: Session, oks_number: int) -> int:
        statement = insert(Project).values(oks_number=oks_number)
        statement = statement.on_conflict_do_update(
            index_elements=[Project.oks_number],
            set_={"oks_number": statement.excluded.oks_number},
        ).returning(Project.id)
        return session.execute(statement).scalar_one()

    @staticmethod
    async def get_all(session: AsyncSession, snapshot_id: int, filters: ProjectFilters):
        statement = (
            select(Project.oks_number, ProjectSnapshot.report_data)
            .join(ProjectSnapshot, ProjectSnapshot.project_id == Project.id)
            .where(ProjectSnapshot.snapshot_id == snapshot_id)
        )
        for field, value in (
            (ProjectSnapshot.stage, filters.stage),
            (ProjectSnapshot.state, filters.state),
            (ProjectSnapshot.customer, filters.customer),
            (ProjectSnapshot.status, filters.status),
        ):
            if value is not None:
                statement = statement.where(field == value)
        result = await session.execute(
            statement.order_by(Project.oks_number).offset(filters.offset).limit(filters.limit)
        )
        return result.tuples().all()

    @staticmethod
    async def get_by_number(session: AsyncSession, snapshot_id: int, oks_number: int):
        statement = (
            select(ProjectSnapshot.report_data)
            .join(Project, Project.id == ProjectSnapshot.project_id)
            .where(ProjectSnapshot.snapshot_id == snapshot_id, Project.oks_number == oks_number)
        )
        return await session.scalar(statement)
