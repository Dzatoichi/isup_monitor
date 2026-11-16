from pydantic import BaseModel

from src.web.snapshots.schemas import SnapshotRead


class ParticipantRead(BaseModel):
    external_id: str
    organization_external_id: str
    organization: str | None
    organization_role: str | None
    organization_inn: str | None
    full_name: str | None
    position: str | None
    role: str | None
    signed: bool | None
    email: str | None = None
    phone: str | None = None


class ProjectParticipantsRead(BaseModel):
    snapshot: SnapshotRead
    oks_number: int
    items: list[ParticipantRead]
