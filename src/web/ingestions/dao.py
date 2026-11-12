from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.web.snapshots.models import Snapshot

from .models import IngestionRun


class IngestionDAO:
    """Ведёт журнал запусков и меняет статус снимка вместе со статусом запуска."""

    @staticmethod
    async def get_all(session: AsyncSession, *, offset: int, limit: int):
        statement = select(IngestionRun).order_by(IngestionRun.id.desc()).offset(offset).limit(limit)
        return (await session.scalars(statement)).all()

    @staticmethod
    def start_run(session: Session, exported_on: date) -> tuple[int, int]:
        run = IngestionRun(status="running")
        session.add(run)
        session.flush()

        snapshot = Snapshot(run_id=run.id, exported_on=exported_on, status="running")
        session.add(snapshot)
        session.flush()
        return run.id, snapshot.id

    @staticmethod
    def record_project(session: Session, run_id: int, errors: list[dict[str, Any]]) -> None:
        run = session.get_one(IngestionRun, run_id)
        run.processed_count += 1
        if errors:
            run.errors = [*run.errors, *errors]

    @staticmethod
    def finish_run(
        session: Session,
        run_id: int,
        snapshot_id: int,
        status: str,
        errors: list[dict[str, Any]],
    ) -> None:
        run = session.get_one(IngestionRun, run_id)
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.errors = [*run.errors, *errors]
        session.get_one(Snapshot, snapshot_id).status = status
