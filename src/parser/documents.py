"""Чтение дат документов из таблицы ИСУП."""

import re

from playwright.sync_api import expect

from .auth import find_scrollable, get_next_button, get_scroll_info, is_next_disabled
from .report import parse_date


DATE_CELL = '[role="gridcell"][col-id="doc_date"]'


def read_document_dates(page, *, records=None):
    """Собирает даты и, если передан список, реквизиты строк документации."""
    heading = page.locator('[role="columnheader"][col-id="doc_date"]')
    grid = page.locator(".ag-root-wrapper:visible").filter(has=heading)
    grid.wait_for(state="visible", timeout=25000)
    column_left = grid.locator('[role="columnheader"][col-id="doc_date"]').evaluate(
        "header => header.offsetLeft"
    )

    all_documents = page.get_by_text("Все", exact=True).filter(visible=True)
    if all_documents.count() == 1:
        all_documents.click(timeout=10000)

    grid.locator(".ag-overlay-loading-center:visible").first.wait_for(
        state="hidden", timeout=25000
    )
    first = grid.locator('.ag-paging-panel [ref="lbFirstRowOnPage"], .ag-paging-panel [data-ref="lbFirstRowOnPage"]')
    last = grid.locator('.ag-paging-panel [ref="lbLastRowOnPage"], .ag-paging-panel [data-ref="lbLastRowOnPage"]')
    total = grid.locator('.ag-paging-panel [ref="lbRecordCount"], .ag-paging-panel [data-ref="lbRecordCount"]')
    dates = []
    while True:
        first_row = int(first.inner_text().strip())
        last_row = int(last.inner_text().strip())
        if first_row == last_row == 0:
            return dates

        cells = grid.locator(f'[role="row"][row-index] {DATE_CELL}')
        scroll = find_scrollable(grid)
        if scroll is not None:
            scroll.evaluate("(el) => { el.scrollTop = 0; }")
        first_cell = grid.locator(f'[role="row"][row-index="{first_row - 1}"] {DATE_CELL}')
        horizontal = grid.locator(".ag-body-horizontal-scroll-viewport")
        if not first_cell.count() and horizontal.count() == 1:
            # После переключения фильтра AG Grid может ещё не отрисовать столбец с датой.
            horizontal.evaluate("(el, left) => { el.scrollLeft = left; }", column_left)
        first_cell.wait_for(state="attached", timeout=15000)
        received = {}
        while True:
            received.update(cells.evaluate_all("""elements => elements.map(cell => {
                const row = cell.closest('[role="row"]');
                const read = id => row.querySelector(`[col-id="${id}"]`)?.textContent.trim() || null;
                return [Number(row.getAttribute('row-index')), {
                    document_on: cell.textContent.trim(),
                    document_number: read('doc_num'),
                    name: read('doc_name'),
                    document_type: read('type_name'),
                    status: read('status_name')
                }];
            })"""))
            if scroll is None:
                break
            info = get_scroll_info(scroll)
            if info["top"] >= info["max"] - 2:
                break
            scroll.evaluate("(el) => { el.scrollTop += Math.max(1, el.clientHeight * 0.6); }")
            page.wait_for_timeout(300)
            if get_scroll_info(scroll)["top"] <= info["top"]:
                raise ValueError("Прокрутка таблицы документации остановилась")

        # AG Grid может держать соседние строки в DOM. Считаем только текущую страницу.
        expected = range(first_row - 1, last_row)
        missing = set(expected).difference(received)
        if missing and total.count() == 1:
            # Пока итог неизвестен, AG Grid показывает размер страницы вместо её фактического конца.
            expect(total).to_have_text(re.compile(r"^\s*\d[\d\s]*\s*$"), timeout=15000)
            record_count = int("".join(total.inner_text().split()))
            last_row = min(int(last.inner_text().strip()), record_count)
            expected = range(first_row - 1, last_row)
            missing = set(expected).difference(received)
        if missing:
            raise ValueError(
                f"В документации прочитано {len(expected) - len(missing)} из "
                f"{len(expected)} строк страницы (записи {first_row}–{last_row})"
            )
        for index in expected:
            record = received[index]
            record["document_on"] = parse_date(record["document_on"])
            dates.append(record["document_on"])
            if records is not None:
                records.append(record)

        button = get_next_button(grid)
        if is_next_disabled(button):
            return dates
        button.click(timeout=15000)
        expect(first).to_have_text(str(last_row + 1), timeout=15000)
