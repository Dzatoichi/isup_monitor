from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import RedirectResponse

from src.web.auth.dependencies import OptionalUser
from src.web.auth.service import csrf_token
from src.web.dependencies import DatabaseSession
from src.web.documents.dao import DocumentDAO
from src.web.participants.service import ParticipantService
from src.web.snapshots.service import SnapshotService
from src.web.users.models import ROLES
from src.web.users.service import UserService
from src.web.views import templates

from .schemas import ProjectFilters
from .service import ProjectService


router = APIRouter(include_in_schema=False)
SnapshotId = Annotated[int | None, Query(gt=0, le=2147483647)]


@router.get("/")
async def projects_page(
    request: Request, session: DatabaseSession, user: OptionalUser,
    snapshot_id: str = "", offset: Annotated[int, Query(ge=0)] = 0,
    stage: str = "", state: str = "", customer: str = "", status: str = "",
    name: Annotated[str, Query(max_length=500)] = "",
):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    context = {"user": user, "csrf": csrf_token(request), "role": ROLES[user.role]}
    if user.role == "guest":
        return templates.TemplateResponse(request, "guest.html", context)

    if snapshot_id and (not snapshot_id.isascii() or not snapshot_id.isdecimal()
                        or len(snapshot_id) > 10 or not 0 < int(snapshot_id) <= 2147483647):
        raise HTTPException(422, "Некорректный номер снимка")
    filters = ProjectFilters(
        snapshot_id=int(snapshot_id) if snapshot_id else None, offset=offset, stage=stage or None, state=state or None,
        customer=customer or None, status=status or None, name=name.strip() or None,
    )
    scope = await UserService.project_scope(session, user)
    context["filters"] = filters
    try:
        result = await ProjectService.get_all(session, filters, scope=scope)
        page_count = (result.total + result.limit - 1) // result.limit
        page = min(result.offset // result.limit + 1, max(1, page_count))
        page_offset = (page - 1) * result.limit
        if result.offset != page_offset:
            query = dict(request.query_params)
            query.update(snapshot_id=result.snapshot.id, offset=page_offset)
            return RedirectResponse("/?" + urlencode(query), status_code=303)
        context.update(result=result, page=page, page_count=page_count)
    except HTTPException as error:
        if error.status_code not in {404, 409}:
            raise
        context["error"] = error.detail
    return templates.TemplateResponse(request, "projects.html", context)


@router.get("/projects/{oks_number}")
async def project_page(
    request: Request, session: DatabaseSession, user: OptionalUser,
    oks_number: Annotated[int, Path(gt=0, le=9223372036854775807)], snapshot_id: SnapshotId = None,
    history_type: str = "",
):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user.role == "guest":
        return RedirectResponse("/", status_code=303)
    await UserService.check_project(session, user, oks_number)
    snapshot = await SnapshotService.resolve(session, snapshot_id)
    project = await ProjectService.get_by_number(session, oks_number, snapshot.id)
    show_contacts = user.role in {"admin", "leadership"}
    participants = await ParticipantService.get_for_project(
        session, oks_number, snapshot.id, show_contacts=show_contacts
    )
    documents = await DocumentDAO.get_for_project(session, snapshot.id, oks_number)
    history_types = ProjectService.HISTORY_FIELDS
    if history_type and history_type not in history_types:
        raise HTTPException(422, "Неизвестный тип события")
    history = await ProjectService.get_history(session, oks_number, snapshot, history_type)
    return templates.TemplateResponse(request, "project.html", {
        "user": user, "csrf": csrf_token(request), "project": project.root,
        "snapshot": snapshot, "participants": participants.items, "show_contacts": show_contacts,
        "documents": documents,
        "history": history, "history_type": history_type, "history_types": history_types,
    })
