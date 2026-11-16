"""Чтение реестра ИСУП через HTTP-клиент Playwright."""

import asyncio
import os
import re
from html.parser import HTMLParser
from urllib.parse import urlencode

from playwright.async_api import Error as PlaywrightError

from .auth import RegistryOpenError
from .edo import collect_edo_records, summarize_teams
from .report import parse_date, parse_passport


REGISTRY_PATH = "/datawarehouseservice/query/5427"
DOCUMENTS_PATH = "/datawarehouseservice/query/786"
FINANCE_PATH = "/datawarehouseservice/query/9235"
SCHEDULE_PATH = "/datawarehouseservice/query/7992"

EDO_BASE_URL = "https://uks24-gis.exonproject.ru/"
EDO_TOKEN_PATH = "/registryservice/plugins/execute/GisTokenQuery?" + urlencode({
    "baseUrl": EDO_BASE_URL, "configurationItemId": 236,
})


class FinanceText(HTMLParser):
    """Собирает подписи и значения из HTML, возвращённого ИСУП."""

    def __init__(self):
        super().__init__()
        self.lines = []

    def handle_data(self, data):
        value = " ".join(data.split())
        if value:
            self.lines.append(value)


async def read_http_registry(playwright, *, limit=None, on_project=None, concurrency=1):
    """Авторизуется и читает страницы реестра без запуска браузера."""
    base_url = os.environ["ISUP_URL"].rstrip("/")
    client = await playwright.request.new_context(
        base_url=base_url,
        extra_http_headers={"Accept": "application/json", "Origin": base_url, "Referer": base_url + "/"},
        timeout=30000,
    )
    auth = None
    auth_lock = asyncio.Lock()
    refresh_error = None
    edo_token = os.environ.get("ISUP_EDO_TOKEN", "").strip()
    edo_client = None
    edo_lock = asyncio.Lock()

    async def get_edo_token(rejected=None):
        nonlocal edo_token
        async with edo_lock:
            # Остальные задачи используют токен, обновлённый первой задачей после 401.
            if not edo_token or edo_token == rejected:
                result = await request("GET", EDO_TOKEN_PATH)
                token = result.get("access_token") if isinstance(result, dict) else None
                if not isinstance(token, str) or not token.strip():
                    raise RegistryOpenError("ИСУП не вернула токен ЭДО")
                edo_token = token.strip()
            return edo_token

    async def get_edo_members(path, params):
        token = await get_edo_token()
        for attempt in range(2):
            response = await edo_client.get(
                path, params=params, headers={"Authorization": f"Bearer {token}"}, max_redirects=0
            )
            if response.status != 401 or attempt == 1:
                return response
            await response.dispose()
            token = await get_edo_token(rejected=token)

    async def request(method, path, payload=None, *, authenticated=True):
        # Повторяем временные ошибки только для запросов чтения.
        read_queries = (REGISTRY_PATH, DOCUMENTS_PATH, FINANCE_PATH, SCHEDULE_PATH)
        attempts = 3 if method == "GET" or path in read_queries else 1
        attempt = 0
        refreshed = False
        while True:
            session = auth if authenticated else None
            headers = {"Authorization": session["token"]} if session is not None else {}
            unauthorized = False
            try:
                response = await client.fetch(path, method=method, data=payload, headers=headers, max_redirects=0)
            except PlaywrightError as error:
                if attempt + 1 == attempts:
                    raise RegistryOpenError(f"Не удалось выполнить HTTP-запрос {path}") from error
                delay = 2 ** attempt
            else:
                try:
                    if response.status == 401 and session is not None and not refreshed:
                        unauthorized = True
                    elif response.status in (429, 502, 503, 504) and attempt + 1 < attempts:
                        retry_after = response.headers.get("retry-after", "")
                        delay = max(2 ** attempt, int(retry_after)) if retry_after.isdecimal() else 2 ** attempt
                    elif not response.ok:
                        raise RegistryOpenError(f"ИСУП вернула HTTP {response.status} для {path}")
                    else:
                        return await response.json()
                except ValueError as error:
                    raise RegistryOpenError(f"ИСУП вернула ответ в неожиданном формате для {path}") from error
                finally:
                    await response.dispose()
            if unauthorized:
                await refresh_auth(session)
                refreshed = True
                continue
            await asyncio.sleep(delay)
            attempt += 1

    async def post(path, payload):
        return await request("POST", path, payload)

    async def authenticate():
        credentials = {
            "login": os.environ["ISUP_LOGIN"],
            "password": os.environ["ISUP_PASSWORD"],
            "ldap": False,
        }
        login = await request("POST", "/defaultauthentication/auth/login", credentials, authenticated=False)
        if not isinstance(login, dict) or not login.get("uuid"):
            raise RegistryOpenError("ИСУП не вернула идентификатор входа")
        result = await request("POST", "/accesseditor/login/authorize", {"uuid": login["uuid"]}, authenticated=False)
        if not isinstance(result, dict) or not result.get("token") or not result.get("id"):
            raise RegistryOpenError("ИСУП не создала HTTP-сессию")
        if result.get("need_change_password"):
            raise RegistryOpenError("ИСУП требует сменить пароль")
        return result

    async def refresh_auth(expired_session):
        nonlocal auth, refresh_error
        async with auth_lock:
            # Пока запрос ждал блокировку, другая задача могла уже обновить сессию.
            if auth is not expired_session:
                return
            if refresh_error is not None:
                raise RegistryOpenError(refresh_error)
            try:
                renewed = await authenticate()
                if renewed["id"] != expired_session["id"]:
                    raise RegistryOpenError("ИСУП вернула другую учётную запись")
            except RegistryOpenError as error:
                refresh_error = f"Не удалось повторно войти в ИСУП: {error}"
                raise RegistryOpenError(refresh_error) from error
            auth = renewed

    try:
        auth = await authenticate()
        query = {
            "where": {"and": [{"eq": {"archive_oks": False}}, {"eq": {"check_ons": False}}]},
            "query_parameters": {"id_user_from_card": auth["id"]},
        }
        counter = await post(REGISTRY_PATH, {"*": {"func": "count"}, **query})
        try:
            count = int(counter[0]["count"])
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise RegistryOpenError("ИСУП вернула некорректный счётчик ОКС") from error
        if count < 0:
            raise RegistryOpenError("ИСУП вернула отрицательный счётчик ОКС")
        target = count if limit is None else min(limit, count)
        rows = []
        ids = set()
        for offset in range(0, target, 100):
            page_size = min(100, target - offset)
            batch = await post(REGISTRY_PATH, {"limit": page_size, "offset": offset, **query})
            if not isinstance(batch, list) or len(batch) != page_size:
                raise RegistryOpenError(f"ИСУП вернула неполную страницу ОКС со смещением {offset}")
            for row in batch:
                number = row.get("id_oks") if isinstance(row, dict) else None
                if type(number) is not int or number <= 0 or number in ids:
                    raise RegistryOpenError("ИСУП вернула отсутствующий, некорректный или повторный номер ОКС")
                ids.add(number)
                rows.append(row)
        if on_project is not None:
            # Токен ЭДО передаётся только отдельному клиенту на подтверждённом домене.
            edo_client = await playwright.request.new_context(
                base_url=EDO_BASE_URL, extra_http_headers={"Accept": "application/json"}, timeout=30000,
            )
            await read_projects(rows, request, on_project, concurrency, get_edo_members)
        return rows
    finally:
        try:
            if edo_client is not None:
                await edo_client.dispose()
        finally:
            await client.dispose()


