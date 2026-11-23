"""Сохраняет управленческую книгу и сведения о её составе атомарно."""
import json
import os
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from src.parser.report import REPORT_TIMEZONE
from src.shared.database import db_helper
from src.web.projects.export import build_workbook, load_export_rows
from src.web.snapshots.service import SnapshotService


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=".isup-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class ExportService:
    @staticmethod
    async def save(output_dir, snapshot_id=None, numbers=None):
        """Служебная выгрузка без телефонов и email. numbers ограничивает все листы и историю."""
        async with db_helper.session_factory() as session:
            snapshot = await SnapshotService.resolve(session, snapshot_id)
            rows = await load_export_rows(session, snapshot.id, numbers, show_contacts=False)
            name = f"isup-{snapshot.exported_on.isoformat()}-snapshot-{snapshot.id}"
        folder = Path(output_dir)
        path = folder / f"{name}.xlsx"
        content = build_workbook(rows, show_contacts=False)
        atomic_write(path, content)
        manifest = {
            "snapshot_id": snapshot.id, "snapshot_status": snapshot.status,
            "snapshot_date": snapshot.exported_on.isoformat(),
            "generated_at": datetime.now(REPORT_TIMEZONE).isoformat(),
            "objects": len(rows["Сводка объектов"]), "issues": len(rows["Проблемы"]),
            "restricted": numbers is not None, "contacts_included": False,
            "file": path.name, "sheets": list(rows), "disk": "Не отправлено",
            "limitations": ["Источник ИД и история движения не подключены", "Старые снимки без реквизитов ОЖР требуют повторной проверки"],
        }
        atomic_write(folder / f"{name}.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode())
        return path, manifest
