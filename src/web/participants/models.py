from sqlalchemy import ForeignKeyConstraint, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database import Base


class ProjectParticipantSnapshot(Base):
    __tablename__ = "project_participant_snapshots"
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
    external_id: Mapped[str] = mapped_column(Text)
    organization_external_id: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str | None] = mapped_column(Text)
    position: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text)
    signed: Mapped[bool | None] = mapped_column(Boolean)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
