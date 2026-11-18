from datetime import date
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from .models import Regulation
from .schemas import TrafficRules


class RegulationDAO:
    @staticmethod
    def applicable(session, day):
        return session.scalar(select(Regulation).where(Regulation.effective_on <= day)
                              .order_by(Regulation.effective_on.desc(), Regulation.id.desc()).limit(1))

    @staticmethod
    def ensure_applicable(session, day):
        regulation = RegulationDAO.applicable(session, day)
        if regulation:
            return regulation
        statement = insert(Regulation).values(
            version="ТЗ v3 (предварительные)", effective_on=date.min, rules=TrafficRules().model_dump()
        ).on_conflict_do_nothing(index_elements=[Regulation.version])
        session.execute(statement)
        return RegulationDAO.applicable(session, day)

    @staticmethod
    async def get_all(session):
        return (await session.scalars(select(Regulation).order_by(Regulation.effective_on.desc(), Regulation.id.desc()))).all()

    @staticmethod
    async def create(session, version, effective_on, rules):
        session.add(Regulation(version=version, effective_on=effective_on, rules=TrafficRules.model_validate(rules).model_dump()))
        await session.commit()
