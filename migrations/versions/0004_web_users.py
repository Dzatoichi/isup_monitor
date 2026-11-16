"""Добавляет пользователей, закрепления ОКС и веб-сессии."""

import sqlalchemy as sa
from alembic import op


revision = "0004_web_users"
down_revision = "0003_project_related_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "web_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("yandex_id", sa.Text, nullable=False, unique=True),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
    )
    op.create_table(
        "web_user_projects",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("web_users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("oks_number", sa.BigInteger, sa.ForeignKey("projects.oks_number", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "web_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("web_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_web_sessions_user_id", "web_sessions", ["user_id"])
    op.create_index("ix_web_sessions_expires_at", "web_sessions", ["expires_at"])


def downgrade():
    op.drop_table("web_sessions")
    op.drop_table("web_user_projects")
    op.drop_table("web_users")
