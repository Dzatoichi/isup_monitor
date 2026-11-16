from typing import Annotated

from fastapi import APIRouter, Path, Query
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from src.web.auth.dependencies import Reader
from src.web.snapshots.service import SnapshotService
from src.web.users.service import UserService
from src.web.dependencies import DatabaseSession

from .schemas import ProjectFilters, ProjectList, ProjectRead
from .export import build_workbook, load_export_rows
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


@router.get("/export.xlsx", response_class=Response)
async def export_projects(
    session: DatabaseSession,
    user: Reader,
    snapshot_id: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
) -> Response:
    scope = await UserService.project_scope(session, user)
    snapshot = await SnapshotService.resolve(session, snapshot_id)
    show_contacts = user.role in {"admin", "leadership"}
    rows = await load_export_rows(session, snapshot.id, scope, show_contacts=show_contacts)
    content = await run_in_threadpool(build_workbook, rows, show_contacts=show_contacts)
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="isup-snapshot-{snapshot.id}.xlsx"'},
    )


@router.get("/{oks_number}", response_model=ProjectRead)
async def get_project(
    oks_number: Annotated[int, Path(gt=0, le=9223372036854775807)],
    session: DatabaseSession,
    user: Reader,
    snapshot_id: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
) -> ProjectRead:
    await UserService.check_project(session, user, oks_number)
    return await ProjectService.get_by_number(session, oks_number, snapshot_id)
