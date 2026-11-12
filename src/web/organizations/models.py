from sqlalchemy import ForeignKeyConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database import Base


class ProjectOrganizationSnapshot(Base):
    __tablename__ = "project_organization_snapshots"
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
    source: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text)
    inn: Mapped[str | None] = mapped_column(Text)
    kpp: Mapped[str | None] = mapped_column(Text)
    ogrn: Mapped[str | None] = mapped_column(Text)
