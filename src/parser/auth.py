"""Авторизация в ИСУП и чтение таблицы реестра ОКС."""

import os

from dotenv import load_dotenv
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

# Настройки подключения берутся из окружения, которое можно заполнить через .env.
load_dotenv()

VISIBLE_PROJECT_NAME = ".ag-center-cols-container .name_oks_table:visible"


# Авторизация
def login(page):
    """Входит в ИСУП с настройками из окружения и ждёт появления меню."""
    def skip_prefetch(route):
        headers = route.request.headers
        purpose = headers.get("sec-purpose") or headers.get("purpose", "")
        if "prefetch" in purpose:
            route.abort()
        else:
            route.fallback()

    # Страница входа заранее запрашивает сотни ресурсов для других разделов.
    page.route("**/*", skip_prefetch)
    try:
        login_input = page.get_by_placeholder("Логин")
        password_input = page.get_by_placeholder("Пароль")
        for attempt in range(2):
            try:
                page.goto(os.environ["ISUP_URL"], wait_until="commit", timeout=30000)
                break
            except PlaywrightTimeoutError as error:
                if attempt == 1:
                    raise RuntimeError("ИСУП не ответила на открытие страницы входа после двух попыток") from error
                page.wait_for_timeout(2000)

        print("Страница ИСУП ответила, ждём загрузки формы входа")
        try:
            # Повторное открытие страницы прервало бы загрузку тяжёлых скриптов.
            login_input.wait_for(state="visible", timeout=180000)
            password_input.wait_for(state="visible", timeout=15000)
        except PlaywrightTimeoutError as error:
            raise RuntimeError("ИСУП ответила, но форма входа не загрузилась за 3 минуты") from error

        print("Сайт открыт")

        login_input.fill(os.environ["ISUP_LOGIN"])
        password_input.fill(os.environ["ISUP_PASSWORD"])

        page.get_by_role(
            "button",
            name="Войти",
            exact=True,
        ).click()

        registry_icon = page.locator(
            'img[src*="edinii_reestr_objectov.png"]'
        )

        registry_icon.wait_for(
            state="visible",
            timeout=60000,
        )

        print("Авторизация успешна")
    finally:
        page.unroute("**/*", skip_prefetch)


# ==========================================
# 2. Переход в реестр
# ==========================================

def open_projects_registry(page):
    """Открывает таблицу объектов капитального строительства."""
    project_name = page.locator(VISIBLE_PROJECT_NAME).first
    if project_name.is_visible():
        return

    registry_icon = page.locator(
        'img[src*="edinii_reestr_objectov.png"]'
    )

    registry_tab = page.locator(".el-tabs__item:visible").filter(
        has_text="Единый реестр объектов"
    )
    if not registry_tab.is_visible():
        registry_icon.click()
    registry_tab.click(timeout=30000)
    print("Открыли единый реестр объектов")

    objects_button = page.locator("button:visible").filter(
        has_text="Объекты капитального строительства"
    )

    if not project_name.is_visible():
        try:
            objects_button.click(timeout=15000)
        except PlaywrightTimeoutError as click_error:
            active_tab = registry_tab.and_(page.locator(".is-active"))
            if not active_tab.is_visible():
                # ИСУП может вернуть фокус на главную при завершении авторизации.
                registry_tab.click(timeout=15000)
                if not project_name.is_visible():
                    objects_button.click(timeout=30000)
            else:
                try:
                    project_name.wait_for(state="visible", timeout=30000)
                except PlaywrightTimeoutError:
                    raise click_error from None

    project_name.wait_for(state="visible", timeout=30000)
    print("Открыли объекты капитального строительства")


# ==========================================
# 3. Поиск AG Grid
# ==========================================

def find_projects_grid(page):
    """Находит видимую таблицу AG Grid по ячейкам с названиями объектов."""
    page.locator(VISIBLE_PROJECT_NAME).first.wait_for(
        state="visible",
        timeout=30000,
    )

    grid = page.locator(
        ".ag-root-wrapper:visible"
    ).filter(
        has=page.locator(".name_oks_table")
    ).last

    grid.wait_for(state="visible")

    print("AG Grid найдена")
    return grid


# Чтение текущих строк

