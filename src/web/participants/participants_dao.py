from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.web.organizations.models import ProjectOrganizationSnapshot
from src.web.projects.projects_model import Project, ProjectSnapshot

from .models import ProjectParticipantSnapshot


class ParticipantDAO:
    @staticmethod
    async def get_register(session, snapshot_id, scope, organization, role, signature):
        person = ProjectParticipantSnapshot
        org = ProjectOrganizationSnapshot
        # Берём первое название организации из снимка, даже если она сохранена в нескольких ролях.
        org_name = (
            select(org.name).where(
                org.snapshot_id == person.snapshot_id, org.project_id == person.project_id,
                org.external_id == person.organization_external_id,
            ).order_by(org.row_number).limit(1).scalar_subquery()
        )
        statement = (
            select(Project.oks_number, ProjectSnapshot.name, person.organization_external_id, org_name, person)
            .select_from(person)
            .join(Project, Project.id == person.project_id)
            .join(ProjectSnapshot, (ProjectSnapshot.project_id == person.project_id)
                  & (ProjectSnapshot.snapshot_id == person.snapshot_id))
            .where(person.snapshot_id == snapshot_id)
            .order_by(Project.oks_number, person.row_number)
        )
        if scope is not None:
            statement = statement.where(Project.oks_number.in_(scope))
        if organization.strip():
            statement = statement.where(org_name.icontains(organization.strip(), autoescape=True))
        if role.strip():
            statement = statement.where(person.role.icontains(role.strip(), autoescape=True))
        if signature != "all":
            statement = statement.where(person.signed.is_({"signed": True, "unsigned": False, "unknown": None}[signature]))
        return (await session.execute(statement)).all()

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
