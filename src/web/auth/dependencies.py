from typing import Annotated

from fastapi import Depends, HTTPException, Request

from src.web.dependencies import DatabaseSession
from src.web.users.models import User

from .service import SESSION_COOKIE, AuthService


async def current_user(request: Request, session: DatabaseSession):
    return await AuthService.get_user(session, request.cookies.get(SESSION_COOKIE))


OptionalUser = Annotated[User | None, Depends(current_user)]


async def require_user(user: OptionalUser):
    if user is None:
        raise HTTPException(401, "Войдите через Яндекс ID")
    return user


async def require_reader(user: Annotated[User, Depends(require_user)]):
    if user.role == "guest":
        raise HTTPException(403, "Роль ещё не назначена")
    return user


async def require_admin(user: Annotated[User, Depends(require_user)]):
    if user.role != "admin":
        raise HTTPException(403, "Требуются права администратора")
    return user


Reader = Annotated[User, Depends(require_reader)]
Admin = Annotated[User, Depends(require_admin)]
