import asyncio
import json
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.config import settings
from src.web.users.dao import UserDAO

from .dao import AuthDAO
from .models import WebSession


SESSION_COOKIE = "isup_session"
SESSION_AGE = 8 * 60 * 60


def digest(token):
    return sha256(token.encode()).hexdigest()


def csrf_token(request):
    return digest("csrf:" + request.cookies.get(SESSION_COOKIE, ""))


def yandex_enabled():
    return all((settings.YANDEX_CLIENT_ID, settings.YANDEX_CLIENT_SECRET,
                settings.YANDEX_REDIRECT_URI, settings.YANDEX_CORPORATE_DOMAIN))


def fetch_yandex_identity(code):
    """Обменивает код и читает профиль только у Яндекса."""
    token_request = Request("https://oauth.yandex.ru/token", data=urlencode({
        "grant_type": "authorization_code", "code": code, "client_id": settings.YANDEX_CLIENT_ID,
        "client_secret": settings.YANDEX_CLIENT_SECRET.get_secret_value(),
    }).encode(), method="POST")
    with urlopen(token_request, timeout=10) as response:
        token = json.load(response)["access_token"]
    profile_request = Request("https://login.yandex.ru/info?format=json", headers={
        "Authorization": f"OAuth {token}",
    })
    with urlopen(profile_request, timeout=10) as response:
        return json.load(response)


class AuthService:
    @staticmethod
    async def get_user(session, token):
        return await AuthDAO.get_user(session, digest(token)) if token else None

    @staticmethod
    async def login(session, code, previous_token):
        try:
            profile = await asyncio.to_thread(fetch_yandex_identity, code)
        except (URLError, TimeoutError, ValueError, KeyError, TypeError) as error:
            raise ValueError("Яндекс ID не подтвердил вход. Попробуйте ещё раз.") from error
        if not isinstance(profile, dict):
            raise ValueError("Яндекс ID вернул некорректный профиль.")
        email = str(profile.get("default_email") or "").strip().lower()
        local_part, _, domain = email.rpartition("@")
        domain_allowed = domain == settings.YANDEX_CORPORATE_DOMAIN.strip().lower()
        yandex_id = profile.get("id")
        if not local_part or not domain_allowed or not yandex_id:
            raise ValueError("Войдите под корпоративной учётной записью Яндекс ID.")
        user = await UserDAO.upsert_identity(
            session, yandex_id=str(yandex_id), email=email, name=profile.get("display_name") or email
        )
        # Первый администратор назначается оператором из консоли после первого входа.
        if previous_token:
            await AuthDAO.revoke(session, digest(previous_token))
        token = secrets.token_urlsafe(32)
        session.add(WebSession(
            token_hash=digest(token), user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(seconds=SESSION_AGE),
        ))
        await session.commit()
        return token

    @staticmethod
    async def logout(session, token):
        if token:
            await AuthDAO.revoke(session, digest(token))
            await session.commit()
