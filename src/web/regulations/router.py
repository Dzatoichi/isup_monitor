from datetime import date
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.web.auth.dependencies import Admin
from src.web.auth.router import read_protected_form
from src.web.auth.service import csrf_token
from src.web.dependencies import DatabaseSession
from src.web.views import templates
from .dao import RegulationDAO
from .schemas import TrafficRules, FIELD_LABELS
from src.web.analytics.monitoring import ROLE_LABELS


router = APIRouter(prefix="/admin/regulations", include_in_schema=False)


async def page(request, session, user, error=None):
    versions = await RegulationDAO.get_all(session)
    current = next((item for item in versions if item.effective_on <= date.today()), None)
    return templates.TemplateResponse(request, "regulations.html", {
        "user": user, "csrf": csrf_token(request), "rules": TrafficRules.model_validate(current.rules if current else {}).model_dump(),
        "versions": versions, "error": error,
        "field_labels": FIELD_LABELS,
        "role_labels": ROLE_LABELS,
    }, status_code=400 if error else 200)


@router.get("")
async def regulations(request: Request, session: DatabaseSession, user: Admin):
    return await page(request, session, user)


@router.post("")
async def create(request: Request, session: DatabaseSession, user: Admin):
    form = await read_protected_form(request)
    try:
        version = form.get("version", "").strip()
        if not version or len(version) > 120:
            raise ValueError("Введите название версии до 120 символов")
        effective_on = date.fromisoformat(form.get("effective_on", ""))
        rules = TrafficRules.model_validate({
            key: form[key] for key in (
                "exchange_yellow_days", "exchange_red_days", "overdue_red_days",
                "unsigned_red_percent", "stagnation_days",
            )
        }).model_dump()
        by_label = {label.casefold(): key for key, label in FIELD_LABELS.items()}
        required = [label.strip().casefold() for label in form.get("required_fields", "").split(",") if label.strip()]
        if not required or any(label not in by_label for label in required):
            raise ValueError("Неизвестное обязательное поле")
        rules["required_fields"] = list(dict.fromkeys(by_label[label] for label in required))
        roles_by_label = {label.casefold(): key for key, label in ROLE_LABELS.items()}
        def values(key):
            return [item.strip() for item in form.get(key, "").split(",") if item.strip()]
        rules["required_roles_by_stage"] = {
            stage: [roles_by_label[item.casefold()] for item in values(key)]
            for stage, key in (("ПИР", "roles_pir"), ("СМР", "roles_smr"))
        }
        rules["required_documents_by_stage"] = {
            stage: values(key) for stage, key in (("ПИР", "documents_pir"), ("СМР", "documents_smr"))
        }
        rules["gsn_required_stages"] = values("gsn_required_stages")
        await RegulationDAO.create(session, version, effective_on, rules)
    except IntegrityError:
        await session.rollback()
        return await page(request, session, user, "Название версии уже используется")
    except (ValueError, KeyError, ValidationError):
        return await page(request, session, user, "Проверьте дату, пороги, названия ролей и документов. Красный порог обмена должен быть больше жёлтого.")
    return RedirectResponse("/admin/regulations", 303)
