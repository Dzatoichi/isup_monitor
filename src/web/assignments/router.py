import secrets
from io import BytesIO
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError
from openpyxl.utils.exceptions import InvalidFileException

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from openpyxl import Workbook
from starlette.concurrency import run_in_threadpool

from src.web.auth.dependencies import Admin
from src.web.auth.router import read_protected_form
from src.web.auth.service import csrf_token, SESSION_COOKIE
from src.web.dependencies import DatabaseSession
from src.web.views import templates

from .dao import AssignmentDAO
from .service import AssignmentService, COLUMNS


router = APIRouter(prefix="/admin/assignments", include_in_schema=False)


async def page(request, session, user, error=None):
    return templates.TemplateResponse(request, "assignments.html", {
        "user": user, "csrf": csrf_token(request), "rows": await AssignmentDAO.get_all(session),
        "error": error, "columns": COLUMNS,
    }, status_code=400 if error else 200)


@router.get("")
async def assignments(request: Request, session: DatabaseSession, user: Admin):
    return await page(request, session, user)


@router.get("/template.xlsx")
async def template(user: Admin):
    workbook = Workbook()
    workbook.active.title = "Закрепления"
    workbook.active.append(tuple(COLUMNS))
    output = BytesIO()
    workbook.save(output)
    return Response(output.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="assignments.xlsx"'})


@router.post("")
async def edit(request: Request, session: DatabaseSession, user: Admin):
    form = await read_protected_form(request)
    try:
        number = int(form.get("oks_number", ""))
        if not 0 < number < 2**63:
            raise ValueError("Некорректный номер ОКС")
        values = {key: form.get(key, "").strip() or None for key in COLUMNS.values() if key != "oks_number"}
        for key, value in values.items():
            if value and (len(value) > 500 or key.endswith("_email") and ("@" not in value or " " in value)):
                raise ValueError("Проверьте значения и адреса почты")
            if value and key.endswith("_email"):
                values[key] = value.lower()
        await AssignmentService.save(session, [{"oks_number": number, **values}])
    except ValueError as error:
        return await page(request, session, user, str(error))
    return RedirectResponse("/admin/assignments", 303)


@router.post("/import")
async def import_excel(request: Request, session: DatabaseSession, user: Admin):
    if not request.cookies.get(SESSION_COOKIE) or not secrets.compare_digest(
        request.headers.get("x-csrf-token", "").encode(), csrf_token(request).encode()
    ):
        raise HTTPException(403, "Обновите страницу")
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 5_000_000:
            raise HTTPException(413, "Размер XLSX должен быть до 5 МБ")
    try:
        rows = await run_in_threadpool(AssignmentService.parse_excel, content)
        await AssignmentService.save(session, rows)
    except (ValueError, BadZipFile, KeyError, IndexError, TypeError, ParseError, InvalidFileException) as error:
        raise HTTPException(422, str(error) if isinstance(error, ValueError) else "Не удалось прочитать XLSX") from None
    return {"imported": len(rows)}
