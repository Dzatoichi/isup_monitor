from pathlib import Path

from fastapi.templating import Jinja2Templates


WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")


def event_value(value):
    """Форматирует журнал для чтения без технических имён полей."""
    labels = {"full_name": "ФИО", "position": "Должность", "role": "Роль", "signed": "Подпись",
              "version": "Версия", "remark_count": "Замечаний", "approved_on": "Согласован",
              "transferred_on": "Передан заказчику", "issued_on": "Выдан в работу",
              "name": "Название", "status": "Статус", "document_type": "Тип документа"}
    if value is None:
        return "—"
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if key == "signed" and item is not None:
                item = "Подписан" if item else "Без подписи"
            parts.append(f"{labels.get(key, key)}: {item if item is not None else '—'}")
        return "; ".join(parts)
    return value


templates.env.filters["event_value"] = event_value
