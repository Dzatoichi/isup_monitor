import unittest
import json
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as Row
from unittest.mock import AsyncMock, Mock

from openpyxl import load_workbook
from src.web.projects.export import HEADERS, build_workbook
from src.web.projects.export_facts import management_facts
from src.web.exports.scheduler import next_run
from src.web.exports.service import atomic_write
from src.web.exports.disk import DiskService, DeliveryError
from src.web.regulations.schemas import TrafficRules
from src.parser.http_registry import read_registry_rows
from src.parser.auth import RegistryOpenError
from src.parser.report import REPORT_TIMEZONE


class ManagementFactsTests(unittest.TestCase):
    def facts(self, source=None, orgs=(), people=(), docs=(), rules=None):
        return management_facts(1, {'Стадия': 'СМР', 'Руководитель проекта': 'РП', 'Строительный заместитель': 'З'},
                                source or {}, orgs, people, docs, rules or {})

    def test_absent_role_requires_explicit_rule(self):
        source = {'sections_read': {'organizations': True, 'people': True, 'pir_documents': True}}
        _, issues = self.facts(source)
        absent = next(item for item in issues if item['code'] == 'ROLE_ABSENT:AUTHOR_SUPERVISION')
        self.assertEqual(absent['level'], 'Факт для проверки')
        _, issues = self.facts(source, rules={'required_roles_by_stage': {'СМР': ['AUTHOR_SUPERVISION']}})
        self.assertEqual(next(item for item in issues if item['code'] == absent['code'])['level'], 'Подтверждённая проблема')
        _, issues = self.facts(rules={'required_roles_by_stage': {'СМР': ['AUTHOR_SUPERVISION']}})
        self.assertFalse(any(item['code'].startswith('ROLE_ABSENT:') for item in issues))

    def test_unsigned_deduplicated_and_empty_team_separate(self):
        source = {'sections_read': {'organizations': True, 'people': True}}
        orgs = [Row(source='edo', external_id='1', name='А', role='AUTHOR_SUPERVISION'),
                Row(source='edo', external_id='2', name='Б', role='BUILD_CONTROL')]
        person = Row(organization_external_id='1', external_id='u1', signed=False, full_name='Петров')
        facts, issues = self.facts(source, orgs, [person, person])
        self.assertEqual(sum(item['code'] == 'UNSIGNED_PARTICIPANT' for item in issues), 1)
        self.assertEqual(next(item for item in issues if item['code'] == 'EMPTY_TEAM:BUILD_CONTROL')['organization'], 'Б')
        self.assertIn('Подписали 0 из 1', facts['AUTHOR_SUPERVISION'][1])

    def test_document_card_is_not_file(self):
        source = {'sections_read': {'pir_documents': True}}
        docs = [Row(kind='ПД', source_data={'documentFileId': 'file'}), Row(kind='РД', source_data={'documentFileId': None})]
        facts, _ = self.facts(source, docs=docs)
        self.assertEqual((facts['ПД'], facts['РД']), ('Загружена', 'Не загружена'))
        facts, _ = self.facts(docs=[])
        self.assertEqual(facts['РД'], 'Не удалось проверить')

    def test_rule_validation_rejects_unknown_values(self):
        for value in ({'required_roles_by_stage': {'СМР': ['WRONG']}},
                      {'required_documents_by_stage': {'СМР': ['ИД']}}, {'gsn_required_stages': ['WRONG']}):
            with self.assertRaises(ValueError):
                TrafficRules.model_validate(value)

    def test_excel_metadata_dates_and_formula_text(self):
        rows = {name: [] for name in HEADERS}
        values = [None] * len(HEADERS['Сводка объектов'])
        values[0], values[1] = 1, '=HYPERLINK("bad")'
        rows['Сводка объектов'] = [(*values, 40, date(2026, 11, 18))]
        book = load_workbook(BytesIO(build_workbook(rows, show_contacts=False)))
        sheet = book['Сводка объектов']
        self.assertEqual(book.sheetnames[:2], ['Сводка объектов', 'Проблемы'])
        self.assertEqual(sheet['B2'].data_type, 's')
        self.assertEqual(sheet.cell(2, sheet.max_column).value.date(), date(2026, 11, 18))
        self.assertEqual(sheet.freeze_panes, 'C2')
        self.assertNotIn('Email', [cell.value for cell in book['Участники и подписи'][1]])
        for page in book:
            self.assertTrue(page.auto_filter.ref)
        self.assertEqual(len(HEADERS['Объекты']), 34)

    def test_atomic_file_and_disk_disabled_without_credentials(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'a.xlsx'
            atomic_write(path, b'first')
            atomic_write(path, b'second')
            self.assertEqual(path.read_bytes(), b'second')
            self.assertEqual(len(list(Path(folder).iterdir())), 1)
        with self.assertRaises(DeliveryError):
            DiskService(None, 'disk:/reports')

    def test_disk_upload_does_not_forward_token_to_upload_host(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'report.xlsx'
            path.write_bytes(b'xlsx')
            disk = DiskService('secret', 'disk:/Reports')
            href = 'https://uploader.dst.yandex.net/upload/temporary'
            disk.request = Mock(side_effect=[(200, json.dumps({'href': href, 'method': 'PUT'}).encode()), (202, b'')])
            self.assertEqual(disk.upload(path), 'Принято Диском')
            self.assertEqual(disk.request.call_args_list[1].kwargs, {'data': b'xlsx', 'authorized': False})
            disk.request = Mock(return_value=(200, json.dumps({'href': 'https://other.example/upload', 'method': 'PUT'}).encode()))
            with self.assertRaises(DeliveryError):
                disk.upload(path)
            disk.request.assert_called_once()

    def test_schedule_uses_krasnoyarsk_weekday(self):
        now = datetime(2026, 11, 20, 21, 0, tzinfo=REPORT_TIMEZONE)
        self.assertEqual(next_run(now, 4, 22, 0), now.replace(hour=22))
        self.assertEqual((next_run(now.replace(hour=23), 4, 22, 0) - now.replace(hour=22)).days, 7)


class ArchiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_archive_groups_and_global_limit(self):
        async def post(path, payload):
            archived = payload['where']['and'][0]['eq']['archive_oks']
            if '*' in payload:
                return [{'count': 2}]
            ids = [3, 4] if archived else [1, 2]
            return [{'id_oks': i} for i in ids[payload['offset']:payload['offset'] + payload['limit']]]
        rows = await read_registry_rows(post, 1, 3, 'all')
        self.assertEqual([row['_archived'] for row in rows], [False, False, True])
        self.assertEqual([row['id_oks'] for row in rows], [1, 2, 3])
        self.assertEqual(len(await read_registry_rows(post, 1, None, 'archived')), 2)
        with self.assertRaises(RegistryOpenError):
            await read_registry_rows(AsyncMock(return_value=[{'count': -1}]), 1, None, 'all')


if __name__ == '__main__':
    unittest.main()
