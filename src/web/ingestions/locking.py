"""Одна выгрузка одновременно для одной базы PostgreSQL."""
from contextlib import contextmanager
from sqlalchemy import text


@contextmanager
def ingestion_lock(enabled):
    if not enabled:
        yield
        return
    from src.shared.database import create_ingestion_sessions
    sessions = create_ingestion_sessions()
    engine = sessions.kw["bind"]
    try:
        with engine.connect() as connection:
            acquired = connection.scalar(text("SELECT pg_try_advisory_lock(3765010)"))
            connection.commit()
            if not acquired:
                raise RuntimeError("Уже выполняется другая выгрузка ИСУП")
            try:
                yield
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(3765010)"))
                connection.commit()
    finally:
        engine.dispose()
