from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from src.web.assignments.router import router as assignments_router
from src.web.regulations.router import router as regulations_router
from src.web.analytics.router import router as analytics_router
from src.web.auth.dependencies import require_admin, require_reader
from src.web.auth.router import router as auth_router
from src.web.ingestions.pages import router as ingestion_pages
from src.web.participants.pages import router as participant_pages
from src.web.projects.pages import router as project_pages
from src.web.users.router import router as users_router
from src.web.views import WEB_DIR

from src.web.ingestions.router import router as ingestions_router
from src.web.participants.participants_router import router as participants_router
from src.web.projects.router import router as projects_router
from src.web.snapshots.router import router as snapshots_router


app = FastAPI(title="ИСУП Монитор")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(snapshots_router, prefix="/api/v1", dependencies=[Depends(require_reader)])
app.include_router(ingestions_router, prefix="/api/v1", dependencies=[Depends(require_admin)])
app.include_router(participants_router, prefix="/api/v1")

app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
app.include_router(auth_router)
app.include_router(project_pages)
app.include_router(analytics_router)
app.include_router(assignments_router)
app.include_router(regulations_router)
app.include_router(participant_pages)
app.include_router(users_router)
app.include_router(ingestion_pages)


@app.middleware("http")
async def disable_private_caching(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health", tags=["Служебные"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
