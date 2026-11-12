"""Добавляет журнал выгрузок и снимки объектов."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0001_ingestion"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("oks_number", sa.BigInteger, nullable=False, unique=True),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("processed_count", sa.Integer, nullable=False),
        sa.Column("errors", JSONB, nullable=False),
        sa.CheckConstraint("status IN ('running', 'ready', 'partial', 'failed')", name="ck_run_status"),
    )
    op.create_table(
        "snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("ingestion_runs.id"), nullable=False, unique=True),
        sa.Column("exported_on", sa.Date, nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.CheckConstraint("status IN ('running', 'ready', 'partial', 'failed')", name="ck_snapshot_status"),
    )
    op.create_table(
        "project_snapshots",
        sa.Column("snapshot_id", sa.Integer, sa.ForeignKey("snapshots.id"), primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("source_data", JSONB, nullable=False),
        sa.Column("report_data", JSONB, nullable=False),
    )


def downgrade():
    op.drop_table("project_snapshots")
    op.drop_table("snapshots")
    op.drop_table("ingestion_runs")
    op.drop_table("projects")
