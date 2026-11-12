from typing import Annotated

from fastapi import APIRouter, Query

from src.web.dependencies import DatabaseSession

from .schemas import IngestionRunRead
from .service import IngestionQueryService


router = APIRouter(prefix="/ingestions", tags=["Выгрузки"])


@router.get("", response_model=list[IngestionRunRead])
async def get_ingestions(
    session: DatabaseSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[IngestionRunRead]:
    return await IngestionQueryService.get_all(session, offset=offset, limit=limit)
