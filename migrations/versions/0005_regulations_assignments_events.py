"""Справочник закреплений, версии правил и события объектов."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_rules_events"
down_revision = "0004_web_users"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_assignments",
        sa.Column("oks_number", sa.BigInteger, sa.ForeignKey("projects.oks_number"), primary_key=True),
        *(sa.Column(name, sa.Text) for name in (
            "manager", "manager_email", "manager_position", "deputy", "deputy_email", "deputy_position"
        )),
    )
    op.create_table(
        "regulations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("version", sa.Text, nullable=False, unique=True),
        sa.Column("effective_on", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("rules", JSONB, nullable=False),
    )
    op.create_table(
        "project_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("snapshot_id", sa.Integer, sa.ForeignKey("snapshots.id"), nullable=False),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("observed_on", sa.Date, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("field", sa.Text, nullable=False),
        sa.Column("before", JSONB),
        sa.Column("after", JSONB),
        sa.UniqueConstraint("snapshot_id", "project_id", "category", "field"),
    )
    op.create_index("ix_project_events_project_id", "project_events", ["project_id"])
    op.add_column("snapshots", sa.Column("regulation_id", sa.Integer, sa.ForeignKey("regulations.id")))


def downgrade():
    op.drop_column("snapshots", "regulation_id")
    op.drop_table("project_events")
    op.drop_table("regulations")
    op.drop_table("project_assignments")
