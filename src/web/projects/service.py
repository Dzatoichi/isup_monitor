from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.parser.report import DATE_FIELDS
from src.web.snapshots.schemas import SnapshotRead
from src.web.snapshots.service import SnapshotService

from .dao import ProjectDAO
from .schemas import ProjectFilters, ProjectList, ProjectRead


class ProjectService:
    HISTORY_FIELDS = {
        "Характеристики": ("Стадия", "Состояние", "Готовность, %"),
        "Сроки": tuple(DATE_FIELDS),
        "Финансы": ("Стоимость по договорам, руб.", "Освоено, руб.", "Остаток, руб."),
        "Ответственные": ("Строительный заместитель", "Руководитель проекта"),
        "Светофор": ("Статус", "Вывод"),
    }

    @staticmethod
    async def get_history(session, oks_number, snapshot, category):
        rows = await ProjectDAO.get_history(session, oks_number, snapshot)
        events = []
        for previous, current in zip(rows, rows[1:]):
            snapshot_id, observed_on, report = current
            old_report = previous[2]
            for group, fields in ProjectService.HISTORY_FIELDS.items():
                if category and category != group:
                    continue
                for field in fields:
                    before, after = old_report.get(field), report.get(field)
                    # Пропуск значения может означать, что раздел не считался.
                    if before is not None and after is not None and before != after:
                        events.append((snapshot_id, observed_on, field, before, after))
        return list(reversed(events))

    @staticmethod
    async def get_all(session: AsyncSession, filters: ProjectFilters, *, scope: set[int] | None = None) -> ProjectList:
        snapshot = await SnapshotService.resolve(session, filters.snapshot_id)
        rows, total = await ProjectDAO.get_all(session, snapshot.id, filters, scope)
        return ProjectList(
            snapshot=SnapshotRead.model_validate(snapshot),
            items=[ProjectRead.from_report(report) for _, report in rows],
            offset=filters.offset,
            limit=filters.limit,
            total=total,
        )

    @staticmethod
    async def get_by_number(
        session: AsyncSession, oks_number: int, snapshot_id: int | None = None
    ) -> ProjectRead:
        snapshot = await SnapshotService.resolve(session, snapshot_id)
        report = await ProjectDAO.get_by_number(session, snapshot.id, oks_number)
        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Объект отсутствует в выбранном снимке",
            )
        return ProjectRead.from_report(report)
