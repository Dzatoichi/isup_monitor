"""Сохраняет результаты обхода и публикует только проверенный полный снимок."""

from datetime import datetime
from typing import Any

from pydantic_core import to_jsonable_python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, sessionmaker

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
        return [IngestionRunRead.model_validate(run) for run in runs]


class IngestionService:
    def __init__(self, sessions: sessionmaker[Session], exchange_threshold: int) -> None:
        self.sessions = sessions
        self.exported_on = datetime.now(REPORT_TIMEZONE).date()
        self.exchange_threshold = exchange_threshold
        self.has_errors = False
        self.seen_numbers: set[int] = set()
        with sessions.begin() as session:
            self.run_id, self.snapshot_id = IngestionDAO.start_run(session, self.exported_on)

    def save_project(self, record: dict[str, Any]) -> None:
        report = make_object_report(
            record, exported_on=self.exported_on, exchange_threshold=self.exchange_threshold
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
                related_keys = {"organizations", "people", "contracts", "documents"}
                source = {key: value for key, value in record.items() if key not in related_keys}
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
        errors = []
        if error is not None:
            # Не помещаем в журнал URL, параметры запросов и исключения с данными подключения.
            errors.append({"message": f"Выгрузка прервана ({type(error).__name__})"})
        elif not complete or not self.seen_numbers:
            errors.append({"message": "Обход реестра не завершён или снимок пуст"})

        status = "failed" if errors or self.has_errors else "partial" if limited else "ready"
        with self.sessions.begin() as session:
            IngestionDAO.finish_run(session, self.run_id, self.snapshot_id, status, errors)
        return status
