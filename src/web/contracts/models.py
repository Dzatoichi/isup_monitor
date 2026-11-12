from sqlalchemy import ForeignKeyConstraint, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database import Base


class ProjectContractSnapshot(Base):
    __tablename__ = "project_contract_snapshots"
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
    external_id: Mapped[str | None] = mapped_column(Text)
    organization_external_id: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
