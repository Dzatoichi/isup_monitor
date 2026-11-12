from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IngestionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    processed_count: int
