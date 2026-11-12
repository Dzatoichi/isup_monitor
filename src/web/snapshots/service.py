from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .dao import SnapshotDAO
from .models import Snapshot


class SnapshotService:
    @staticmethod
    async def resolve(session: AsyncSession, snapshot_id: int | None) -> Snapshot:
        if snapshot_id is None:
            return await SnapshotService.get_latest_ready(session)
        snapshot = await SnapshotDAO.get_by_id(session, snapshot_id)
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Снимок не найден")
        if snapshot.status == "running":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Снимок ещё формируется")
        return snapshot

    @staticmethod
    async def get_latest_ready(session: AsyncSession) -> Snapshot:
        snapshot = await session.run_sync(SnapshotDAO.get_latest_ready)
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Нет готового снимка ИСУП",
            )
        return snapshot
