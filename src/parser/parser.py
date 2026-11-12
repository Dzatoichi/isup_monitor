"""Обход карточек ИСУП, сбор организаций и запуск выгрузки."""

import argparse
import json
import re
import signal
import sys
from contextlib import redirect_stdout
from datetime import datetime
from itertools import count
from time import monotonic

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from .auth import (
    VISIBLE_PROJECT_NAME,
    advance_registry_page,
    collect_current_page,
    find_projects_grid,
    find_scrollable,
    login,
    open_projects_registry,
    registry_page_number,
)
from .report import REPORT_TIMEZONE, make_object_report, parse_passport
from .documents import read_document_dates
from .edo import read_edo_teams


PROJECT_NUMBER = re.compile(r"^[ \t]*ОКС\s*№\s*(\d+)", re.MULTILINE)
PARTICIPANTS_PANEL = ".contract_child_list .a-list:visible"


def parse_participant(text):
    """Разбирает карточку организации на роль, название и реквизиты."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError("В строке участника не удалось выделить роль и организацию")
    role, *details = lines
    fields = {"ИНН": "inn", "КПП": "kpp", "ОГРН": "ogrn"}
    participant = dict.fromkeys(fields.values())
    organization = []
    current_field = None

    # Значение реквизита бывает на одной строке с меткой или под ней.
    for line in details:
        label = re.fullmatch(r"(ИНН|КПП|ОГРН)\s*:?\s*(\d+)?", line)
        if label:
            current_field = fields[label[1]]
            participant[current_field] = label[2]
        elif current_field is None:
            organization.append(line)
        elif re.fullmatch(r"\d+", line) and participant[current_field] is None:
            participant[current_field] = line

    if not organization:
        raise ValueError("В строке участника не удалось выделить название организации")

    return {"role": role, "organization": " ".join(organization), **participant}


def read_project_number(page):
    """Ищет номер ОКС в видимом тексте страницы."""
    number = PROJECT_NUMBER.search(page.locator("body").inner_text())
    return number[1] if number else None


def read_participants(page):
    """Читает все видимые записи организаций или подтверждает, что список пуст."""
    panel = page.locator(PARTICIPANTS_PANEL)
    panel.wait_for(state="visible", timeout=60000)
    cells = panel.locator("table:visible, [role=table]:visible").get_by_role("cell")
    populated = cells.filter(has_text=re.compile(r"\S"), visible=True)
    empty = panel.get_by_text(re.compile(r"^(Нет данных|Нет записей|Список пуст)$")).filter(
        visible=True
    )
    populated.or_(empty).first.wait_for(state="visible", timeout=60000)

    # Пустой список возвращаем только по явному сообщению интерфейса.
    if empty.first.is_visible():
        return []

    texts = [text for text in populated.all_inner_texts() if text.strip()]
    if not texts:
        raise ValueError("Список участников виден, но текст строк не прочитан")
    return [parse_participant(text) for text in texts]


def project_cell(grid, project):
    """Находит ячейку объекта по индексу строки и полному названию."""
    index = project["row_index"]
    words = (re.escape(word) for word in project["name"].split())
    name = re.compile(r"^\s*" + r"\s+".join(words) + r"\s*$")
    return grid.locator(
        f'.ag-center-cols-container [role="row"][row-index="{index}"] .name_oks_table'
    ).filter(has_text=name)


def scroll_registry(grid, top):
    """Возвращает таблицу к заданной позиции прокрутки."""
    scrollable = find_scrollable(grid)
    if scrollable is not None:
        scrollable.evaluate("(el, top) => { el.scrollTop = top; }", top)


def restore_registry_page(page, first_project, page_number):
    """Возвращается из карточки на нужную страницу реестра."""
    if not page.locator(VISIBLE_PROJECT_NAME).first.is_visible():
        page.locator("a.back_breadcrumb:visible").click(timeout=15000)
        open_projects_registry(page)

    grid = find_projects_grid(page)
    current_page = registry_page_number(grid)
    # После закрытия карточки ИСУП может сбросить пагинацию.
    for _ in range(current_page, page_number):
        if not advance_registry_page(page, grid):
            break

    if registry_page_number(grid) != page_number:
        raise RuntimeError(f"Не удалось вернуться на страницу {page_number} реестра")

    scroll_registry(grid, 0)
    project_cell(grid, first_project).wait_for(state="visible", timeout=15000)
    return grid


def open_project(cell, management_tab):
    """Открывает карточку и ждёт появления раздела управления проектами."""
    cell.click(timeout=10000)
    try:
        cell.wait_for(state="hidden", timeout=3000)
    except PlaywrightTimeoutError:
        # Если одиночный клик оставил таблицу на экране, пробуем двойной.
        if not management_tab.is_visible():
            cell.dblclick(timeout=10000)
    management_tab.wait_for(state="visible", timeout=60000)
    cell.page.get_by_text("Пожалуйста, подождите...", exact=True).filter(
        visible=True
    ).first.wait_for(state="hidden", timeout=60000)


def read_project_schedule(page, details):
    """Читает начало и окончание ПИР и СМР в режимах «План» и «Факт»."""
    tab = page.locator("div.tab span.label:visible").filter(
        has_text=re.compile(r"^\s*Подробнее об объекте\s*$")
    )
    tab.wait_for(state="visible", timeout=45000)
    active_tab = tab.locator("..").and_(page.locator(".tab.active"))
    if not active_tab.is_visible():
        tab.click(timeout=15000)
    switch = page.locator('[role="switch"]:visible').filter(
        has=page.locator('input[name="switch_plan_fact"]')
    )
    try:
        switch.wait_for(state="visible", timeout=45000)
    except PlaywrightTimeoutError as error:
        if not tab.is_visible():
            raise ValueError("вкладка «Подробнее об объекте» исчезла при загрузке") from error
        passport = page.get_by_text("Паспорт объекта", exact=True).filter(visible=True).first
        if active_tab.is_visible() and passport.is_visible():
            passport.click(timeout=10000)
        tab.click(timeout=15000)
        try:
            switch.wait_for(state="visible", timeout=30000)
        except PlaywrightTimeoutError as retry_error:
            raise ValueError("после повторного открытия вкладки переключатель «План / Факт» не появился") from retry_error
    container = switch.locator("xpath=ancestor::div[contains(@class, 'isup-switch')][1]/..")
    panels = container.locator(":scope > .block").filter(
        has=page.locator('.isup-input-label [data-value="ПИР"]')
    ).filter(
        has=page.locator('.isup-input-label [data-value="СМР"]')
    )
    fact_switch = switch.filter(has=page.locator(".el-switch__label--right.is-active"))
    plan_switch = switch.filter(has=page.locator(".el-switch__label--left.is-active"))
    fact_switch.wait_for(state="visible", timeout=15000)

    panel = panels.filter(visible=True)
    for mode, label, active_switch in (
        ("actual", "Факт", fact_switch),
        ("plan", "План", plan_switch),
    ):
        if mode == "plan":
            # Переключаем один раз, после чтения и сохранения фактических сроков.
            old_panel = panel.element_handle(timeout=10000) if panels.count() > 1 else None
            switch.locator(".el-switch__core").click(timeout=10000)
            active_switch.wait_for(state="visible", timeout=15000)
            if old_panel is not None:
                old_panel.wait_for_element_state("hidden", timeout=15000)

        panel.wait_for(state="visible", timeout=15000)
        panel.locator(".el-loading-mask:visible").first.wait_for(state="hidden", timeout=45000)
        read_stages = r"""panel => {
            const position = (block, property) => {
                // У скрытых блоков Chromium может вернуть calc(…) вместо вычисленного px.
                const value = getComputedStyle(block)[property] || block.style[property];
                return parseFloat(value.replace(/^calc\(/, ''));
            };
            const isVisible = label => label.getClientRects().length > 0;
            const labels = [...panel.querySelectorAll('.isup-input-label [data-value]')]
                .filter(isVisible)
                .filter(label => label.dataset.value && label.dataset.value !== 'Не указано')
                .map(label => [label.dataset.value, position(label.closest('.block'), 'top')]);
            const dates = [...panel.querySelectorAll('.isup-body-main [data-value]')]
                .filter(isVisible)
                .map(label => {
                    const block = label.closest('.block');
                    return [position(block, 'top'), position(block, 'left'), label.dataset.value];
                });
            return Object.fromEntries(labels.filter(([name]) => name === 'ПИР' || name === 'СМР')
                .map(([name, top]) => {
                    // Даты стоят под заголовком стадии: начало слева, окончание справа.
                    const next = Math.min(...labels.map(([, y]) => y).filter(y => y > top));
                    const row = dates.filter(([y]) => y > top && y < next);
                    return [name, [row.find(([, x]) => x < 100)?.[2] ?? null,
                                   row.find(([, x]) => x >= 100)?.[2] ?? null]];
                }));
        }"""
        deadline = monotonic() + 45
        while True:
            stages = panel.evaluate(read_stages)
            if active_switch.is_visible() and {"ПИР", "СМР"} <= stages.keys() and not any(
                value and "{{" in value
                for dates in stages.values() for value in dates
            ):
                break
            if monotonic() >= deadline:
                raise ValueError(f"ИСУП не загрузила даты в режиме «{label}»")
            page.wait_for_timeout(300)
        for stage, key in (("ПИР", "pir"), ("СМР", "smr")):
            start, end = stages.get(stage, (None, None))
            details[f"{key}_{mode}_start"] = start
            details[f"{key}_{mode}_end"] = end


def read_report_sections(page, details):
    """Добавляет сведения из ЭДО и документации независимо друг от друга."""
    def tab(name):
        return page.get_by_text(name, exact=True).filter(visible=True).first

    try:
        details.update(read_edo_teams(
            page, tab("Информационный обмен"), tab("Модуль заказчика (ЭДО)")
        ))
    except (PlaywrightError, ValueError) as error:
        print(f"  Не удалось прочитать команды ЭДО: {str(error).splitlines()[0]}", file=sys.stderr)
        details["edo_error"] = f"Не удалось получить состав команды из ЭДО ({type(error).__name__})"

    try:
        tab("Документация").click(timeout=45000)
        documents = []
        details["operation_dates"] = read_document_dates(page, records=documents)
        details["documents"] = documents
    except (PlaywrightError, AssertionError, ValueError) as error:
        print(f"  Не удалось прочитать даты документов: {str(error).splitlines()[0]}", file=sys.stderr)
        details["documents_error"] = True


def collect_projects_with_participants(page, *, limit=None, report=False, on_project=None):
    """Обходит объекты и возвращает записи вместе с признаком завершения обхода."""
    grid = find_projects_grid(page)
    management_tab = page.locator('div.tab[depth="1"] span.label:visible').filter(
        has_text=re.compile(r"^\s*Управление проектами\s*$")
    )
    participants_tab = page.get_by_text("Управление участниками", exact=True).filter(visible=True)
    results = []

    # Сначала запоминаем строки страницы, чтобы открывать карточки по очереди.
    for page_number in count(1):
        scroll_positions = {}
        try:
            if registry_page_number(grid) != page_number:
                raise RuntimeError("Таблица не перешла на ожидаемую страницу")
            projects = collect_current_page(page, grid, scroll_positions=scroll_positions)
        except (PlaywrightError, RuntimeError, ValueError) as error:
            print(f"Обход прерван на странице {page_number}: {error}", file=sys.stderr)
            return results, False
        for project in projects:
            print(
                f"Страница {page_number}. Объект {len(results) + 1}: {project['name']}",
                file=sys.stderr,
            )
            details = {}
            step = "открытие карточки"
            try:
                scroll_registry(grid, scroll_positions[project["row_index"]])
                open_project(project_cell(grid, project), management_tab)
                details["oks_number"] = read_project_number(page)
                # Паспорт читаем до перехода на вкладку организаций.
                if report:
                    for label, timeout in (
                        ("Состояние объекта", 20000),
                        ("Стоимость объекта (плановая)", 12000),
                    ):
                        field = page.get_by_text(label, exact=True).filter(visible=True).first
                        try:
                            field.wait_for(state="visible", timeout=timeout)
                        except PlaywrightTimeoutError:
                            print(f"  В паспорте не найдено поле «{label}»", file=sys.stderr)
                    details.update(parse_passport(page.locator("body").inner_text()))
                    try:
                        try:
                            read_project_schedule(page, details)
                        except (PlaywrightError, AssertionError, ValueError):
                            if not page.get_by_placeholder("Логин").is_visible():
                                raise
                            print("  ИСУП вернула на вход. Повторно открываем карточку", file=sys.stderr)
                            login(page)
                            open_projects_registry(page)
                            grid = restore_registry_page(page, projects[0], page_number)
                            scroll_registry(grid, scroll_positions[project["row_index"]])
                            open_project(project_cell(grid, project), management_tab)
                            read_project_schedule(page, details)
                    except (PlaywrightError, AssertionError, RuntimeError, ValueError) as error:
                        print(f"  Не удалось прочитать сроки ПИР и СМР: {str(error).splitlines()[0]}", file=sys.stderr)
                        details["schedule_error"] = "Не удалось прочитать сроки ПИР и СМР"
                step = "переход в «Управление проектами»"
                management_tab.click(timeout=45000)
                step = "переход в «Управление участниками»"
                if not page.locator(PARTICIPANTS_PANEL).is_visible():
                    participants_tab.click(timeout=45000)
                step = "чтение списка участников"
                details["participants"] = read_participants(page)
                details["oks_number"] = read_project_number(page) or details["oks_number"]
            # Ошибка одной карточки остаётся в результате, обход продолжается при доступном реестре.
            except (PlaywrightError, ValueError) as error:
                print(f"  Ошибка сбора, {step}: {error}", file=sys.stderr)
                details["participants"] = None
                details["participants_error"] = f"{step}: {str(error).splitlines()[0]}"

            if report and "oks_number" in details:
                read_report_sections(page, details)

            record = {**project, **details}
            if on_project is not None:
                on_project(record)
            results.append(record)
            if len(results) == limit:
                return results, True

            try:
                grid = restore_registry_page(page, projects[0], page_number)
            except (PlaywrightError, RuntimeError, ValueError) as error:
                print(f"Обход прерван: {error}", file=sys.stderr)
                return results, False

        try:
            if not advance_registry_page(page, grid):
                return results, True
        except (PlaywrightError, RuntimeError) as error:
            print(f"Обход прерван: {error}", file=sys.stderr)
            return results, False


def stop_on_sigterm(signum, frame):
    """Передаёт остановку контейнера штатной обработке прерванной выгрузки."""
    raise KeyboardInterrupt


def main():
    """Разбирает параметры запуска, собирает данные и печатает JSON."""
    cli = argparse.ArgumentParser(description="Сбор объектов и участников из ИСУП")
    cli.add_argument("--limit", type=int, help="Остановиться после указанного числа объектов")
    cli.add_argument("--headed", action="store_true", help="Показать окно браузера")
    cli.add_argument("--report", action="store_true", help="Выгрузить 34 поля отчёта «Объекты»")
    cli.add_argument("--save-db", action="store_true", help="Записать снимок в PostgreSQL")
    cli.add_argument("--exchange-threshold", type=int, default=7, help="Порог для вывода о днях без обмена")
    args = cli.parse_args()
    if args.limit is not None and args.limit < 1:
        cli.error("--limit должен быть больше нуля")
    if args.exchange_threshold < 0:
        cli.error("--exchange-threshold должен быть неотрицательным")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        try:
            ingestion = None
            if args.save_db:
                from src.shared.database import create_ingestion_sessions
                from src.web.ingestions.service import IngestionService

                ingestion = IngestionService(create_ingestion_sessions(), args.exchange_threshold)
            # Служебные сообщения отправляем в stderr, чтобы stdout содержал только JSON.
            with redirect_stdout(sys.stderr):
                previous_handler = signal.signal(signal.SIGTERM, stop_on_sigterm)
                try:
                    page = browser.new_page(viewport={"width": 1600, "height": 900})
                    login(page)
                    open_projects_registry(page)
                    results, complete = collect_projects_with_participants(
                        page, limit=args.limit, report=args.report or args.save_db,
                        on_project=ingestion.save_project if ingestion is not None else None,
                    )
                except BaseException as error:
                    if ingestion is not None:
                        try:
                            ingestion.finish(error=error)
                        except Exception as log_error:
                            print(f"Не удалось обновить журнал выгрузки ({type(log_error).__name__})")
                    if isinstance(error, KeyboardInterrupt):
                        print("Выгрузка остановлена")
                        raise SystemExit(130) from None
                    raise
                finally:
                    signal.signal(signal.SIGTERM, previous_handler)
                if ingestion is not None:
                    status = ingestion.finish(complete=complete, limited=args.limit is not None)
                    print(f"Снимок {ingestion.snapshot_id} сохранён в PostgreSQL со статусом {status}")
            output = results
            if args.report:
                exported_on = ingestion.exported_on if ingestion is not None else datetime.now(REPORT_TIMEZONE).date()
                output = [
                    make_object_report(
                        project, exported_on=exported_on, exchange_threshold=args.exchange_threshold
                    )
                    for project in results
                ]
            if not args.save_db or args.report:
                print(json.dumps(output, ensure_ascii=False, indent=2))
            errors = ("participants_error", "edo_error", "documents_error")
            if (ingestion is not None and status == "failed") or not complete or any(
                any(key in project for key in errors) for project in results
            ):
                raise SystemExit(1)
        finally:
            try:
                browser.close()
            except Exception as error:
                # Драйвер мог завершиться раньше браузера. Результат уже записан в stdout.
                if "Connection closed while reading from the driver" not in str(error):
                    raise
                print("  Соединение с драйвером Chromium уже закрыто", file=sys.stderr)


if __name__ == "__main__":
    main()
