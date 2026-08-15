import os
import tempfile
import unittest

from bs4 import BeautifulSoup

import app.housing_agent as h


class HousingAgentTests(unittest.TestCase):
    def test_house_offer_recognizes_generic_house_rental(self):
        self.assertTrue(h.is_house_offer(h.normalize("Schönes Haus 135 m² ab sofort zur Miete")))
        self.assertFalse(h.is_house_offer(h.normalize("Schöne Wohnung 90 m² zur Miete")))

    def test_extract_kleinanzeigen_house_and_reject_wanted_ad(self):
        html = """
        <article>
          <h2>Schönes Haus 130 m² zur Miete</h2>
          <div>32423 Minden 1.250 € 130 m² 5 Zimmer Garten Garage</div>
          <a href="/s-anzeige/haus/123">Details</a>
        </article>
        """
        anchor = BeautifulSoup(html, "html.parser").a
        listing = h.extract_listing("Kleinanzeigen", "https://www.kleinanzeigen.de/", anchor)
        self.assertIsNotNone(listing)
        self.assertEqual(listing.postcode, "32423")
        self.assertEqual(listing.price_eur, 1250)
        self.assertEqual(listing.area_m2, 130)
        self.assertEqual(listing.rooms, 5)

        wanted = """
        <article><h2>Haus zu mieten gesucht</h2><div>32423 Minden</div>
        <a href="/s-anzeige/gesuch/124">Details</a></article>
        """
        self.assertIsNone(
            h.extract_listing(
                "Kleinanzeigen",
                "https://www.kleinanzeigen.de/",
                BeautifulSoup(wanted, "html.parser").a,
            )
        )

    def test_cross_portal_dedupe_key(self):
        a = h.Listing(
            "A", "Haus A", "https://a.example/1", "",
            postcode="32423", price_eur=1500, area_m2=140, rooms=5,
        )
        b = h.Listing(
            "B", "Ganz anderer Titel", "https://b.example/2", "",
            postcode="32423", price_eur=1500, area_m2=140, rooms=5,
        )
        self.assertEqual(h.cross_key(a), h.cross_key(b))
        self.assertNotEqual(h.fingerprint(a), h.fingerprint(b))

    def test_ukrainian_summary_contains_useful_features(self):
        listing = h.Listing(
            "Test", "Haus", "https://example.invalid/1",
            "Einfamilienhaus mit Garten Garage und Einbauküche",
            area_m2=150, rooms=5, distance_km=7.2,
        )
        text = h.ukrainian_summary(listing)
        self.assertIn("Будинок здається в оренду", text)
        self.assertIn("сад", text)
        self.assertIn("гараж", text)
        self.assertIn("7.2 км", text)

    def test_failed_notification_is_not_recorded_as_seen(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = h.DB_PATH
            h.DB_PATH = os.path.join(tmp, "housing.db")
            try:
                db = h.db_connect()
                listing = h.Listing(
                    "Test", "Haus", "https://example.invalid/new",
                    "Haus zur Miete", postcode="32423",
                )
                self.assertEqual(h.seen_reason(db, listing), "new")
                # No record_seen() call simulates a Telegram failure.
                self.assertEqual(h.seen_reason(db, listing), "new")
                h.record_seen(db, listing)
                self.assertEqual(h.seen_reason(db, listing), "same-url")
                db.close()
            finally:
                h.DB_PATH = old_path


if __name__ == "__main__":
    unittest.main()
