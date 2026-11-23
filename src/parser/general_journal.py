"""Регистрация ОЖР берётся из сведений стройнадзора, а не из target-solution."""
from .auth import RegistryOpenError
from .report import parse_date


def parse_registration(data, project_id):
    """Сохраняет только реквизиты регистрации, без персональных данных журнала."""
    if not isinstance(data, dict) or data.get('projectId') != project_id:
        raise RegistryOpenError('ЭДО вернуло журнал другого проекта или неизвестный формат')
    title = data.get('titlePage')
    building = title.get('buildingInfo') if isinstance(title, dict) else None
    if building is not None and not isinstance(building, dict):
        raise RegistryOpenError('Неизвестный формат сведений о регистрации ОЖР')
    building = building or {}
    number = building.get('number')
    if isinstance(number, str):
        number = number.strip() or None
    elif number is not None:
        raise RegistryOpenError('Некорректный номер регистрации ОЖР')
    raw_date = building.get('registrationDate')
    day = parse_date(raw_date) if isinstance(raw_date, str) and raw_date else None
    if raw_date and day is None:
        raise RegistryOpenError('Некорректная дата регистрации ОЖР')
    signed = building.get('signed')
    if signed is not None and type(signed) is not bool:
        raise RegistryOpenError('Некорректный признак подписи регистрации ОЖР')
    return {'journal_id': data.get('id'), 'project_id': project_id,
            'number': number, 'registration_date': day.isoformat() if day else None,
            'signed': signed, 'title_status': data.get('titleStatus')}


def registration_state(source):
    """Противоречивые или старые косвенные признаки не объявляет регистрацией либо её отсутствием."""
    record = source.get('general_journal_registration')
    if source.get('gsn_error') or not isinstance(record, dict):
        return None
    if record.get('signed') is True and record.get('number') and record.get('registration_date'):
        return True
    if record.get('signed') is False and not record.get('number') and not record.get('registration_date'):
        return False
    return None
