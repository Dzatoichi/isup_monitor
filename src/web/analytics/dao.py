from sqlalchemy import select, tuple_

from src.web.assignments.expressions import current_project_report
from src.web.assignments.models import Assignment
from src.web.projects.projects_model import Project, ProjectSnapshot
from src.web.snapshots.models import Snapshot


class AnalyticsDAO:
    @staticmethod
    async def get_reports(session, snapshot_ids, scope):
        """Получает показатели только по объектам, доступным пользователю."""
        statement = (
            select(ProjectSnapshot.snapshot_id, Project.oks_number, current_project_report())
            .join(Project, Project.id == ProjectSnapshot.project_id)
            .outerjoin(Assignment, Assignment.oks_number == Project.oks_number)
            .where(ProjectSnapshot.snapshot_id.in_(snapshot_ids))
            .order_by(Project.oks_number)
        )
        if scope is not None:
            statement = statement.where(Project.oks_number.in_(scope))
        return (await session.execute(statement)).all()

    @staticmethod
    async def get_source_issues(session, snapshot_id, scope):
        statement = (
            select(Project.oks_number, ProjectSnapshot.source_data)
            .join(ProjectSnapshot, ProjectSnapshot.project_id == Project.id)
            .where(ProjectSnapshot.snapshot_id == snapshot_id)
        )
        if scope is not None:
            statement = statement.where(Project.oks_number.in_(scope))
        return (await session.execute(statement)).all()

    @staticmethod
    async def get_snapshots(session, snapshot, since=None):
        statement = (
            select(Snapshot)
            .where(
                Snapshot.status.in_(("ready", "partial")),
                tuple_(Snapshot.exported_on, Snapshot.id) <= (snapshot.exported_on, snapshot.id),
            )
            .order_by(Snapshot.exported_on, Snapshot.id)
        )
        if since is not None:
            statement = statement.where(Snapshot.exported_on >= since)
        return (await session.scalars(statement)).all()

    @staticmethod
    async def get_latest_status_changes(session, numbers, snapshot):
        statement = (
            select(Project.oks_number, Snapshot.exported_on, ProjectSnapshot.status)
            .join(ProjectSnapshot, ProjectSnapshot.project_id == Project.id)
            .join(Snapshot, Snapshot.id == ProjectSnapshot.snapshot_id)
            .where(
                Project.oks_number.in_(numbers),
                Snapshot.status.in_(("ready", "partial")),
                tuple_(Snapshot.exported_on, Snapshot.id) <= (snapshot.exported_on, snapshot.id),
            )
            .order_by(Snapshot.exported_on, Snapshot.id)
        )
        return (await session.execute(statement)).all()
