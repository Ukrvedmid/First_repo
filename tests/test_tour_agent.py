import unittest
from datetime import date

from app import tour_agent as t


class TourAgentTests(unittest.TestCase):
    def test_numeric_date_range(self):
        parsed = t.parse_date_range("Pauschalreise 26.08.2026 - 02.09.2026 ab Hannover")
        self.assertEqual(parsed, (date(2026, 8, 26), date(2026, 9, 2)))

    def test_text_date_range(self):
        parsed = t.parse_date_range("Deal ab Berlin 26. Aug. - 02. Sept. All Inclusive")
        self.assertEqual(parsed, (date(2026, 8, 26), date(2026, 9, 2)))

    def test_return_after_deadline_is_rejected(self):
        self.assertFalse(t.in_window(date(2026, 8, 29), date(2026, 9, 7)))
        self.assertTrue(t.in_window(date(2026, 8, 26), date(2026, 9, 2)))

    def test_sea_package_filter(self):
        self.assertTrue(t.is_sea_package("Pauschalreise mit Flug All Inclusive Strandurlaub Kreta"))
        self.assertFalse(t.is_sea_package("Nur Hotel in Berlin mit Frühstück"))
        self.assertFalse(t.is_sea_package("Pauschalreise Städtereise Berlin mit Flug"))

    def test_holidaycheck_like_deal_is_parsed(self):
        text = (
            "Calido Maris Hotel Türkische Riviera Deal ab Berlin Brandenburg "
            "All Inclusive 26. Aug. - 02. Sept. ab 1.354 € 2 P 7 Tage Strand"
        )
        deal = t.build_deal("HolidayCheck", "https://example.test/deal", "Calido Maris Hotel", text)
        self.assertIsNotNone(deal)
        self.assertEqual(deal.departure, date(2026, 8, 26))
        self.assertEqual(deal.return_date, date(2026, 9, 2))
        self.assertEqual(deal.price_eur, 1354)
        self.assertEqual(deal.persons, 2)
        self.assertIn("Berlin", deal.airport)
        self.assertEqual(deal.board, "All Inclusive")

    def test_late_return_deal_is_not_built(self):
        text = "Pauschalreise Strand Kreta ab Hannover 29. Aug. - 07. Sept. ab 2.118 € 2 Personen"
        self.assertIsNone(t.build_deal("Test", "https://example.test/late", "Kreta", text))

    def test_queries_cover_all_germany_and_major_sources(self):
        joined = "\n".join(t.search_queries()).lower()
        for term in ("hannover", "düsseldorf", "berlin", "frankfurt", "münchen", "check24.de", "holidaycheck.de", "tui.com", "dertour.de"):
            self.assertIn(term.lower(), joined)


if __name__ == "__main__":
    unittest.main()
