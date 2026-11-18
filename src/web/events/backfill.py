"""Восстанавливает журнал из сохранённых снимков, не меняя исторические показатели."""
import argparse
from sqlalchemy import select, text
from src.shared.database import create_ingestion_sessions
from src.web.snapshots.models import Snapshot
from src.web.events.dao import EventDAO
from src.web.assignments import models as assignment_models
from src.web.regulations import models as regulation_models


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-id", type=int)
    args = parser.parse_args()
    sessions = create_ingestion_sessions()
    with sessions.begin() as session:
        # Повторный запуск команды не создаёт дубли.
        session.execute(text("SELECT pg_advisory_xact_lock(3765005)"))
        statement = select(Snapshot.id).where(Snapshot.status.in_(("ready", "partial"))).order_by(Snapshot.exported_on, Snapshot.id)
        if args.snapshot_id is not None:
            statement = statement.where(Snapshot.id == args.snapshot_id)
        for identifier in session.scalars(statement).all():
            EventDAO.capture(session, identifier)
    print("Журнал событий обновлён")


if __name__ == "__main__":
    main()
