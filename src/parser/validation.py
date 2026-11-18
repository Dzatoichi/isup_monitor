"""Отмечает некорректные значения ИСУП, сохраняя причину в снимке."""
import re


EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validate_record(record):
    for key, value in list(record.items()):
        if value == "[object Object]":
            record[key] = None
            record[f"{key}_error"] = "ИСУП вернула [object Object] вместо значения"
    invalid_contacts = []
    for person in record.get("people") or []:
        email = person.get("email")
        if email and not EMAIL.fullmatch(email):
            invalid_contacts.append(str(person.get("external_id", "")))
    if invalid_contacts:
        # Контакты остаются в защищённых таблицах. В общую диагностику попадают только идентификаторы.
        record["contacts_error"] = "Некорректный email у участников: " + ", ".join(invalid_contacts)
