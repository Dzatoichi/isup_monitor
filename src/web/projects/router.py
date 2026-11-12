from typing import Annotated

from fastapi import APIRouter, Path, Query

from src.web.dependencies import DatabaseSession

from .schemas import ProjectFilters, ProjectList, ProjectRead
from .service import ProjectService


router = APIRouter(prefix="/projects", tags=["Объекты"])


@router.get("", response_model=ProjectList)
async def get_projects(
    session: DatabaseSession,
    filters: Annotated[ProjectFilters, Query()],
) -> ProjectList:
    return await ProjectService.get_all(session, filters)


@router.get("/{oks_number}", response_model=ProjectRead)
async def get_project(
    oks_number: Annotated[int, Path(gt=0, le=9223372036854775807)],
    session: DatabaseSession,
    snapshot_id: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
) -> ProjectRead:
    return await ProjectService.get_by_number(session, oks_number, snapshot_id)
