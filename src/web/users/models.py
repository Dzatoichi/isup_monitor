from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database import Base


ROLES = {
    "guest": "Гость",
    "admin": "Администратор",
    "leadership": "Руководство",
    "analyst": "Аналитик",
    "manager": "Руководитель проекта",
    "deputy": "Строительный заместитель",
}
SCOPED_ROLES = {"manager", "deputy"}


class User(Base):
    __tablename__ = "web_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    yandex_id: Mapped[str] = mapped_column(Text, unique=True)
    email: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default="guest")


class UserProject(Base):
    __tablename__ = "web_user_projects"

    user_id: Mapped[int] = mapped_column(ForeignKey("web_users.id", ondelete="CASCADE"), primary_key=True)
    oks_number: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.oks_number", ondelete="CASCADE"), primary_key=True
    )
