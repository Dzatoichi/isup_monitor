"""Сохраняет авторство и исходные реквизиты документов."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_document_sources"
down_revision = "0005_rules_events"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("external_id", "author", "section"):
        op.add_column("document_operation_snapshots", sa.Column(name, sa.Text))
    op.add_column("document_operation_snapshots", sa.Column("source_data", JSONB))


def downgrade():
    for name in ("external_id", "author", "section", "source_data"):
        op.drop_column("document_operation_snapshots", name)
