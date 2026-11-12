from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from src.shared.database import Base
from src.web.snapshots.models import Snapshot


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    oks_number: Mapped[int] = mapped_column(BigInteger, unique=True)


class ProjectSnapshot(Base):
    __tablename__ = "project_snapshots"

    snapshot_id: Mapped[int] = mapped_column(ForeignKey(Snapshot.id), primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey(Project.id), primary_key=True)
    source_data: Mapped[dict] = mapped_column(JSONB)
    report_data: Mapped[dict] = mapped_column(JSONB)

    exported_on: Mapped[date]
    name: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    customer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[int | None]
    organization_count: Mapped[int | None]
    organizations_without_team: Mapped[int | None]
    participant_count: Mapped[int | None]
    unsigned_count: Mapped[int | None]
    operation_count: Mapped[int | None]
    operations_last_7_days: Mapped[int | None]
    days_without_exchange: Mapped[int | None]
    overdue_days: Mapped[int | None]
    last_operation_on: Mapped[date | None]
    pir_plan_start: Mapped[date | None]
    pir_plan_end: Mapped[date | None]
    pir_actual_start: Mapped[date | None]
    pir_actual_end: Mapped[date | None]
    smr_plan_start: Mapped[date | None]
    smr_plan_end: Mapped[date | None]
    smr_actual_start: Mapped[date | None]
    smr_actual_end: Mapped[date | None]
    contract_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    spent: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
