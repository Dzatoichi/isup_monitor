import unittest
from types import SimpleNamespace as Row

from src.web.analytics.monitoring import project_monitoring, paginate_monitoring


class MonitoringTests(unittest.TestCase):
    def test_search_before_ten_row_pagination(self):
        rows = [{"number": 1000 + i, "name": f"Школа {i}" if i < 23 else "Бассейн",
                 "author_supervision": [], "build_control": [], "rd_status": "Загружена"}
                for i in range(30)]
        result = paginate_monitoring(rows, 2, search="  ШКОЛА  ")
        self.assertEqual((result["total"], result["page_count"], result["first"], result["last"]), (23, 3, 11, 20))
        self.assertEqual([row["number"] for row in result["monitoring"]], list(range(1010, 1020)))
        self.assertEqual(result["monitoring_totals"]["rd_uploaded"], 30)
        self.assertEqual(paginate_monitoring(rows, 1, search="1029")["monitoring"], [rows[-1]])
        empty = paginate_monitoring(rows, 99, search="не существует")
        self.assertEqual((empty["total"], empty["page"], empty["monitoring"]), (0, 1, []))
        default = paginate_monitoring(rows, 1)
        self.assertEqual(len(default["monitoring"]), 10)

    def test_pagination_preserves_totals_and_snapshot_order(self):
        rows = [{"number": i, "author_supervision": ["org"] if i == 0 else [],
                 "build_control": [], "rd_status": "Загружена"} for i in range(148)]
        first = paginate_monitoring(rows, 1, 25)
        last = paginate_monitoring(rows, 6, 25)
        self.assertEqual((first["first"], first["last"], first["page_count"]), (1, 25, 6))
        self.assertEqual((last["first"], last["last"], len(last["monitoring"])), (126, 148, 23))
        self.assertEqual(first["monitoring_totals"], last["monitoring_totals"])
        self.assertEqual(last["monitoring_totals"]["rd_uploaded"], 148)
        self.assertEqual(paginate_monitoring(rows, 999, 50)["page"], 3)
        empty = paginate_monitoring([], 10, 25)
        self.assertEqual((empty["first"], empty["last"], empty["page"]), (0, 0, 1))

    def build(self, source=None, organizations=(), people=(), documents=()):
        return project_monitoring(1, {"Объект": "Школа"}, source or {}, organizations, people, documents)

    def test_missing_source_does_not_mean_absent(self):
        result = self.build()
        self.assertFalse(result["edo_read"])
        self.assertEqual(result["rd_status"], "Нет данных")
        self.assertEqual(result["gsn_status"], "Нет данных")

    def test_empty_read_sections_are_known(self):
        result = self.build({"sections_read": {"organizations": True, "people": True, "pir_documents": True}})
        self.assertTrue(result["edo_read"])
        self.assertEqual(result["author_supervision"], [])
        self.assertEqual(result["rd_status"], "Не загружена")

    def test_signatures_stay_with_organization_and_deduplicate_users(self):
        orgs = [Row(source="edo", external_id="a", name="Надзор", role="AUTHOR_SUPERVISION")]
        people = [Row(organization_external_id=org, external_id=user, signed=signed)
                  for org, user, signed in [("a", "1", True), ("a", "1", True), ("a", "2", False), ("b", "3", True)]]
        result = self.build({"sections_read": {"organizations": True, "people": True}}, orgs, people)
        org = result["author_supervision"][0]
        self.assertEqual((org["total"], org["signed"], org["unsigned"]), (2, 1, 1))
        self.assertEqual(org["label"], "Авторский надзор")

    def test_rd_card_without_file_is_not_uploaded(self):
        source = {"sections_read": {"pir_documents": True}}
        result = self.build(source, documents=[Row(kind="РД", source_data={"documentFileId": None})])
        self.assertEqual(result["rd_status"], "Не загружена")
        result = self.build(source, documents=[Row(kind="РД", source_data={"documentFileId": "file"})])
        self.assertEqual(result["rd_status"], "Загружена")
        result = self.build(source, documents=[Row(kind="РД", source_data={})])
        self.assertEqual(result["rd_status"], "Нет данных")


if __name__ == "__main__":
    unittest.main()
