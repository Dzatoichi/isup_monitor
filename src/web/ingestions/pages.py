from fastapi import APIRouter, Request

from src.web.auth.dependencies import Admin
from src.web.auth.service import csrf_token
from src.web.dependencies import DatabaseSession
from src.web.views import templates

from .service import IngestionQueryService


router = APIRouter(include_in_schema=False)


@router.get("/admin/ingestions")
async def ingestion_page(request: Request, session: DatabaseSession, admin: Admin):
    return templates.TemplateResponse(request, "ingestions.html", {
        "user": admin, "csrf": csrf_token(request),
        "runs": await IngestionQueryService.get_all(session, offset=0, limit=50),
    })
