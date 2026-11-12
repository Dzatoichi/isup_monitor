"""Чтение состава команд из ответа, загружаемого модулем заказчика."""

import re
import sys
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError


MEMBERS_PATH = re.compile(r"/api/project-service/organizations/members/([0-9a-fA-F]{24})/?$")
PARTICIPANT_CARD = '.user-info-wrapper, [data-testid="userInfoCard"], .MuiCardHeader-root:has(.userInfoCardTitle)'


def summarize_teams(rows):
    """Считает организации, команды и уникальных людей по идентификаторам."""
    if not isinstance(rows, list):
        raise ValueError("Ответ ЭДО не содержит списка организаций")

    teams = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("В ответе ЭДО запись организации имеет неожиданный формат")
        organization = row.get("organization") or {}
        organization_id = row.get("organizationId") or organization.get("id") or organization.get("_id")
        user_ids = row.get("userIds")
        member_users = row.get("memberUsers")
        if not organization_id or not (isinstance(user_ids, list) or isinstance(member_users, list)):
            raise ValueError("В ответе ЭДО не удалось выделить организацию или состав команды")

        members = teams.setdefault(organization_id, set())
        if isinstance(user_ids, list):
            members.update(user_id for user_id in user_ids if isinstance(user_id, str) and user_id)
        for member in member_users if isinstance(member_users, list) else []:
            user_id = member.get("userId") if isinstance(member, dict) else None
            if not user_id:
                raise ValueError("В ответе ЭДО не удалось выделить идентификатор участника")
            members.add(user_id)

    people = set().union(*teams.values())
    return {
        "edo_organization_count": len(teams),
        "organizations_without_team": sum(not members for members in teams.values()),
        "person_count": len(people),
        "unsigned_count": None if people else 0,
    }


def read_unsigned_from_cards(frame, organizations, person_count, *, signatures=None):
    """Считает подписи по карточкам участников, открытым через меню ЭДО."""
    names = {}
    emails = {}
    for organization in organizations:
        for user in organization.get("users") or []:
            if user.get("id") and user.get("fullName"):
                names[user["id"]] = user["fullName"].casefold().split()
                email = (user.get("emailAddress") or "").strip().casefold()
                if email:
                    emails.setdefault(email, set()).add(user["id"])
    if len(names) != person_count:
        raise ValueError(
            f"ЭДО вернуло ФИО для {len(names)} из {person_count} участников"
        )

    cards = frame.locator(PARTICIPANT_CARD).filter(visible=True)
    try:
        cards.first.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeoutError:
        # Список может открыться со свёрнутыми организациями.
        pass
    if signatures is None:
        signatures = {}

    def remember_visible_cards():
        # В новой разметке подпись внутри карточки, в старой — рядом с её заголовком.
        for name, email, signed in cards.evaluate_all("""(cards, selector) => cards.flatMap(card => {
            const row = card.matches('.user-info-wrapper') ? card : card.parentElement;
            if (row !== card && (card.closest('.user-info-wrapper') ||
                row.querySelectorAll(selector).length !== 1)) return [];
            return [[card.querySelector('.user-info-content-title, .userInfoCardTitle')?.innerText || '',
                     card.querySelector('a[href^="mailto:"]')?.getAttribute('href').slice(7) || '',
                     Boolean(row.querySelector('.signer_signed'))]];
        })""", PARTICIPANT_CARD):
            words = name.casefold().split()
            matches = list(emails.get(email.strip().casefold(), ()))
            if len(matches) != 1 and words:
                matches = [
                    user_id for user_id, full_name in names.items()
                    if full_name[:len(words)] == words
                ]
            if len(matches) == 1:
                signatures[matches[0]] = signatures.get(matches[0], False) or signed

    remember_visible_cards()
    for organization in organizations:
        if len(signatures) == person_count:
            break
        users = organization.get("users") or []
        if all(user.get("id") in signatures for user in users):
            continue
        info = organization.get("organization") or {}
        for name in dict.fromkeys((info.get("shortName"), info.get("name"))):
            if not name:
                continue
            label = frame.get_by_text(name, exact=True).filter(visible=True)
            if label.count() == 1:
                expander = label.locator('xpath=ancestor-or-self::*[@aria-expanded][1]')
                if expander.count() == 1:
                    if expander.get_attribute("aria-expanded") == "false":
                        expander.click(timeout=3000)
                else:
                    label.click(timeout=3000)
                for _ in range(10):
                    remember_visible_cards()
                    if all(user.get("id") in signatures for user in users):
                        break
                    frame.wait_for_timeout(300)
                remember_visible_cards()
                break

    if len(signatures) == person_count:
        return person_count - sum(signatures.values())
    raise ValueError(
        f"сопоставлено карточек {len(signatures)} из {person_count}, "
        f"на открытом экране видно {cards.count()}"
    )


