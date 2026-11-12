from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.database import db_helper


DatabaseSession = Annotated[AsyncSession, Depends(db_helper.session_getter)]
