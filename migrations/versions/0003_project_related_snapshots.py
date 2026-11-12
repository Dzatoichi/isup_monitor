"""Добавляет записи организаций, участников, договоров и документов снимка."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0003_project_related_snapshots"
down_revision = "0002_project_snapshot_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_organization_snapshots",
        sa.Column("snapshot_id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, primary_key=True),
        sa.Column("row_number", sa.Integer, primary_key=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("external_id", sa.Text, nullable=True),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("role", sa.Text, nullable=True),
        sa.Column("inn", sa.Text, nullable=True),
        sa.Column("kpp", sa.Text, nullable=True),
        sa.Column("ogrn", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "project_id"],
            ["project_snapshots.snapshot_id", "project_snapshots.project_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "project_participant_snapshots",
        sa.Column("snapshot_id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, primary_key=True),
        sa.Column("row_number", sa.Integer, primary_key=True),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("organization_external_id", sa.Text, nullable=False),
        sa.Column("full_name", sa.Text, nullable=True),
        sa.Column("position", sa.Text, nullable=True),
        sa.Column("role", sa.Text, nullable=True),
        sa.Column("signed", sa.Boolean, nullable=True),
        sa.Column("email", sa.Text, nullable=True),
        sa.Column("phone", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "project_id"],
            ["project_snapshots.snapshot_id", "project_snapshots.project_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "project_contract_snapshots",
        sa.Column("snapshot_id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, primary_key=True),
        sa.Column("row_number", sa.Integer, primary_key=True),
        sa.Column("external_id", sa.Text, nullable=True),
        sa.Column("organization_external_id", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "project_id"],
            ["project_snapshots.snapshot_id", "project_snapshots.project_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "document_operation_snapshots",
        sa.Column("snapshot_id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, primary_key=True),
        sa.Column("row_number", sa.Integer, primary_key=True),
        sa.Column("document_on", sa.Date, nullable=True),
        sa.Column("document_number", sa.Text, nullable=True),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("document_type", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "project_id"],
            ["project_snapshots.snapshot_id", "project_snapshots.project_id"],
            ondelete="CASCADE",
        ),
    )
    # В старых снимках были строки организаций и даты документов.
    op.execute("""
        INSERT INTO project_organization_snapshots
            (snapshot_id, project_id, row_number, source, name, role, inn, kpp, ogrn)
        SELECT p.snapshot_id, p.project_id, x.ordinality, 'isup',
               x.data->>'organization', x.data->>'role', x.data->>'inn',
               x.data->>'kpp', x.data->>'ogrn'
        FROM project_snapshots p
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(p.source_data->'participants') = 'array'
                 THEN p.source_data->'participants' ELSE '[]'::jsonb END
        ) WITH ORDINALITY x(data, ordinality)
        WHERE jsonb_typeof(x.data) = 'object'
    """)
    op.execute("""
        INSERT INTO document_operation_snapshots
            (snapshot_id, project_id, row_number, document_on)
        SELECT p.snapshot_id, p.project_id, x.ordinality,
               CASE WHEN x.value ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                         AND pg_input_is_valid(x.value, 'date') THEN x.value::date END
        FROM project_snapshots p
        CROSS JOIN LATERAL jsonb_array_elements_text(
            CASE WHEN jsonb_typeof(p.source_data->'operation_dates') = 'array'
                 THEN p.source_data->'operation_dates' ELSE '[]'::jsonb END
        ) WITH ORDINALITY x(value, ordinality)
    """)


def downgrade():
    op.drop_table("document_operation_snapshots")
    op.drop_table("project_contract_snapshots")
    op.drop_table("project_participant_snapshots")
    op.drop_table("project_organization_snapshots")
