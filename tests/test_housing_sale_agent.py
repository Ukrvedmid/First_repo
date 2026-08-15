import os
import tempfile
import unittest

from bs4 import BeautifulSoup

from app import housing_sale_agent as s


class HousingSaleAgentTests(unittest.TestCase):
    def test_house_sale_is_recognized(self):
        self.assertTrue(s.is_house_sale(s.h.normalize("Einfamilienhaus in Minden zum Kauf 329.000 €")))
        self.assertTrue(s.is_house_sale(s.h.normalize("Haus zu verkaufen in 32423 Minden")))
        self.assertFalse(s.is_house_sale(s.h.normalize("Haus zur Miete in Minden")))
        self.assertFalse(s.is_house_sale(s.h.normalize("Eigentumswohnung zum Kauf in Minden")))
        self.assertFalse(s.is_house_sale(s.h.normalize("Baugrundstück zum Kauf in Minden")))

    def test_extract_sale_listing(self):
        html = """
        <article>
          <h2>Einfamilienhaus zum Kauf</h2>
          <div>32423 Minden 329.000 € 145 m² 5 Zimmer Garten Garage provisionsfrei</div>
          <a href="/expose/123456">Details</a>
        </article>
        """
        listing = s.extract_sale_listing(
            "ImmoScout24-Kauf",
            "https://www.immobilienscout24.de/",
            BeautifulSoup(html, "html.parser").a,
        )
        self.assertIsNotNone(listing)
        self.assertEqual(listing.postcode, "32423")
        self.assertEqual(listing.price_eur, 329000)
        self.assertEqual(listing.area_m2, 145)
        self.assertEqual(listing.rooms, 5)

    def test_sale_radius_default_is_ten_km(self):
        self.assertEqual(s.SALE_RADIUS_KM, 10.0)

    def test_direct_sale_portals_are_broad(self):
        names = {name for name, _ in s.SALE_SOURCES}
        for expected in (
            "Kleinanzeigen-Kauf",
            "ImmoScout24-Kauf",
            "Immowelt-Kauf",
            "Immonet-Kauf",
            "Immobilien.de-Kauf",
            "Immosuchmaschine-Kauf",
        ):
            self.assertIn(expected, names)

    def test_local_agencies_and_sparkasse_are_in_discovery(self):
        queries = "\n".join(s.SALE_DISCOVERY_QUERIES).lower()
        self.assertIn("immobilien.sparkasse.de", queries)
        self.assertIn("kellermeier & salge", queries)
        self.assertIn("orange immobilien", queries)
        self.assertIn("weserbergland immobilien", queries)
        self.assertIn("immobilienmakler", queries)

    def test_sale_dedupe_is_separate_and_cross_portal(self):
        a = s.h.Listing(
            "A", "Haus A", "https://a.example/1", "",
            postcode="32423", price_eur=350000, area_m2=150, rooms=5,
        )
        b = s.h.Listing(
            "B", "Haus B", "https://b.example/2", "",
            postcode="32423", price_eur=350000, area_m2=150, rooms=5,
        )
        self.assertEqual(s.cross_key(a), s.cross_key(b))
        self.assertNotEqual(s.fingerprint(a), s.fingerprint(b))

        with tempfile.TemporaryDirectory() as tmp:
            old_path = s.DB_PATH
            s.DB_PATH = os.path.join(tmp, "sale.db")
            try:
                db = s.db_connect()
                self.assertEqual(s.seen_reason(db, a), "new")
                s.record_seen(db, a)
                self.assertEqual(s.seen_reason(db, a), "same-url")
                self.assertEqual(s.seen_reason(db, b), "cross-portal")
                db.close()
            finally:
                s.DB_PATH = old_path

    def test_ukrainian_sale_summary(self):
        listing = s.h.Listing(
            "Test", "Haus zum Kauf", "https://example.invalid/1",
            "Einfamilienhaus mit Garten Garage provisionsfrei modernisiert",
            area_m2=150, rooms=5, distance_km=6.4,
        )
        summary = s.ukrainian_summary(listing)
        self.assertIn("Будинок продається", summary)
        self.assertIn("без комісії покупця", summary)
        self.assertIn("6.4 км", summary)


if __name__ == "__main__":
    unittest.main()