async def read_projects(rows, request, on_project, concurrency, get_edo_members):
    """Запускает ограниченное число обработчиков на общей HTTP-сессии."""
    pending_rows = iter(rows)

    async def worker():
        for row in pending_rows:
            project = await read_project(request, row, get_edo_members)
            on_project(project)

    workers = [asyncio.create_task(worker()) for _ in range(min(concurrency, len(rows)))]
    try:
        await asyncio.gather(*workers)
    finally:
        # При остановке или ошибке записи закрываем задачи до закрытия HTTP-сессии.
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


async def read_project(request, row, get_edo_members):
    """Собирает подтверждённые поля ОКС в формате основной выгрузки."""
    number = row["id_oks"]
    project = {
        "oks_number": number,
        "name": row.get("full_name_oks") or row.get("full_name_oks_1"),
        "stage": row.get("name_stadia"),
        "state": row.get("name_state_2"),
        "progress": row.get("progress_oks_2"),
        "customer": row.get("customer"),
    }
    registry = row.get("id_registry")
    if type(registry) is not int or registry <= 0:
        project["passport_error"] = "ИСУП не указала реестр карточки"
        return project
    try:
        card = await request("GET", f"/registryservice/registry/{registry}/card/{number}")
    except RegistryOpenError as error:
        project["passport_error"] = str(error)
        return project
    if not isinstance(card, dict) or card.get("id") != number:
        project["passport_error"] = "ИСУП вернула данные другой карточки"
        return project
    for key, attribute in (
        ("pir_plan_start", "attr_174_"),
        ("pir_plan_end", "attr_175_"),
        ("smr_plan_start", "attr_4177_"),
        ("smr_plan_end", "attr_4178_"),
        ("pir_actual_start", "attr_4945_"),
        ("external_id", "attr_6636_"),
    ):
        value = card.get(attribute)
        if isinstance(value, str) and value.strip():
            project[key] = value

    try:
        project.update(await read_http_finance(request, card))
    except RegistryOpenError as error:
        project["finance_error"] = str(error)

    try:
        project.update(await read_http_schedule(request, card.get("attr_169_")))
    except RegistryOpenError as error:
        project["schedule_error"] = str(error)

    try:
        project.update(await read_http_edo(get_edo_members, project.get("external_id")))
    except (RegistryOpenError, ValueError, TypeError, KeyError, AttributeError) as error:
        project["edo_error"] = (
            str(error) if isinstance(error, RegistryOpenError) else "Не удалось разобрать ответ ЭДО"
        )

    try:
        documents = await read_http_documents(request, card.get("attr_169_"))
    except RegistryOpenError as error:
        project["documents_error"] = str(error)
    else:
        project["documents"] = documents
        project["operation_dates"] = [document["document_on"] for document in documents]
    return project


