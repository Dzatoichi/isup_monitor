"""Текущие закрепления поверх последнего снимка без перезаписи его истории."""

from sqlalchemy import Text, case, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB

from src.web.projects.projects_model import ProjectSnapshot
from src.web.snapshots.models import Snapshot

from .models import Assignment


def current_project_report():
    """Строит SQL-представление последнего снимка с текущими закреплениями. Сохранённый снимок не перезаписывается."""
    latest = (
        select(Snapshot.id)
        .where(Snapshot.status.in_(("ready", "partial")))
        .order_by(Snapshot.exported_on.desc(), Snapshot.id.desc())
        .limit(1).scalar_subquery()
    )
    fields = []
    for source_key, label, assigned in (
        ("project_manager", "Руководитель проекта", Assignment.manager),
        ("construction_deputy", "Строительный заместитель", Assignment.deputy),
    ):
        from_assignment = ProjectSnapshot.source_data["_assignment_fields"].contains([source_key])
        original = case(
            (from_assignment, literal(None, type_=Text)),
            else_=func.coalesce(
                func.nullif(func.btrim(ProjectSnapshot.source_data[source_key].astext), ""),
                func.nullif(func.btrim(ProjectSnapshot.report_data[label].astext), ""),
            ),
        )
        value = func.coalesce(original, func.nullif(func.btrim(assigned), ""))
        fields.extend((label, value))
    amended = ProjectSnapshot.report_data.op("||")(func.jsonb_build_object(*fields))
    return case(
        (ProjectSnapshot.snapshot_id == latest, amended),
        else_=ProjectSnapshot.report_data,
    ).cast(JSONB)
