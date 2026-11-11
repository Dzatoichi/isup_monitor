from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import settings


class Base(DeclarativeBase):
    pass


class DatabaseHelper:
    def __init__(self):
        self.engine = create_async_engine(
            url = settings.CONNECT_ASYNC(),
            echo = False,
        )
        self.session_factory = async_sessionmaker(
            bind = self.engine,
            expire_on_commit = False,
        )

    async def session_getter(
            self,
        ) -> AsyncGenerator[AsyncSession]:
        async with self.session_factory() as session:
            yield session


db_helper = DatabaseHelper()
