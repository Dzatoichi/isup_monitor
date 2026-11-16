from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from src.web.auth.dependencies import Admin
from src.web.auth.router import read_protected_form
from src.web.auth.service import csrf_token
from src.web.dependencies import DatabaseSession
from src.web.views import templates

from .dao import UserDAO
from .models import ROLES, SCOPED_ROLES
from .service import UserService


router = APIRouter(prefix="/admin/users", include_in_schema=False)


async def users_page(request, session, admin, error=None):
    users = await UserDAO.get_all(session)
    assignments = {
        user.id: sorted(await UserDAO.get_assignments(session, user.id))
        for user in users if user.role in SCOPED_ROLES
    }
    return templates.TemplateResponse(request, "users.html", {
        "user": admin, "users": users, "assignments": assignments, "roles": ROLES,
        "csrf": csrf_token(request), "error": error,
    }, status_code=400 if error else 200)


@router.get("")
async def list_users(request: Request, session: DatabaseSession, admin: Admin):
    return await users_page(request, session, admin)


@router.post("/{user_id}")
async def update_user(request: Request, session: DatabaseSession, admin: Admin, user_id: int):
    form = await read_protected_form(request)
    try:
        await UserService.set_access(session, admin, user_id, form.get("role"), form.get("assignments", ""))
    except ValueError as error:
        return await users_page(request, session, admin, str(error))
    return RedirectResponse("/admin/users", status_code=303)
