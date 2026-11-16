from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from src.web.projects.projects_model import Project

from .models import User, UserProject


class UserDAO:
    @staticmethod
    async def upsert_identity(session, *, yandex_id, email, name):
        statement = insert(User).values(yandex_id=yandex_id, email=email, name=name, role="guest")
        return await session.scalar(statement.on_conflict_do_update(
            index_elements=[User.yandex_id],
            set_={"email": statement.excluded.email, "name": statement.excluded.name},
        ).returning(User))

    @staticmethod
    async def get_all(session):
        return (await session.scalars(select(User).order_by(User.name, User.id))).all()

    @staticmethod
    async def lock_accounts(session, *ids):
        statement = select(User).where(User.id.in_(ids)).order_by(User.id).with_for_update()
        return {user.id: user for user in await session.scalars(
            statement.execution_options(populate_existing=True)
        )}

    @staticmethod
    async def get_assignments(session, user_id):
        return set(await session.scalars(select(UserProject.oks_number).where(UserProject.user_id == user_id)))

    @staticmethod
    async def replace_assignments(session, user_id, numbers):
        existing = set(await session.scalars(select(Project.oks_number).where(Project.oks_number.in_(numbers))))
        if numbers != existing:
            raise ValueError("В реестре нет ОКС № " + ", ".join(map(str, sorted(numbers - existing))))
        await session.execute(delete(UserProject).where(UserProject.user_id == user_id))
        session.add_all(UserProject(user_id=user_id, oks_number=number) for number in sorted(numbers))
