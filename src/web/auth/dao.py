from datetime import UTC, datetime

from sqlalchemy import delete, select

from src.web.users.models import User

from .models import WebSession


class AuthDAO:
    @staticmethod
    async def get_user(session, token_hash):
        return await session.scalar(
            select(User).join(WebSession, WebSession.user_id == User.id).where(
                WebSession.token_hash == token_hash, WebSession.expires_at > datetime.now(UTC)
            )
        )

    @staticmethod
    async def revoke(session, token_hash):
        await session.execute(delete(WebSession).where(WebSession.token_hash == token_hash))
