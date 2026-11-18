"""Документы ПД и РД из модуля ПИР."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_pir_documents"
down_revision = "0006_document_sources"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pir_document_snapshots",
        sa.Column("snapshot_id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, primary_key=True),
        sa.Column("row_number", sa.Integer, primary_key=True),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        *(sa.Column(name, sa.Text) for name in ("cipher", "name", "section", "status")),
        *(sa.Column(name, sa.Integer) for name in ("version", "remark_count", "delay_days")),
        *(sa.Column(name, sa.Date) for name in ("created_on", "approved_on", "expected_approval_on", "transferred_on", "issued_on")),
        sa.Column("source_data", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id", "project_id"],
                                ["project_snapshots.snapshot_id", "project_snapshots.project_id"], ondelete="CASCADE"),
    )


def downgrade():
    op.drop_table("pir_document_snapshots")
