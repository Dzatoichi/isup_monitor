from typing import Annotated

from fastapi import APIRouter, Path, Query

from src.web.auth.dependencies import Reader
from src.web.users.service import UserService
from src.web.dependencies import DatabaseSession

from .schemas import ProjectParticipantsRead
from .service import ParticipantService


router = APIRouter(prefix="/projects", tags=["Участники"])


@router.get("/{oks_number}/participants", response_model=ProjectParticipantsRead)
async def get_project_participants(
    oks_number: Annotated[int, Path(gt=0, le=9223372036854775807)],
    session: DatabaseSession,
    user: Reader,
    snapshot_id: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
) -> ProjectParticipantsRead:
    await UserService.check_project(session, user, oks_number)
    return await ParticipantService.get_for_project(
        session, oks_number, snapshot_id, show_contacts=user.role in {"admin", "leadership"}
    )