def open_participants_frame(module_frame, project_id):
    """Открывает раздел «Участники» из меню ⚏ во встроенном окне ЭДО."""
    for _ in range(30):
        # Ищем меню в том же модуле, который загрузил состав команды.
        frames = [module_frame]
        while frames:
            frame = frames.pop(0)
            frames.extend(frame.child_frames)
            menu = frame.locator('[class*="BreadcrumbButton"][tabindex="0"]').filter(
                has_text=re.compile(r"^\s*⚏\s*$"), visible=True
            )
            if menu.count() == 1:
                menu.click(timeout=5000)
                route = f"/projects/{project_id}/participants"
                frame.get_by_role("link", name="Участники", exact=True).and_(
                    frame.locator(f'a[href="{route}"]')
                ).click(timeout=10000)
                frame.wait_for_url(lambda url: urlsplit(url).path.rstrip("/") == route, timeout=15000)
                return frame
        module_frame.wait_for_timeout(500)
    raise ValueError("В модуле заказчика (ЭДО) не найдено меню ⚏ для открытия участников")


def collect_edo_records(organizations, signatures):
    """Сохраняет доступные строки ЭДО и подтверждённые признаки подписи."""
    organization_rows = []
    people = []
    contracts = []
    for row in organizations:
        org = row.get("organization") or {}
        organization_id = row.get("organizationId") or org.get("id") or org.get("_id")
        role = row.get("organizationRole")
        organization_rows.append({
            "source": "edo", "external_id": organization_id,
            "name": org.get("name") or org.get("shortName"),
            "role": role if isinstance(role, str) else None,
            **{key: org.get(key) for key in ("inn", "kpp", "ogrn")},
        })
        users = {user["id"]: user for user in row.get("users") or [] if user.get("id")}
        members = {user["userId"]: user for user in row.get("memberUsers") or []}
        for user_id in dict.fromkeys([*(row.get("userIds") or []), *members]):
            if not user_id:
                continue
            user = users.get(user_id, {})
            people.append({
                "external_id": user_id, "organization_external_id": organization_id,
                "full_name": user.get("fullName"), "position": user.get("position"),
                "role": members.get(user_id, {}).get("projectParticipantRole") or user.get("participantRole"),
                "signed": signatures.get(user_id), "email": user.get("emailAddress"),
                "phone": user.get("phoneNumber"),
            })
        for contract in row.get("contracts") or []:
            if isinstance(contract, dict):
                external_id = contract.get("id") or contract.get("_id")
                payload = contract
            elif isinstance(contract, str):
                external_id = contract
                payload = {"id": contract}
            else:
                continue
            contracts.append({
                "external_id": external_id, "organization_external_id": organization_id, "payload": payload,
            })
    return {"organizations": organization_rows, "people": people, "contracts": contracts}


def read_edo_teams(page, exchange_tab, module_tab):
    """Перехватывает штатный ответ ЭДО при открытии вкладки."""
    def is_members_response(response):
        return response.request.method != "OPTIONS" and bool(
            MEMBERS_PATH.search(urlsplit(response.url).path)
        )

    # ЭДО может грузиться в отдельном окне. Подписываемся до открытия обеих вкладок.
    try:
        with page.context.expect_event("response", predicate=is_members_response, timeout=60000) as pending:
            exchange_tab.click(timeout=45000)
            module_tab.click(timeout=45000)
    except PlaywrightTimeoutError:
        journal_tab = page.get_by_text("Журнал", exact=True).filter(visible=True).first
        if not journal_tab.is_visible() or not module_tab.is_visible():
            raise
        # При повторном открытии журнала и ЭДО встроенная страница загружается заново.
        journal_tab.click(timeout=10000)
        with page.context.expect_event("response", predicate=is_members_response, timeout=25000) as pending:
            module_tab.click(timeout=15000)
    response = pending.value
    if not response.ok:
        raise ValueError(f"Модуль ЭДО вернул HTTP {response.status}")

    project_id = MEMBERS_PATH.search(urlsplit(response.url).path)[1]
    organizations = response.json()
    details = summarize_teams(organizations)
    signatures = {}
    if details["person_count"]:
        try:
            frame = open_participants_frame(response.request.frame, project_id)
            unsigned = read_unsigned_from_cards(
                frame, organizations, details["person_count"], signatures=signatures
            )
        except (PlaywrightError, ValueError) as error:
            print(f"  Не удалось сверить подписи ЭДО: {str(error).splitlines()[0]}", file=sys.stderr)
            details["signatures_error"] = "Не удалось сверить подписи ЭДО"
        else:
            details["unsigned_count"] = unsigned
    details["external_id"] = project_id
    try:
        details.update(collect_edo_records(organizations, signatures))
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        # Ошибка разбора подробных записей не обнуляет уже рассчитанные счётчики.
        details["edo_records_error"] = f"Не удалось разобрать подробные записи ЭДО ({type(error).__name__})"
        print(f"  {details['edo_records_error']}", file=sys.stderr)
    return details
