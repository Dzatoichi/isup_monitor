from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from .models import Assignment


class AssignmentDAO:
    @staticmethod
    async def get_all(session):
        return (await session.scalars(select(Assignment).order_by(Assignment.oks_number))).all()

    @staticmethod
    async def save(session, rows):
        for values in rows:
            statement = insert(Assignment).values(**values)
            await session.execute(statement.on_conflict_do_update(
                index_elements=[Assignment.oks_number],
                set_={name: getattr(statement.excluded, name) for name in values if name != "oks_number"},
            ))
