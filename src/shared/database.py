from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.config import settings


class Base(DeclarativeBase):
    pass


class DatabaseHelper:
    """Хранит асинхронное подключение и фабрику сессий для обработчиков FastAPI."""
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
        """Выдаёт отдельную сессию БД на запрос и закрывает её после завершения обработки."""
        async with self.session_factory() as session:
            yield session


db_helper = DatabaseHelper()


def create_ingestion_sessions():
    """Создаёт синхронные сессии для записи результатов парсера вне цикла веб-запросов."""
    engine = create_engine(settings.CONNECT_ASYNC(), pool_pre_ping=True)
    return sessionmaker(engine)
