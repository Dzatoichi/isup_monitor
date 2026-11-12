from fastapi import FastAPI

from src.web.ingestions.router import router as ingestions_router
from src.web.projects.router import router as projects_router
from src.web.snapshots.router import router as snapshots_router


app = FastAPI(title="ИСУП Монитор")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(snapshots_router, prefix="/api/v1")
app.include_router(ingestions_router, prefix="/api/v1")


@app.get("/health", tags=["Служебные"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
