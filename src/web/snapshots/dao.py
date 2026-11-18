from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.web.projects.projects_model import ProjectSnapshot
from src.web.projects.snapshot_fields import project_snapshot_values

from .models import Snapshot


class SnapshotDAO:
    """Записывает объекты снимка и находит опубликованный снимок."""

    @staticmethod
    def progress_stalled(session, project_id, exported_on, progress, days=56):
        """Проверяет рост по ежедневным наблюдениям за последние восемь недель."""
        if type(progress) is not int or not 0 <= progress <= 100:
            return None
        start = exported_on - timedelta(days=days)
        rows = session.execute(
            select(Snapshot.exported_on, ProjectSnapshot.progress)
            .join(ProjectSnapshot, ProjectSnapshot.snapshot_id == Snapshot.id)
            .where(
                ProjectSnapshot.project_id == project_id,
                Snapshot.status.in_(("ready", "partial")),
                Snapshot.exported_on >= start,
                Snapshot.exported_on <= exported_on,
                ProjectSnapshot.progress.is_not(None),
            ).order_by(Snapshot.exported_on, Snapshot.id)
        ).all()
        daily = dict(rows)
        daily[exported_on] = progress
        values = [value for _, value in sorted(daily.items())]
        if any(after > before for before, after in zip(values, values[1:])):
            return False
        if len(daily) < days + 1 or start not in daily:
            return None
        return True

    @staticmethod
    async def get_by_id(session: AsyncSession, snapshot_id: int) -> Snapshot | None:
        return await session.get(Snapshot, snapshot_id)

    @staticmethod
    def upsert_project(
        session: Session,
        snapshot_id: int,
        project_id: int,
        exported_on: date,
        source: dict[str, Any],
        report: dict[str, Any],
    ) -> None:
        values = {
            "exported_on": exported_on,
            "source_data": source,
            "report_data": report,
            **project_snapshot_values(report),
        }
        statement = insert(ProjectSnapshot).values(
            snapshot_id=snapshot_id,
            project_id=project_id,
            **values,
        )
        session.execute(statement.on_conflict_do_update(
            index_elements=[ProjectSnapshot.snapshot_id, ProjectSnapshot.project_id],
            set_={column: statement.excluded[column] for column in values},
        ))

    @staticmethod
    def get_latest_available(session: Session) -> Snapshot | None:
        statement = (
            select(Snapshot)
            .where(Snapshot.status.in_(("ready", "partial")))
            .order_by(Snapshot.exported_on.desc(), Snapshot.id.desc())
            .limit(1)
        )
        return session.scalar(statement)
