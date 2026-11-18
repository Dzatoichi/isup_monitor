from io import BytesIO
from zipfile import ZipFile
from openpyxl import load_workbook
from sqlalchemy import select

from src.web.projects.projects_model import Project
from .dao import AssignmentDAO


COLUMNS = {
    "Номер в ИСУП": "oks_number", "Руководитель проекта": "manager",
    "Аккаунт РП": "manager_email", "Должность РП": "manager_position",
    "Строительный заместитель": "deputy", "Аккаунт заместителя": "deputy_email",
    "Должность заместителя": "deputy_position",
}


class AssignmentService:
    @staticmethod
    def parse_excel(content):
        """Проверяет весь импорт до записи, чтобы ошибка не оставила половину справочника."""
        with ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 30_000_000:
                raise ValueError("Распакованный файл слишком большой")
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=False)
        try:
            iterator = workbook.active.iter_rows(values_only=True)
            header = next(iterator, ())
            names = [str(value).strip() if value is not None else "" for value in header]
            if not set(COLUMNS) <= set(names) or len(names) != len(set(names)):
                raise ValueError("Нужны уникальные колонки: " + ", ".join(COLUMNS))
            rows = []
            numbers = set()
            for line, row in enumerate(iterator, start=2):
                if not any(value is not None for value in row):
                    continue
                if line > 10001:
                    raise ValueError("Максимум 10000 строк")
                values = {key: row[names.index(label)] for label, key in COLUMNS.items()}
                number = values["oks_number"]
                if isinstance(number, str) and number.isdecimal():
                    number = int(number)
                if type(number) is not int or not 0 < number < 2**63 or number in numbers:
                    raise ValueError(f"Строка {line}: неверный или повторный номер ОКС")
                values["oks_number"] = number
                for key in COLUMNS.values():
                    if key == "oks_number":
                        continue
                    value = str(values[key]).strip() if values[key] is not None else None
                    if value and (len(value) > 500 or value.startswith("=")):
                        raise ValueError(f"Строка {line}: некорректное значение")
                    if key.endswith("_email") and value:
                        if "@" not in value or any(char.isspace() for char in value):
                            raise ValueError(f"Строка {line}: неверный email")
                        value = value.lower()
                    values[key] = value
                numbers.add(number)
                rows.append(values)
            return rows
        finally:
            workbook.close()

    @staticmethod
    async def save(session, rows):
        numbers = {row["oks_number"] for row in rows}
        existing = set(await session.scalars(select(Project.oks_number).where(Project.oks_number.in_(numbers))))
        if numbers != existing:
            raise ValueError("Не найдены ОКС: " + ", ".join(map(str, sorted(numbers - existing))))
        await AssignmentDAO.save(session, rows)
        await session.commit()
