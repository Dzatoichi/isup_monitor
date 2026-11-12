from datetime import date

from pydantic import BaseModel, ConfigDict


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    exported_on: date
    status: str
