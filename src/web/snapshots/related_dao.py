from sqlalchemy import delete
from sqlalchemy.orm import Session

from src.web.contracts.models import ProjectContractSnapshot
from src.web.documents.models import DocumentOperationSnapshot
from src.web.organizations.models import ProjectOrganizationSnapshot
from src.web.participants.models import ProjectParticipantSnapshot


class RelatedSnapshotDAO:
    """Заменяет прочитанные разделы одного объекта в текущем снимке."""

    @staticmethod
    def save(session: Session, snapshot_id: int, project_id: int, record: dict) -> None:
        sections = (
            (ProjectOrganizationSnapshot, record.get("organizations")),
            (ProjectParticipantSnapshot, record.get("people")),
            (ProjectContractSnapshot, record.get("contracts")),
            (DocumentOperationSnapshot, record.get("documents")),
        )
        for model, rows in sections:
            if rows is None:
                continue
            session.execute(delete(model).where(
                model.snapshot_id == snapshot_id, model.project_id == project_id,
            ))
            session.add_all([
                model(snapshot_id=snapshot_id, project_id=project_id, row_number=index, **row)
                for index, row in enumerate(rows, start=1)
            ])
