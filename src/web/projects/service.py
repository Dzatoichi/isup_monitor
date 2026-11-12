from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.web.snapshots.schemas import SnapshotRead
from src.web.snapshots.service import SnapshotService

from .dao import ProjectDAO
from .schemas import ProjectFilters, ProjectList, ProjectRead


class ProjectService:
    @staticmethod
    async def get_all(session: AsyncSession, filters: ProjectFilters) -> ProjectList:
        snapshot = await SnapshotService.resolve(session, filters.snapshot_id)
        rows = await ProjectDAO.get_all(session, snapshot.id, filters)
        return ProjectList(
            snapshot=SnapshotRead.model_validate(snapshot),
            items=[ProjectRead.from_report(report) for _, report in rows],
            offset=filters.offset,
            limit=filters.limit,
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
