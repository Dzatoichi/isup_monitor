from collections import defaultdict
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from src.web.auth.dependencies import Reader
from src.web.auth.service import csrf_token
from src.web.dependencies import DatabaseSession
from src.web.snapshots.service import SnapshotService
from src.web.users.service import UserService
from src.web.views import templates

from .participants_dao import ParticipantDAO


router = APIRouter(include_in_schema=False)


@router.get("/participants")
async def participants_page(
    request: Request, session: DatabaseSession, user: Reader,
    snapshot_id: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
    organization: Annotated[str, Query(max_length=300)] = "",
    role: Annotated[str, Query(max_length=300)] = "",
    signature: Literal["all", "signed", "unsigned", "unknown"] = "all",
):
    scope = await UserService.project_scope(session, user)
    context = {
        "user": user, "csrf": csrf_token(request), "organization": organization,
        "participant_role": role, "signature": signature,
        "show_contacts": user.role in {"admin", "leadership"},
    }
    try:
        snapshot = await SnapshotService.resolve(session, snapshot_id)
    except HTTPException as error:
        if error.status_code not in {404, 409}:
            raise
        context["error"] = error.detail
    else:
        rows = await ParticipantDAO.get_register(session, snapshot.id, scope, organization, role, signature)
        counts = defaultdict(lambda: (set(), set()))
        names = {}
        for number, _, org_id, org_name, participant in rows:
            names.setdefault(org_id, org_name or org_id)
            projects, unsigned = counts[org_id]
            projects.add(number)
            if participant.signed is False:
                unsigned.add(participant.external_id)
        context.update(snapshot=snapshot, rows=rows, counts=sorted(
            (names[org_id], len(projects), len(unsigned)) for org_id, (projects, unsigned) in counts.items()
        ))
    return templates.TemplateResponse(request, "participants.html", context)
