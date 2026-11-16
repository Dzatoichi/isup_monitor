from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.web.organizations.models import ProjectOrganizationSnapshot
from src.web.projects.projects_model import Project

from .models import ProjectParticipantSnapshot


class ParticipantDAO:
    @staticmethod
    async def get_for_project(
        session: AsyncSession, snapshot_id: int, oks_number: int
    ) -> Sequence[ProjectParticipantSnapshot]:
        model = ProjectParticipantSnapshot
        statement = (
            select(model).join(Project, Project.id == model.project_id)
            .where(model.snapshot_id == snapshot_id, Project.oks_number == oks_number)
            .order_by(model.row_number)
        )
        return (await session.scalars(statement)).all()

    @staticmethod
    async def get_organizations(
        session: AsyncSession, snapshot_id: int, oks_number: int
    ) -> dict[str, ProjectOrganizationSnapshot]:
        model = ProjectOrganizationSnapshot
        statement = (
            select(model).join(Project, Project.id == model.project_id)
            .where(model.snapshot_id == snapshot_id, Project.oks_number == oks_number)
            .order_by(model.row_number)
        )
        organizations = {}
        for row in await session.scalars(statement):
            if row.external_id is not None:
                organizations.setdefault(row.external_id, row)
        return organizations
