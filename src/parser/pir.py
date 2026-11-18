"""Читает ПД/РД из тех же запросов, что и раздел «Документация» модуля ПИР."""
from datetime import datetime
from playwright.async_api import Error as PlaywrightError

from .auth import RegistryOpenError
from .report import parse_date, REPORT_TIMEZONE


DATE_KEYS = {
    "created_on": "createdAt", "approved_on": "approvalDate",
    "expected_approval_on": "expectedApprovalDate",
    "transferred_on": "transferToClientDate", "issued_on": "sendToWorkContractorDate",
}


def read_date(value):
    if value in (None, ""):
        return None
    try:
        day = parse_date(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (ValueError, TypeError, AttributeError):
        day = parse_date(value) if isinstance(value, str) else None
    if day is None:
        raise RegistryOpenError("ПИР вернул некорректную дату документа")
    return day


async def read_pir_documents(request, project_id):
    documents = []
    exported_on = datetime.now(REPORT_TIMEZONE).date()
    for kind, endpoint in (("ПД", "project-documents"), ("РД", "work-documents")):
        page, total = 0, None
        seen = set()
        while True:
            try:
                response = await request(
                    f"/api/project-work-document-service/{endpoint}/projects/page/{project_id}",
                    params={"page": page, "pageSize": 100, "withFiles": "true"},
                    method="POST", payload={"filters": [], "logicalOperator": "AND", "searchValue": "", "sorts": []},
                )
            except PlaywrightError:
                raise RegistryOpenError(f"Не удалось прочитать {kind} из ПИР") from None
            try:
                if not response.ok:
                    raise RegistryOpenError(f"ПИР вернул HTTP {response.status} при чтении {kind}")
                data = await response.json()
            finally:
                await response.dispose()
            if not isinstance(data, dict) or type(data.get("totalSize")) is not int or data["totalSize"] < 0:
                raise RegistryOpenError(f"ПИР вернул некорректный счётчик {kind}")
            if total is None:
                total = data["totalSize"]
            batch = data.get("content")
            if data["totalSize"] != total or not isinstance(batch, list) or data.get("pageNum") != page:
                raise RegistryOpenError(f"Список {kind} изменился во время чтения")
            if len(batch) != min(100, total - len(seen)):
                raise RegistryOpenError(f"Прочитаны не все документы {kind}")
            for item in batch:
                identifier = item.get("id") if isinstance(item, dict) else None
                if not isinstance(identifier, str) or not identifier or identifier in seen:
                    raise RegistryOpenError(f"В списке {kind} отсутствует или повторён ID документа")
                if item.get("projectId") != project_id:
                    raise RegistryOpenError(f"ПИР вернул документ другого проекта")
                seen.add(identifier)
                dates = {key: read_date(item.get(source)) for key, source in DATE_KEYS.items()}
                deadline = dates["expected_approval_on"]
                delay = max(0, ((dates["approved_on"] or exported_on) - deadline).days) if deadline else None
                documents.append({
                    "external_id": identifier, "kind": kind, "cipher": item.get("cipher"),
                    "name": item.get("name"), "section": item.get("sectionName"), "version": item.get("version"),
                    "status": item.get("status"), "remark_count": item.get("remarkCount"), "delay_days": delay,
                    **dates, "source_data": item,
                })
            if len(seen) == total:
                break
            page += 1
    return documents