def parse_visible_projects(grid):
    """
    Читает строки AG Grid одним JS-вызовом.
    Не зависит от перерисовки отдельных строк.
    """

    return grid.evaluate(r"""
        root => {
            const rows = root.querySelectorAll(
                '.ag-center-cols-container [role="row"][row-index]'
            );

            const getText = (row, selector) => {
                const el = row.querySelector(selector);
                return el?.textContent?.trim() || null;
            };

            const result = [];

            for (const row of rows) {
                const name = getText(row, ".name_oks_table");

                if (!name) continue;

                const index = Number(
                    row.getAttribute("row-index")
                );

                if (!Number.isInteger(index)) continue;

                const tags = Array.from(
                    row.querySelectorAll(".tag-oks_table")
                ).map(el => el.textContent.trim());

                const progressText = getText(
                    row,
                    '[col-id="progress_oks_2"] .percentage'
                );

                const progress = (
                    progressText !== null &&
                    /^\d+$/.test(progressText)
                ) ? Number(progressText) : null;

                result.push({
                    row_index: index,
                    name: name,
                    work_type: tags[0] || null,
                    stage: tags[1] || null,
                    progress: progress,
                    region: getText(
                        row, '[col-id="name_okato"]'
                    ),
                    municipality: getText(
                        row, '[col-id="name_oktmo"]'
                    ),
                    purpose: getText(
                        row, ".func-purp-oks"
                    )
                });
            }

            return result;
        }
    """)

# Поиск прокрутки

def find_scrollable(grid):
    """Находит контейнер, у которого есть запас вертикальной прокрутки."""
    selectors = (
        ".ag-body-vertical-scroll-viewport",
        ".ag-body-viewport",
    )

    for selector in selectors:
        elements = grid.locator(selector)

        for i in range(elements.count()):
            element = elements.nth(i)

            info = element.evaluate("""
                el => ({
                    scrollHeight: el.scrollHeight,
                    clientHeight: el.clientHeight
                })
            """)

            if (
                info["clientHeight"] > 0
                and info["scrollHeight"]
                > info["clientHeight"] + 2
            ):
                return element

    return None


def get_scroll_info(element):
    """Возвращает текущую позицию, предел прокрутки и высоту окна таблицы."""
    return element.evaluate("""
        el => ({
            top: el.scrollTop,
            max: Math.max(
                0,
                el.scrollHeight - el.clientHeight
            ),
            height: el.clientHeight
        })
    """)

# Сбор одной страницы

def collect_current_page(page, grid, *, scroll_positions=None):
    """
    Собирает все объекты текущей страницы
    с учётом виртуализации строк AG Grid.
    """

    projects = {}
    scrollable = find_scrollable(grid)

    def remember_visible(top):
        """Сохраняет строки, которые AG Grid сейчас держит в разметке."""
        for project in parse_visible_projects(grid):
            index = project["row_index"]
            projects[index] = project
            # По этой позиции затем можно снова найти строку и открыть карточку.
            if scroll_positions is not None:
                scroll_positions.setdefault(index, top)

    if scrollable is None:
        remember_visible(0)
    else:
        # В начале каждой страницы идём наверх
        scrollable.evaluate("el => el.scrollTop = 0")
        page.wait_for_timeout(300)

        stalled_steps = 0
        for _ in range(300):
            before = get_scroll_info(scrollable)
            remember_visible(before["top"])

            if before["top"] >= before["max"] - 2:
                break

            # Прокручиваем небольшими шагами
            scrollable.evaluate("""
                el => {
                    const distance = Math.max(
                        80,
                        Math.floor(el.clientHeight * 0.6)
                    );

                    el.scrollTop = Math.min(
                        el.scrollTop + distance,
                        el.scrollHeight - el.clientHeight
                    );
                }
            """)

            page.wait_for_timeout(300)

            after = get_scroll_info(scrollable)

            if after["top"] <= before["top"]:
                if after["top"] >= after["max"] - 2:
                    # После подгрузки строк AG Grid может пересчитать высоту и сдвинуть конец.
                    remember_visible(after["top"])
                    break
                stalled_steps += 1
                if stalled_steps == 3:
                    raise RuntimeError(
                        f"Не удалось продолжить прокрутку: позиция {after['top']} из {after['max']}"
                    )
            else:
                stalled_steps = 0
        else:
            raise RuntimeError(
                "Превышен лимит шагов прокрутки"
            )

    if not projects:
        raise RuntimeError(
            "На странице не найдены объекты"
        )

    indices = sorted(projects)

    # Сверяем также начало и конец страницы, чтобы заметить пропуск крайних строк.
    bounds = grid.evaluate("""root => {
        const read = ref => Number(root.querySelector(
            `.ag-paging-panel :is([ref="${ref}"], [data-ref="${ref}"])`
        )?.textContent.trim());
        return [read('lbFirstRowOnPage'), read('lbLastRowOnPage')];
    }""")
    start, end = bounds
    expected = range(start - 1, end) if start and end and end >= start else range(indices[0], indices[-1] + 1)
    missing = [
        index
        for index in expected
        if index not in projects
    ]

    if missing:
        raise RuntimeError(
            f"Пропущены строки AG Grid: {missing[:20]}"
        )

    return [projects[index] for index in indices]


