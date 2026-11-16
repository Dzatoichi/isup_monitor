from typing import Annotated

from fastapi import APIRouter, Path, Query

from src.web.auth.dependencies import Reader
from src.web.users.service import UserService
from src.web.dependencies import DatabaseSession

from .schemas import ProjectFilters, ProjectList, ProjectRead
from .service import ProjectService


router = APIRouter(prefix="/projects", tags=["Объекты"])


@router.get("", response_model=ProjectList)
async def get_projects(
    session: DatabaseSession,
    user: Reader,
    filters: Annotated[ProjectFilters, Query()],
) -> ProjectList:
    scope = await UserService.project_scope(session, user)
    return await ProjectService.get_all(session, filters, scope=scope)


@router.get("/{oks_number}", response_model=ProjectRead)
async def get_project(
    oks_number: Annotated[int, Path(gt=0, le=9223372036854775807)],
    session: DatabaseSession,
    user: Reader,
    snapshot_id: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
) -> ProjectRead:
    await UserService.check_project(session, user, oks_number)
    return await ProjectService.get_by_number(session, oks_number, snapshot_id)
