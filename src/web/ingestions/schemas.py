from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field


class IngestionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    processed_count: int

    @computed_field
    @property
    def duration_seconds(self) -> int | None:
        if self.finished_at is None:
            return None
        return max(0, int((self.finished_at - self.started_at).total_seconds()))
