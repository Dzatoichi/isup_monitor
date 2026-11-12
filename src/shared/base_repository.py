from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository[
    ModelType,
    ]:

    def __init__(
            self, 
            model: type[ModelType],
        ) -> None:
        self.model = model

    async def create(
            self,
            session: AsyncSession,
            payload: dict[str, Any],
    ) -> ModelType | None:
        """
        Создание записи
        """
        obj = self.model(**payload)

        session.add(obj)
        await session.flush()

        return obj

    async def get_by_id(
            self,
            session: AsyncSession,
            obj_id: int,
    ) -> ModelType | None:

        obj = await session.get(
            self.model,
            obj_id
            )

        return obj


    async def get_all(
            self,
            session: AsyncSession,
    ) -> list[ModelType] | None:

        stmt = select(self.model)

        objs = await session.execute(stmt)

        return list(objs.scalars().all())