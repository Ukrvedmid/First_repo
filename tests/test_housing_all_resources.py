import unittest

from app import housing_agent
from app import housing_sale_agent
from app.housing_all_resources import (
    RENT_ALL_RESOURCE_QUERIES,
    SALE_ALL_RESOURCE_QUERIES,
    _listing_from_text,
)


class AllPropertyResourcesTests(unittest.TestCase):
    def test_rent_queries_cover_non_portal_resources(self):
        text = "\n".join(RENT_ALL_RESOURCE_QUERIES).lower()
        self.assertIn("privat", text)
        self.assertIn("immobilienmakler", text)
        self.assertIn("hausverwaltung", text)
        self.assertIn("sparkasse", text)
        self.assertIn("volksbank", text)
        self.assertIn("wohnungsunternehmen", text)

    def test_sale_queries_cover_non_portal_resources(self):
        text = "\n".join(SALE_ALL_RESOURCE_QUERIES).lower()
        self.assertIn("privat", text)
        self.assertIn("immobilienmakler", text)
        self.assertIn("sparkasse", text)
        self.assertIn("volksbank", text)
        self.assertIn("lbs", text)
        self.assertIn("zwangsversteigerung", text)

    def test_unknown_domain_listing_is_supported(self):
        listing = _listing_from_text(
            housing_agent,
            "WebDeep-Rent/local-makler.example",
            "https://local-makler.example/objekt/123",
            "Einfamilienhaus in Minden zur Miete",
            "Einfamilienhaus in 32423 Minden zur Miete, 1.450 €, 145 m², 5 Zimmer, Garten und Garage.",
        )
        self.assertEqual(listing.postcode, "32423")
        self.assertEqual(listing.price_eur, 1450)
        self.assertEqual(listing.area_m2, 145)
        self.assertEqual(listing.rooms, 5)
        self.assertTrue(housing_agent.is_house_offer(housing_agent.normalize(listing.text)))

    def test_sale_predicate_accepts_unknown_domain_house_sale(self):
        text = housing_agent.normalize(
            "Einfamilienhaus in 32423 Minden zu verkaufen. Kaufpreis 399.000 €, 155 m², 6 Zimmer."
        )
        self.assertTrue(housing_sale_agent.is_house_sale(text))


if __name__ == "__main__":
    unittest.main()
