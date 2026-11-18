from datetime import date, datetime
from sqlalchemy import Date, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.shared.database import Base


class Regulation(Base):
    """Неизменяемая версия правил, применяемая с указанной даты."""
    __tablename__ = "regulations"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(Text, unique=True)
    effective_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rules: Mapped[dict] = mapped_column(JSONB)
