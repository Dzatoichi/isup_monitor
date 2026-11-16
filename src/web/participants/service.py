from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.web.projects.dao import ProjectDAO
from src.web.snapshots.schemas import SnapshotRead
from src.web.snapshots.service import SnapshotService

from .participants_dao import ParticipantDAO
from .schemas import ParticipantRead, ProjectParticipantsRead


class ParticipantService:
    @staticmethod
    async def get_for_project(
        session: AsyncSession, oks_number: int, snapshot_id: int | None, *, show_contacts: bool = False
    ) -> ProjectParticipantsRead:
        snapshot = await SnapshotService.resolve(session, snapshot_id)
        if await ProjectDAO.get_by_number(session, snapshot.id, oks_number) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Объект отсутствует в выбранном снимке",
            )
        rows = await ParticipantDAO.get_for_project(session, snapshot.id, oks_number)
        organizations = await ParticipantDAO.get_organizations(session, snapshot.id, oks_number)
        items = []
        for row in rows:
            org = organizations.get(row.organization_external_id)
            items.append(ParticipantRead(
                external_id=row.external_id,
                organization_external_id=row.organization_external_id,
                organization=org.name if org else None,
                organization_role=org.role if org else None,
                organization_inn=org.inn if org else None,
                full_name=row.full_name,
                position=row.position,
                role=row.role,
                signed=row.signed,
                email=row.email if show_contacts else None,
                phone=row.phone if show_contacts else None,
            ))
        return ProjectParticipantsRead(
            snapshot=SnapshotRead.model_validate(snapshot), oks_number=oks_number, items=items
        )
