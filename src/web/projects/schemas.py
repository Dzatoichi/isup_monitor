from typing import Any

from pydantic import BaseModel, Field, RootModel

from src.parser.report import REPORT_FIELDS
from src.web.snapshots.schemas import SnapshotRead


class ProjectFilters(BaseModel):
    snapshot_id: int | None = Field(default=None, gt=0, le=2147483647)
    stage: str | None = None
    state: str | None = None
    customer: str | None = None
    status: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class ProjectRead(RootModel[dict[str, Any]]):
    @classmethod
    def from_report(cls, report: dict[str, Any]) -> "ProjectRead":
        return cls({field: report.get(field) for field in REPORT_FIELDS})


class ProjectList(BaseModel):
    snapshot: SnapshotRead
    items: list[ProjectRead]
    offset: int
    limit: int
