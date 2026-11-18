from datetime import timedelta
from collections import Counter

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.web.events.dao import EventDAO, FIELD_GROUPS
from src.web.snapshots.schemas import SnapshotRead
from src.web.snapshots.service import SnapshotService

from .dao import ProjectDAO
from .schemas import ProjectFilters, ProjectList, ProjectRead


class ProjectService:
    HISTORY_FIELDS = FIELD_GROUPS

    @staticmethod
    async def get_history(session, oks_number, snapshot, category, since=None, until=None):
        rows = await EventDAO.get_history(session, oks_number, snapshot, category, since, until)
        events = []
        for identifier, day, field, before, after in rows:
            sample = after if isinstance(after, dict) else before
            if isinstance(sample, dict):
                field = sample.get("full_name") or sample.get("name") or "Изменение записи"
            events.append((identifier, day, field, before, after))
        return events

    @staticmethod
    async def get_charts(session, oks_number, snapshot, documents):
        from src.web.analytics.service import week_start
        history = await ProjectDAO.get_history(session, oks_number, snapshot)
        points = {}
        for _, day, report in history:
            points[week_start(day)] = report.get("Готовность, %")
        counts = Counter(week_start(item.document_on) for item in documents if item.document_on)
        start = week_start(snapshot.exported_on) - timedelta(weeks=7)
        return [(start + timedelta(weeks=i), points.get(start + timedelta(weeks=i)),
                 counts[start + timedelta(weeks=i)]) for i in range(8)]

    @staticmethod
    async def get_all(session: AsyncSession, filters: ProjectFilters, *, scope: set[int] | None = None) -> ProjectList:
        snapshot = await SnapshotService.resolve(session, filters.snapshot_id)
        rows, total = await ProjectDAO.get_all(session, snapshot.id, filters, scope)
        return ProjectList(
            snapshot=SnapshotRead.model_validate(snapshot),
            items=[ProjectRead.from_report(report) for _, report in rows],
            offset=filters.offset,
            limit=filters.limit,
            total=total, # type: ignore
        )

    @staticmethod
    async def get_by_number(
        session: AsyncSession, oks_number: int, snapshot_id: int | None = None
    ) -> ProjectRead:
        snapshot = await SnapshotService.resolve(session, snapshot_id)
        report = await ProjectDAO.get_by_number(session, snapshot.id, oks_number)
        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Объект отсутствует в выбранном снимке",
            )
        return ProjectRead.from_report(report)
