import unittest

from app import housing_agent
from app import housing_deep_domains as deep


class DeepPropertyDomainTests(unittest.TestCase):
    def test_local_domain_is_crawlable_but_major_portal_is_not(self):
        self.assertFalse(deep._skip_deep_host("immobilien-minden.de"))
        self.assertFalse(deep._skip_deep_host("kellermeier-salge.de"))
        self.assertTrue(deep._skip_deep_host("www.immobilienscout24.de"))
        self.assertTrue(deep._skip_deep_host("immowelt.de"))

    def test_relevant_internal_property_links_are_selected(self):
        self.assertTrue(deep._relevant_link("https://example.de/immobilien/haus-kaufen-minden"))
        self.assertTrue(deep._relevant_link("https://example.de/angebote/einfamilienhaus-123"))
        self.assertTrue(deep._relevant_link("https://example.de/objekt/haus-zur-miete"))
        self.assertTrue(deep._relevant_link("https://example.de/suchen/anzeige-dh-zur-miete-123"))
        self.assertFalse(deep._relevant_link("https://example.de/datenschutz"))
        self.assertFalse(deep._relevant_link("https://example.de/kontakt"))

    def test_verified_regional_and_public_seeds_are_present(self):
        joined_rent = "\n".join(deep.RENT_SEEDS)
        joined_sale = "\n".join(deep.SALE_SEEDS)
        self.assertIn("immobilien-minden.de", joined_rent)
        self.assertIn("kellermeier-salge.de", joined_rent)
        self.assertIn("immobilien.sparkasse.de", joined_sale)
        self.assertIn("zvg-portal.de", joined_sale)
        self.assertIn("immokralle.com", joined_sale)

    def test_canonical_removes_fragment_but_keeps_property_query(self):
        value = deep._canonical("https://Example.de/immobilien/haus?id=7#photos")
        self.assertEqual(value, "https://example.de/immobilien/haus?id=7")

    def test_category_page_is_not_mistaken_for_single_property(self):
        text = "Haus mieten Minden 1.300 € 100 m² 4 Zimmer"
        self.assertFalse(
            deep._likely_detail_page(housing_agent, "https://www.immobilien-minden.de/", text)
        )
        self.assertTrue(
            deep._likely_detail_page(
                housing_agent,
                "https://www.immobilien-minden.de/suchen/anzeige-dh-zur-miete-123/",
                text,
            )
        )


if __name__ == "__main__":
    unittest.main()
