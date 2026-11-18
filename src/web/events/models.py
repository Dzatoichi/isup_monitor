from datetime import date
from sqlalchemy import Date, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.shared.database import Base


class ProjectEvent(Base):
    """Событие фиксируется один раз в транзакции публикации снимка."""
    __tablename__ = "project_events"
    __table_args__ = (UniqueConstraint("snapshot_id", "project_id", "category", "field"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    observed_on: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(Text)
    field: Mapped[str] = mapped_column(Text)
    before: Mapped[object | None] = mapped_column(JSONB)
    after: Mapped[object | None] = mapped_column(JSONB)
