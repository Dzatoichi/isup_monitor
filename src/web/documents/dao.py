from sqlalchemy import select

from src.web.projects.projects_model import Project

from .models import DocumentOperationSnapshot


class DocumentDAO:
    @staticmethod
    async def get_for_project(session, snapshot_id, oks_number):
        statement = (
            select(DocumentOperationSnapshot)
            .join(Project, Project.id == DocumentOperationSnapshot.project_id)
            .where(DocumentOperationSnapshot.snapshot_id == snapshot_id, Project.oks_number == oks_number)
            .order_by(DocumentOperationSnapshot.row_number)
        )
        return (await session.scalars(statement)).all()
