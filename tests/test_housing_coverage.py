import unittest

from app import housing_agent
from app.housing_coverage import EXTRA_DISCOVERY_QUERIES, EXTRA_SOURCES, enable_broad_coverage


class HousingCoverageTests(unittest.TestCase):
    def test_extra_portals_are_present(self):
        names = {name for name, _ in EXTRA_SOURCES}
        self.assertIn("Immobilien.de", names)
        self.assertIn("Immosuchmaschine-Minden", names)
        self.assertIn("WG-Gesucht", names)

    def test_local_and_generic_discovery_queries_are_present(self):
        joined = "\n".join(EXTRA_DISCOVERY_QUERIES)
        self.assertIn("Immobilienmakler", joined)
        self.assertIn("Sparkasse", joined)
        self.assertIn("Kellermeier & Salge", joined)
        self.assertIn("ORANGE Immobilien", joined)
        self.assertIn("Porta Westfalica", joined)

    def test_enable_broad_coverage_keeps_core_sources_and_adds_more(self):
        class Dummy:
            SOURCES = (("Kleinanzeigen", "https://example.test/k"),)

            @staticmethod
            def looks_like_listing_url(source, href):
                return source == "Kleinanzeigen"

            @staticmethod
            def bing_discovery(session):
                return []

        enable_broad_coverage(Dummy)
        names = {name for name, _ in Dummy.SOURCES}
        self.assertIn("Kleinanzeigen", names)
        self.assertIn("Immobilien.de", names)
        self.assertIn("Immosuchmaschine-Minden", names)

    def test_existing_core_agent_has_major_portals(self):
        names = {name for name, _ in housing_agent.SOURCES}
        self.assertIn("Kleinanzeigen", names)
        self.assertIn("ImmoScout24", names)
        self.assertIn("Immowelt", names)
        self.assertIn("Immonet", names)
        self.assertIn("Meinestadt", names)
        self.assertIn("Ohne-Makler", names)


if __name__ == "__main__":
    unittest.main()
