"""Назначает первого администратора по ID уже вошедшего пользователя."""

import argparse
import asyncio

from sqlalchemy import select, text

from src.shared.database import db_helper
from src.web.users.models import User


async def bootstrap(user_id):
    async with db_helper.session_factory.begin() as session:
        # Блокировка сериализует параллельные запуски команды и изменения пользователей.
        await session.execute(text("LOCK TABLE web_users IN SHARE ROW EXCLUSIVE MODE"))
        if await session.scalar(select(User.id).where(User.role == "admin").limit(1)):
            raise SystemExit("Администратор уже назначен")
        user = await session.get(User, user_id)
        if user is None:
            raise SystemExit("Пользователь ещё не входил в систему")
        user.role = "admin"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user_id", type=int)
    asyncio.run(bootstrap(parser.parse_args().user_id))


if __name__ == "__main__":
    main()