async def read_http_schedule(request, object_id):
    """Читает план и факт из таблицы «Проектные сроки»."""
    if not object_id:
        raise RegistryOpenError("В карточке ОКС нет идентификатора для проектных сроков")
    rows = await request("POST", SCHEDULE_PATH, {"query_parameters": {"oks_id": object_id}})
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise RegistryOpenError("ИСУП вернула неожиданный ответ по проектным срокам")
    row = rows[0]
    dates = {}
    # В таблице ИСУП этап 3 соответствует ПИР, этап 6 — СМР.
    for stage, stage_id in (("pir", 3), ("smr", 6)):
        for mode, suffix in (("plan", "basic"), ("actual", "actual")):
            for edge in ("start", "end"):
                key = f"time_{edge}_{stage_id}_{suffix}"
                value = row.get(key)
                day = parse_date(value.strip()) if isinstance(value, str) else None
                if value is not None and day is None and (not isinstance(value, str) or value.strip()):
                    raise RegistryOpenError(f"ИСУП вернула некорректную дату в поле {key}")
                dates[f"{stage}_{mode}_{edge}"] = day
    if not any(key.startswith(("time_start_", "time_end_")) for key in row):
        raise RegistryOpenError("В ответе ИСУП нет полей проектных сроков")
    return dates


async def read_http_finance(request, card):
    """Читает финансовые данные из того же запроса, что и паспорт объекта."""
    object_id = card.get("attr_169_")
    if not object_id:
        raise RegistryOpenError("В карточке ОКС нет идентификатора для финансирования")
    parameters = {"id_oks_from_card": object_id}
    if card.get("attr_9383_") is not None:
        parameters["is_in_fin_table"] = card["attr_9383_"]
    rows = await request("POST", FINANCE_PATH, {"query_parameters": parameters})
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise RegistryOpenError("ИСУП вернула неожиданный ответ по финансированию")
    html = rows[0].get("column_1")
    if not isinstance(html, str):
        raise RegistryOpenError("В ответе ИСУП нет HTML блока финансирования")
    parser = FinanceText()
    parser.feed(html)
    parser.close()
    fields = parse_passport("\n".join(parser.lines))
    if not fields:
        raise RegistryOpenError("В блоке финансирования ИСУП не найдены суммы")
    return fields


