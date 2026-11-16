import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.config import settings
from src.web.dependencies import DatabaseSession
from src.web.views import templates

from .dependencies import OptionalUser
from .service import SESSION_AGE, SESSION_COOKIE, AuthService, csrf_token, yandex_enabled


router = APIRouter(include_in_schema=False)
STATE_COOKIE = "isup_oauth_state"
CALLBACK_PATH = "/auth/yandex/callback"


def login_page(request, error=None, status_code=200):
    return templates.TemplateResponse(request, "login.html", {
        "enabled": yandex_enabled(), "error": error,
    }, status_code=status_code)


@router.get("/login")
async def login(request: Request, user: OptionalUser):
    if user:
        return RedirectResponse("/", status_code=303)
    return login_page(request)


@router.get("/auth/yandex")
async def start_yandex(request: Request):
    if not yandex_enabled():
        return login_page(request, "Вход через Яндекс ID ещё не настроен.", 503)
    state = secrets.token_urlsafe(32)
    response = RedirectResponse("https://oauth.yandex.ru/authorize?" + urlencode({
        "response_type": "code", "client_id": settings.YANDEX_CLIENT_ID,
        "redirect_uri": settings.YANDEX_REDIRECT_URI, "state": state,
        "scope": "login:info login:email",
    }))
    response.set_cookie(STATE_COOKIE, state, max_age=600, path=CALLBACK_PATH,
                        httponly=True, secure=settings.WEB_COOKIE_SECURE, samesite="lax")
    return response


@router.get(CALLBACK_PATH)
async def yandex_callback(request: Request, session: DatabaseSession, code: str = "", state: str = ""):
    expected = request.cookies.get(STATE_COOKIE, "")
    if not yandex_enabled() or not code or not expected or not secrets.compare_digest(state.encode(), expected.encode()):
        response = login_page(request, "Вход не подтверждён. Начните заново.", 400)
    else:
        try:
            token = await AuthService.login(session, code, request.cookies.get(SESSION_COOKIE))
        except ValueError as error:
            response = login_page(request, str(error), 400)
        else:
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_AGE, httponly=True,
                                secure=settings.WEB_COOKIE_SECURE, samesite="lax")
    response.delete_cookie(STATE_COOKIE, path=CALLBACK_PATH)
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


async def read_protected_form(request):
    """Проверяет, что POST-форма отправлена из текущей сессии."""
    from urllib.parse import parse_qs

    if request.headers.get("content-type", "").split(";", 1)[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Ожидается HTML-форма")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16384:
            raise HTTPException(413, "Форма слишком большая")
    try:
        form = parse_qs(body.decode(), keep_blank_values=True, max_num_fields=10)
    except ValueError as error:
        raise HTTPException(400, "Некорректная форма") from error
    if not request.cookies.get(SESSION_COOKIE) or not secrets.compare_digest(
        form.get("csrf", [""])[0].encode(), csrf_token(request).encode()
    ):
        raise HTTPException(403, "Обновите страницу и повторите действие")
    return {key: values[0] for key, values in form.items()}


@router.post("/logout")
async def logout(request: Request, session: DatabaseSession):
    await read_protected_form(request)
    await AuthService.logout(session, request.cookies.get(SESSION_COOKIE))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
