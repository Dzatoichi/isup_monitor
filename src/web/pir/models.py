from datetime import date
from sqlalchemy import ForeignKeyConstraint, Text, Date, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database import Base


class PirDocumentSnapshot(Base):
    __tablename__ = "pir_document_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(["snapshot_id", "project_id"],
                             ["project_snapshots.snapshot_id", "project_snapshots.project_id"], ondelete="CASCADE"),
    )
    snapshot_id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(primary_key=True)
    row_number: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    cipher: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(Text)
    created_on: Mapped[date | None] = mapped_column(Date)
    approved_on: Mapped[date | None] = mapped_column(Date)
    expected_approval_on: Mapped[date | None] = mapped_column(Date)
    transferred_on: Mapped[date | None] = mapped_column(Date)
    issued_on: Mapped[date | None] = mapped_column(Date)
    remark_count: Mapped[int | None] = mapped_column(Integer)
    delay_days: Mapped[int | None] = mapped_column(Integer)
    source_data: Mapped[dict] = mapped_column(JSONB)
