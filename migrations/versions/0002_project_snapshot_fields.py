"""Добавляет типизированные поля снимка объекта."""

from alembic import op
import sqlalchemy as sa


revision = "0002_project_snapshot_fields"
down_revision = "0001_ingestion"
branch_labels = None
depends_on = None

# Маппинг зафиксирован для воспроизводимого переноса старых снимков.
COLUMNS = {
    "name": ("Объект", "text"),
    "stage": ("Стадия", "text"),
    "state": ("Состояние", "text"),
    "customer": ("Заказчик", "text"),
    "status": ("Статус", "text"),
    "conclusion": ("Вывод", "text"),
    "progress": ("Готовность, %", "int"),
    "organization_count": ("Организаций-участников", "int"),
    "organizations_without_team": ("Организаций без команды", "int"),
    "participant_count": ("Участников", "int"),
    "unsigned_count": ("Из них без подписи", "int"),
    "operation_count": ("Операций всего", "int"),
    "operations_last_7_days": ("Операций за период (последние 7 дн.)", "int"),
    "days_without_exchange": ("Дней без обмена", "int"),
    "overdue_days": ("Просрочка этапа, дн.", "int"),
    "last_operation_on": ("Последняя операция", "date"),
    "pir_plan_start": ("Начало ПИР, план", "date"),
    "pir_plan_end": ("Окончание ПИР, план", "date"),
    "pir_actual_start": ("Начало ПИР, факт", "date"),
    "pir_actual_end": ("Окончание ПИР, факт", "date"),
    "smr_plan_start": ("Начало СМР, план", "date"),
    "smr_plan_end": ("Окончание СМР, план", "date"),
    "smr_actual_start": ("Начало СМР, факт", "date"),
    "smr_actual_end": ("Окончание СМР, факт", "date"),
    "contract_cost": ("Стоимость по договорам, руб.", "money"),
    "spent": ("Освоено, руб.", "money"),
    "balance": ("Остаток, руб.", "money"),
}


def upgrade():
    types = {"text": sa.Text, "int": sa.Integer, "date": sa.Date, "money": lambda: sa.Numeric(18, 2)}
    op.add_column("project_snapshots", sa.Column("exported_on", sa.Date(), nullable=True))
    assignments = ["exported_on = s.exported_on"]
    for column, (label, kind) in COLUMNS.items():
        op.add_column("project_snapshots", sa.Column(column, types[kind](), nullable=True))
        value = f"p.report_data->>'{label}'"
        json_type = f"jsonb_typeof(p.report_data->'{label}')"
        if kind == "date":
            iso = f"substring(({value}), 7, 4) || '-' || substring(({value}), 4, 2) || '-' || substring(({value}), 1, 2)"
            expression = (
                f"CASE WHEN ({value}) ~ '^[0-9]{{2}}[.][0-9]{{2}}[.][0-9]{{4}}$' "
                f"AND pg_input_is_valid(({iso}), 'date') THEN ({iso})::date END"
            )
        elif kind == "int":
            maximum = 100 if column == "progress" else 2147483647
            expression = (
                f"CASE WHEN {json_type} = 'number' AND ({value}) ~ '^[0-9]+$' "
                f"THEN CASE WHEN ({value})::numeric <= {maximum} THEN ({value})::integer END END"
            )
        elif kind == "money":
            expression = f"CASE WHEN {json_type} = 'number' THEN ({value})::numeric(18,2) END"
        else:
            expression = f"CASE WHEN {json_type} = 'string' THEN {value} END"
        assignments.append(f"{column} = {expression}")

    op.execute(
        "UPDATE project_snapshots p SET " + ", ".join(assignments)
        + " FROM snapshots s WHERE s.id = p.snapshot_id"
    )
    op.alter_column("project_snapshots", "exported_on", nullable=False)


def downgrade():
    for column in reversed(COLUMNS):
        op.drop_column("project_snapshots", column)
    op.drop_column("project_snapshots", "exported_on")
