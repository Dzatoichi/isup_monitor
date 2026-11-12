from fastapi import APIRouter

from src.web.dependencies import DatabaseSession

from .schemas import SnapshotRead
from .service import SnapshotService


router = APIRouter(prefix="/snapshots", tags=["Снимки"])


@router.get("/latest", response_model=SnapshotRead)
async def get_latest_snapshot(session: DatabaseSession) -> SnapshotRead:
    snapshot = await SnapshotService.get_latest_ready(session)
    return SnapshotRead.model_validate(snapshot)
