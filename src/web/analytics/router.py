from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from src.web.auth.dependencies import Reader
from src.web.auth.service import csrf_token
from src.web.dependencies import DatabaseSession
from src.web.snapshots.service import SnapshotService
from src.web.users.service import UserService
from src.web.views import templates

from .service import AnalyticsService


router = APIRouter(prefix="/analytics", include_in_schema=False)
Screen = Literal["summary", "problems", "completeness"]
TITLES = {"summary": "Сводка", "problems": "Проблемные объекты", "completeness": "Полнота данных"}


@router.get("/{screen}")
async def analytics_page(
    screen: Screen, request: Request, session: DatabaseSession, user: Reader,
    snapshot_id: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
):
    scope = await UserService.project_scope(session, user)
    context = {"user": user, "csrf": csrf_token(request), "screen": screen, "title": TITLES[screen]}
    try:
        snapshot = await SnapshotService.resolve(session, snapshot_id)
    except HTTPException as error:
        if error.status_code not in {404, 409}:
            raise
        context["error"] = error.detail
    else:
        context["snapshot"] = snapshot
        if screen == "summary":
            context["metrics"], context["weeks"] = await AnalyticsService.summary(session, snapshot, scope)
        elif screen == "problems":
            context["rows"] = await AnalyticsService.problems(session, snapshot, scope)
        else:
            context["rows"] = await AnalyticsService.completeness(session, snapshot, scope)
    return templates.TemplateResponse(request, "analytics.html", context)