# Кнопка следующей страницы
def get_next_button(grid):
    """
    Находит управляющий элемент пагинации
    по иконке ag-icon-next.
    """

    icon = grid.locator(
        ".ag-paging-panel .ag-icon-next"
    ).first

    if icon.count() == 0:
        raise RuntimeError(
            "Кнопка следующей страницы не найдена. "
            "Проверь HTML панели пагинации."
        )

    button = icon.locator(
        "xpath=ancestor::*[contains("
        "concat(' ', normalize-space(@class), ' '), "
        "' ag-paging-button '"
        ")][1]"
    )

    if button.count() == 0:
        button = icon.locator("xpath=..")

    return button


def is_next_disabled(button):
    """Проверяет доступность кнопки Далее."""

    return button.evaluate("""
        el => {
            return (
                el.hasAttribute("disabled") ||
                el.getAttribute("aria-disabled") === "true" ||
                el.classList.contains("ag-disabled") ||
                getComputedStyle(el).pointerEvents === "none"
            );
        }
    """)


# Проверка смены страницы

def get_page_signature(grid):
    """
    Возвращает отпечаток текущих строк.
    Нужен для ожидания следующей страницы.
    """

    return grid.evaluate("""
        root => {
            const rows = root.querySelectorAll(
                '.ag-center-cols-container [role="row"][row-index]'
            );

            return Array.from(rows)
                .map(row => {
                    const index = row.getAttribute("row-index");
                    const name = row.querySelector(
                        ".name_oks_table"
                    )?.textContent?.trim() || "";

                    return index + ":" + name;
                })
                .filter(value => !value.endsWith(":"))
                .join("|");
        }
    """)


def wait_for_new_page(page, grid, old_signature):
    """Ждёт смены данных после перехода."""

    for _ in range(75):
        current = get_page_signature(grid)

        if current and current != old_signature:
            return

        page.wait_for_timeout(200)

    raise RuntimeError(
        "После нажатия Далее таблица не обновилась"
    )


def advance_registry_page(page, grid):
    """Переходит на следующую страницу и ждёт обновления строк."""
    button = get_next_button(grid)
    if is_next_disabled(button):
        return False

    # Строки обновляются асинхронно после клика по кнопке «Далее».
    signature = get_page_signature(grid)
    button.click(timeout=15000)
    wait_for_new_page(page, grid, signature)
    page.wait_for_timeout(300)
    return True


def registry_page_number(grid):
    """Читает номер текущей страницы из панели пагинации AG Grid."""
    current = grid.locator('.ag-paging-panel [ref="lbCurrent"], .ag-paging-panel [data-ref="lbCurrent"]')
    return int(current.inner_text(timeout=15000).strip())

# Сбор всех страниц

def collect_all_projects(page, grid):
    """
    Обходит все страницы, пока доступна
    кнопка перехода на следующую страницу.

    Количество объектов заранее неизвестно.
    """

    all_projects = []

    # Это предохранитель от бесконечного цикла,
    # а не ограничение числа объектов.
    max_pages = 100

    for page_number in range(1, max_pages + 1):
        print(f"\n========== СТРАНИЦА {page_number} ==========")

        # Собираем одну страницу
        page_projects = collect_current_page(page, grid)

        print(
            "Собрано на странице:",
            len(page_projects)
        )

        all_projects.extend(page_projects)

        print(
            "Всего собрано:",
            len(all_projects)
        )

        # Проверяем пагинацию
        if not advance_registry_page(page, grid):
            print("\nДостигнута последняя страница")
            break

    else:
        raise RuntimeError(
            "Достигнут защитный лимит страниц. "
            "Проверь работу пагинации."
        )

    print("\n========== ИТОГ ==========")
    print("Всего объектов:", len(all_projects))
    print("Всего страниц:", page_number)

    return all_projects


# Запуск

def main():
    """Запускает отдельную проверку реестра и печатает статистику по стадиям."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False
        )

        try:
            context = browser.new_context(
                viewport={
                    "width": 1600,
                    "height": 900,
                }
            )

            page = context.new_page()

            login(page)

            open_projects_registry(page)

            grid = find_projects_grid(page)

            projects = collect_all_projects(
                page,
                grid
            )

            pir_count = sum(
                project["stage"] == "ПИР"
                for project in projects
            )

            smr_count = sum(
                project["stage"] == "СМР"
                for project in projects
            )

            print("\n========== СТАТИСТИКА ==========")
            print("Всего:", len(projects))
            print("ПИР:", pir_count)
            print("СМР:", smr_count)

            print("\nПервые 5 записей:")

            for project in projects[:5]:
                print({
                    "row_index": project["row_index"],
                    "stage": project["stage"],
                    "progress": project["progress"],
                })

            input("\nНажми Enter для завершения...")

        except PlaywrightTimeoutError as error:
            print("\nОшибка ожидания:")
            print(error)

            input("Проверь браузер и нажми Enter...")

        except Exception as error:
            print("\nПроизошла ошибка:")
            print(f"{type(error).__name__}: {error}")

            input("Проверь браузер и нажми Enter...")

        finally:
            browser.close()


if __name__ == "__main__":
    main()
