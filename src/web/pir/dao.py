from sqlalchemy import select
from src.web.projects.projects_model import Project
from .models import PirDocumentSnapshot


class PirDocumentDAO:
    @staticmethod
    async def get_for_project(session, snapshot_id, oks_number):
        statement = (
            select(PirDocumentSnapshot)
            .join(Project, Project.id == PirDocumentSnapshot.project_id)
            .where(PirDocumentSnapshot.snapshot_id == snapshot_id, Project.oks_number == oks_number)
            .order_by(PirDocumentSnapshot.kind, PirDocumentSnapshot.row_number)
        )
        return (await session.scalars(statement)).all()
