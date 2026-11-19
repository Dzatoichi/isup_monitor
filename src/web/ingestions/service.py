"""Сохраняет результаты обхода и публикует только проверенный полный снимок."""

from datetime import datetime
from typing import Any

from pydantic_core import to_jsonable_python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, sessionmaker

from src.web.assignments.models import Assignment
from src.web.regulations.dao import RegulationDAO
from src.web.regulations.schemas import TrafficRules
from src.web.snapshots.models import Snapshot
from src.web.events.dao import EventDAO

from src.parser.validation import validate_record
from src.parser.report import REPORT_TIMEZONE, make_object_report
from src.web.projects.dao import ProjectDAO
from src.web.snapshots.dao import SnapshotDAO
from src.web.snapshots.related_dao import RelatedSnapshotDAO

from .dao import IngestionDAO
from .schemas import IngestionRunRead


class IngestionQueryService:
    @staticmethod
    async def get_all(session: AsyncSession, *, offset: int, limit: int) -> list[IngestionRunRead]:
        runs = await IngestionDAO.get_all(session, offset=offset, limit=limit)
        results = []
        for run in runs:
            # В журнале показываем время по Красноярску, включая старые запуски.
            entry = IngestionRunRead.model_validate(run)
            entry.started_at = entry.started_at.astimezone(REPORT_TIMEZONE)
            if entry.finished_at is not None:
                entry.finished_at = entry.finished_at.astimezone(REPORT_TIMEZONE)
            results.append(entry)
        return results


class IngestionService:
    def __init__(self, sessions: sessionmaker[Session], exchange_threshold: int) -> None:
        """Открывает запуск выгрузки и закрепляет за снимком версию правил, действующую на дату сбора."""
        self.sessions = sessions
        self.exported_on = datetime.now(REPORT_TIMEZONE).date()
        self.exchange_threshold = exchange_threshold
        self.has_errors = False
        self.seen_numbers: set[int] = set()
        with sessions.begin() as session:
            regulation = RegulationDAO.ensure_applicable(session, self.exported_on)
            self.rules = TrafficRules.model_validate(regulation.rules if regulation else {}).model_dump()
            self.run_id, self.snapshot_id = IngestionDAO.start_run(session, self.exported_on)
            session.get_one(Snapshot, self.snapshot_id).regulation_id = regulation.id if regulation else None

    def save_project(self, record: dict[str, Any]) -> None:
        """Проверяет объект, подставляет ответственных и сохраняет его показатели и дочерние записи в одной транзакции."""
        validate_record(record)
        record["_traffic_rules"] = self.rules
        # Сохраняем происхождение ФИО, чтобы последующее изменение справочника
        # не перепутать с ответственным, полученным непосредственно из ИСУП.
        for key in record.get("_assignment_fields", []):
            record[key] = None
        record["_assignment_fields"] = []
        if record.get("oks_number"):
            with self.sessions.begin() as session:
                assignment = session.get(Assignment, record["oks_number"])
                if assignment:
                    for key, value in (("project_manager", assignment.manager), ("construction_deputy", assignment.deputy)):
                        if not record.get(key) or not str(record[key]).strip():
                            record[key] = value
                            record["_assignment_fields"].append(key)
        if record.get("stage") == "СМР" and record.get("oks_number"):
            with self.sessions.begin() as session:
                project_id = ProjectDAO.upsert(session, record["oks_number"])
                record["progress_stalled_8_weeks"] = SnapshotDAO.progress_stalled(
                    session, project_id, self.exported_on, record.get("progress"), self.rules["stagnation_days"]
                )
        report = make_object_report(
            record, exported_on=self.exported_on, exchange_threshold=self.exchange_threshold, rules=self.rules
        )
        number = report["Номер в ИСУП"]
        errors = [
            {"oks_number": number, "field": key, "message": value}
            for key, value in record.items() if key.endswith("_error")
        ]
        if not number:
            errors.append({"field": "oks_number", "message": "Нет номера ОКС", "row_index": record.get("row_index")})
        if not isinstance(record.get("name"), str) or not record["name"].strip():
            errors.append({"oks_number": number, "field": "name", "message": "Нет названия объекта"})
        if record.get("progress") is not None and report["Готовность, %"] is None:
            errors.append({"oks_number": number, "field": "progress", "message": "Готовность вне диапазона 0–100"})
        if number in self.seen_numbers:
            errors.append({"oks_number": number, "message": "Объект повторился в реестре"})

        # Сетевой обход происходит вне транзакции. Здесь сохраняем один объект.
        with self.sessions.begin() as session:
            if number:
                project_id = ProjectDAO.upsert(session, number)
                related_keys = {"organizations", "people", "contracts", "documents", "pir_documents"}
                source = {key: value for key, value in record.items() if key not in related_keys}
                source["sections_read"] = {key: record.get(key) is not None for key in related_keys}
                SnapshotDAO.upsert_project(
                    session, self.snapshot_id, project_id, self.exported_on,
                    to_jsonable_python(source), report,
                )
                related = {key: record.get(key) for key in related_keys}
                if related["organizations"] is None and record.get("participants") is not None:
                    related["organizations"] = [
                        {
                            "source": "isup", "name": row["organization"],
                            **{key: row.get(key) for key in ("role", "inn", "kpp", "ogrn")},
                        }
                        for row in record["participants"]
                    ]
                RelatedSnapshotDAO.save(session, self.snapshot_id, project_id, related)
            IngestionDAO.record_project(session, self.run_id, errors)

        if number:
            self.seen_numbers.add(number)
        self.has_errors |= bool(errors)

    def finish(
        self, *, complete: bool = False, limited: bool = False, error: BaseException | None = None
    ) -> str:
        """Завершает запуск. Полный результат получает ready, неполный завершённый результат — partial, прерванный — failed."""
        errors = []
        if error is not None:
            # Не помещаем в журнал URL, параметры запросов и исключения с данными подключения.
            errors.append({"message": f"Выгрузка прервана ({type(error).__name__})"})
        elif not complete or not self.seen_numbers:
            errors.append({"message": "Обход реестра не завершён или снимок пуст"})

        # Ошибки отдельных объектов оставляют пригодные для просмотра данные.
        if errors:
            status = "failed"
        elif limited or self.has_errors:
            status = "partial"
        else:
            status = "ready"
        with self.sessions.begin() as session:
            if status in {"ready", "partial"}:
                EventDAO.capture(session, self.snapshot_id)
            IngestionDAO.finish_run(session, self.run_id, self.snapshot_id, status, errors)
        return status