async def read_http_documents(request, object_id):
    """Читает документы по идентификатору привязки из карточки ОКС."""
    if not object_id:
        raise RegistryOpenError("В карточке ОКС нет идентификатора для документации")
    query = {"query_parameters": {"oks_id": object_id, "is_deleted_param": False}}
    counter = await request("POST", DOCUMENTS_PATH, {"*": {"func": "count"}, **query})
    try:
        count = int(counter[0]["count"])
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise RegistryOpenError("ИСУП вернула некорректный счётчик документов") from error
    if count < 0:
        raise RegistryOpenError("ИСУП вернула отрицательный счётчик документов")

    documents = []
    record_ids = set()
    for offset in range(0, count, 100):
        page_size = min(100, count - offset)
        batch = await request("POST", DOCUMENTS_PATH, {"limit": page_size, "offset": offset, **query})
        if not isinstance(batch, list) or len(batch) != page_size:
            raise RegistryOpenError(f"ИСУП вернула неполную страницу документов со смещением {offset}")
        for row in batch:
            record_id = row.get("record_id") if isinstance(row, dict) else None
            if type(record_id) not in (int, str) or record_id == "" or record_id in record_ids:
                raise RegistryOpenError("ИСУП вернула документ без идентификатора или повторила его")
            record_ids.add(record_id)
            value = row.get("doc_date")
            document_on = parse_date(value) if isinstance(value, str) else None
            documents.append({
                "document_on": document_on,
                "document_number": row.get("doc_num"),
                "name": row.get("doc_name"),
                "document_type": row.get("type_name"),
                "status": row.get("status_name"),
            })
    return documents

async def read_http_edo(get_edo_members, project_id):
    """Читает организации и подписи приказов из ответа модуля заказчика."""
    if not isinstance(project_id, str) or not re.fullmatch(r"[0-9a-fA-F]{24}", project_id):
        raise RegistryOpenError("В карточке нет идентификатора проекта ЭДО")
    try:
        response = await get_edo_members(
            f"/api/project-service/organizations/members/{project_id}",
            params={"excludeCurrentUser": "false", "needBusStatus": "true",
                    "statusFilter": "ACTIVE", "userEnabled": "true"},
        )
    except PlaywrightError:
        raise RegistryOpenError("Не удалось выполнить запрос состава команд ЭДО") from None
    try:
        if not response.ok:
            raise RegistryOpenError(f"Запрос состава команд ЭДО вернул HTTP {response.status}")
        rows = await response.json()
    finally:
        await response.dispose()
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RegistryOpenError("ЭДО не вернуло список организаций")
    visible_rows = []
    signatures = {}
    for row in rows:
        users = row.get("users")
        if users is None and not (row.get("userIds") or row.get("memberUsers")):
            users = []
        if not isinstance(users, list):
            raise RegistryOpenError("ЭДО не вернуло список профилей организации")
        visible_ids = []
        for user in users:
            user_id = user["id"]
            if not isinstance(user_id, str) or not user_id:
                raise RegistryOpenError("В профиле участника ЭДО нет идентификатора")
            visible_ids.append(user_id)
            status = user.get("signStatus")
            # В предоставленной выгрузке у участника без подписи поле отсутствует.
            if status in (None, "SIGNED"):
                signatures[user_id] = signatures.get(user_id, False) or status == "SIGNED"
        # Интерфейс показывает профили из users. Из memberUsers берём только их роли.
        user_ids = set(visible_ids)
        visible_rows.append({
            **row, "users": users, "userIds": visible_ids,
            "memberUsers": [member for member in row.get("memberUsers") or [] if member["userId"] in user_ids],
        })
    result = summarize_teams(visible_rows)
    records = collect_edo_records(visible_rows, signatures)
    people = records["people"]
    signed_by_id = {person["external_id"]: person["signed"] for person in people}
    if len(signed_by_id) == result["person_count"] and all(value is not None for value in signed_by_id.values()):
        result["unsigned_count"] = sum(value is False for value in signed_by_id.values())
    else:
        result["signatures_error"] = "ЭДО вернуло неполные данные о подписях"
    result["organizations"] = records["organizations"]
    result["people"] = people
    return result
