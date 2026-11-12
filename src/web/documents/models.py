from datetime import date

from sqlalchemy import ForeignKeyConstraint, Date, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database import Base


class DocumentOperationSnapshot(Base):
    __tablename__ = "document_operation_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["snapshot_id", "project_id"],
            ["project_snapshots.snapshot_id", "project_snapshots.project_id"],
            ondelete="CASCADE",
        ),
    )

    snapshot_id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(primary_key=True)
    row_number: Mapped[int] = mapped_column(primary_key=True)
    document_on: Mapped[date | None] = mapped_column(Date)
    document_number: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
