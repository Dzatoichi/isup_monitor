import unittest
from unittest.mock import AsyncMock
from types import SimpleNamespace

from src.parser.auth import RegistryOpenError
from src.parser.http_registry import read_http_general_journal
from src.parser.general_journal import parse_registration
from src.web.analytics.monitoring import project_monitoring
from src.web.projects.export_facts import management_facts


PROJECT = '6315a4197231780aab8739ae'


def journal(building):
    return {'id': '694b8dbd04911c318cad8b7e', 'projectId': PROJECT,
            'titleStatus': 'SIGNED', 'titlePage': {'buildingInfo': building}}


class GeneralJournalTests(unittest.IsolatedAsyncioTestCase):
    async def test_registration_details_from_read_only_endpoint(self):
        data = journal({'number': '9/26-Ж4', 'registrationDate': '2026-05-25', 'signed': True})
        response = SimpleNamespace(ok=True, json=AsyncMock(return_value=data), dispose=AsyncMock())
        request = AsyncMock(return_value=response)
        result = await read_http_general_journal(request, PROJECT)
        request.assert_awaited_once_with(f'/api/itd-service/general-work-journal/{PROJECT}')
        response.dispose.assert_awaited_once()
        source = {'general_journal_target_solution': False, 'general_journal_registration': result}
        self.assertEqual(project_monitoring(5620, {}, source, [], [], [])['gsn_status'], 'ОЖР зарегистрирован в ГСН')
        _, issues = management_facts(5620, {}, source, [], [], [], {})
        self.assertFalse(any(item['code'] == 'GSN_NOT_REGISTERED' for item in issues))

    async def test_bad_response_and_wrong_project_are_rejected(self):
        for status, value in [(404, False), (200, 'false'), (200, {}), (200, None),
                              (200, {'projectId': 'another'})]:
            response = SimpleNamespace(ok=status == 200, status=status,
                                       json=AsyncMock(return_value=value), dispose=AsyncMock())
            with self.assertRaises(RegistryOpenError):
                await read_http_general_journal(AsyncMock(return_value=response), PROJECT)
            response.dispose.assert_awaited_once()

    def test_target_solution_alone_has_no_registration_meaning(self):
        for value in (True, False, None, 0, 'false'):
            self.assertEqual(project_monitoring(1, {}, {'general_journal_target_solution': value}, [], [], [])['gsn_status'], 'Нет данных')

    def test_unsigned_without_details_and_conflicting_details(self):
        for building, expected in [
            ({'signed': False, 'number': None, 'registrationDate': None}, 'ОЖР не зарегистрирован в ГСН'),
            ({'signed': True}, 'Нет данных'),
            ({'signed': False, 'number': '9/26', 'registrationDate': '2026-05-25'}, 'Нет данных'),
            ({}, 'Нет данных'),
        ]:
            source = {'general_journal_registration': parse_registration(journal(building), PROJECT)}
            self.assertEqual(project_monitoring(1, {}, source, [], [], [])['gsn_status'], expected)
