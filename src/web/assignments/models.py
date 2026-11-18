from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.shared.database import Base


class Assignment(Base):
    """Резервные закрепления по приказу заказчика."""
    __tablename__ = "project_assignments"

    oks_number: Mapped[int] = mapped_column(BigInteger, ForeignKey("projects.oks_number"), primary_key=True)
    manager: Mapped[str | None] = mapped_column(Text)
    manager_email: Mapped[str | None] = mapped_column(Text)
    manager_position: Mapped[str | None] = mapped_column(Text)
    deputy: Mapped[str | None] = mapped_column(Text)
    deputy_email: Mapped[str | None] = mapped_column(Text)
    deputy_position: Mapped[str | None] = mapped_column(Text)
