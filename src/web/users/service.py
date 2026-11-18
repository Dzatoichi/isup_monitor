from fastapi import HTTPException
from sqlalchemy import select
from src.web.assignments.models import Assignment

from .dao import UserDAO
from .models import ROLES, SCOPED_ROLES


class UserService:
    @staticmethod
    async def project_scope(session, user):
        if user.role in SCOPED_ROLES:
            explicit = await UserDAO.get_assignments(session, user.id)
            column = Assignment.manager_email if user.role == "manager" else Assignment.deputy_email
            assigned = set(await session.scalars(select(Assignment.oks_number).where(column == user.email.lower())))
            return explicit | assigned
        if user.role in {"admin", "leadership", "analyst"}:
            return None
        raise HTTPException(403, "Роль ещё не назначена")

    @staticmethod
    async def check_project(session, user, oks_number):
        scope = await UserService.project_scope(session, user)
        if scope is not None and oks_number not in scope:
            raise HTTPException(404, "Объект недоступен")

    @staticmethod
    async def set_access(session, actor, user_id, role, assignments):
        if role not in ROLES:
            raise ValueError("Выберите роль из списка")
        if actor.id == user_id:
            raise ValueError("Свою роль меняет другой администратор")
        accounts = await UserDAO.lock_accounts(session, actor.id, user_id)
        if actor.id not in accounts or accounts[actor.id].role != "admin":
            raise HTTPException(403, "Требуются права администратора")
        user = accounts.get(user_id)
        if user is None:
            raise ValueError("Пользователь не найден")
        numbers = set()
        if role in SCOPED_ROLES:
            try:
                numbers = {int(item) for item in assignments.replace(",", " ").split()}
            except ValueError as error:
                raise ValueError("Укажите номера ОКС через запятую") from error
            if any(not 0 < number <= 9223372036854775807 for number in numbers):
                raise ValueError("Номер ОКС должен быть положительным")
        await UserDAO.replace_assignments(session, user_id, numbers)
        user.role = role
        await session.commit()
