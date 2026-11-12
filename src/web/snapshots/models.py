from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database import Base
from src.web.ingestions.models import IngestionRun



class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'ready', 'partial', 'failed')", name="ck_snapshot_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey(IngestionRun.id), unique=True)
    exported_on: Mapped[date]
    status: Mapped[str] = mapped_column(String(12))

