import unittest

from app.matcher import analyse_job


TEST_CONFIG = {
    "keywords": {
        "priority": [
            "technical superintendent",
            "field service engineer",
            "project manager",
            "maintenance engineer",
            "fleet manager",
            "schiffbau-ingenieur",
        ],
        "strong": [
            "chief engineer",
            "marine engineering",
            "diesel engine",
            "propulsion",
            "drydock",
            "shipyard",
            "offshore wind",
            "schiffbau",
            "inbetriebnahme",
            "power generation",
        ],
        "bridge": ["servicetechniker"],
        "weak": ["marine", "offshore", "technical", "engineering"],
        "negative": [
            "working student",
            "werkstudent",
            "internship",
            "praktikum",
            "ausbildung",
        ],
        "sea": [
            "chief engineer",
            "rov pilot technician",
            "subsea engineer",
        ],
    },
    "priority_locations": [
        "germany",
        "hamburg",
        "leer",
        "nordrhein-westfalen",
    ],
    "minimum_score": 6,
}


class MatcherTests(unittest.TestCase):
    def test_direct_superintendent_is_top_tier(self):
        result = analyse_job(
            "Technical Superintendent – Offshore Fleet",
            "Hamburg, Germany. Chief Engineer background, drydock, planned "
            "maintenance and marine engineering experience required.",
            TEST_CONFIG,
        )
        self.assertFalse(result["exclude"])
        self.assertGreaterEqual(result["score"], 20)
        self.assertEqual(result["tier"], "A — прямое попадание")
        self.assertEqual(result["route"], "Берег: управление флотом")

    def test_oem_service_role_is_relevant_transition(self):
        result = analyse_job(
            "Field Service Engineer Marine",
            "Service and commissioning of diesel engine and propulsion systems "
            "for customers in Germany and abroad.",
            TEST_CONFIG,
        )
        self.assertFalse(result["exclude"])
        self.assertGreaterEqual(result["score"], TEST_CONFIG["minimum_score"])
        self.assertIn("OEM service", result["route"])

    def test_german_shipbuilding_role_is_ranked(self):
        result = analyse_job(
            "Schiffbau-Ingenieur für Offshore- und Neubau-Projekte",
            "Standort Leer. Schiffbau, Werft, Inbetriebnahme und offshore wind.",
            TEST_CONFIG,
        )
        self.assertFalse(result["exclude"])
        self.assertGreaterEqual(result["score"], TEST_CONFIG["minimum_score"])
        self.assertTrue(result["tier"].startswith("A"))
        self.assertTrue(
            "shipbuilding" in result["route"]
            or "offshore wind" in result["route"]
        )

    def test_chief_engineer_role_remains_in_parallel_search(self):
        result = analyse_job(
            "Chief Engineer – DP2 Offshore Vessel",
            "Marine engineering position on an offshore vessel.",
            TEST_CONFIG,
        )
        self.assertFalse(result["exclude"])
        self.assertEqual(result["tier"], "A — прямое попадание")
        self.assertEqual(result["route"], "Море / offshore")

    def test_generic_software_project_manager_does_not_pass(self):
        result = analyse_job(
            "Project Manager",
            "Lead a consumer software product team and mobile application roadmap.",
            TEST_CONFIG,
        )
        self.assertTrue(result["exclude"])
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["tier"], "X — не морская тематика")

    def test_generic_industrial_service_engineer_is_excluded(self):
        result = analyse_job(
            "Field Service Engineer",
            "Commission diesel engines and power generation equipment at "
            "land-based industrial plants in Germany.",
            TEST_CONFIG,
        )
        self.assertTrue(result["exclude"])
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["route"], "Не морская тематика")

    def test_generic_factory_maintenance_is_excluded(self):
        result = analyse_job(
            "Maintenance Engineer",
            "Maintain packaging machinery and production lines at a food factory.",
            TEST_CONFIG,
        )
        self.assertTrue(result["exclude"])
        self.assertEqual(result["tier"], "X — не морская тематика")

    def test_automotive_fleet_manager_is_excluded(self):
        result = analyse_job(
            "Fleet Manager",
            "Manage a fleet of delivery vans and company cars.",
            TEST_CONFIG,
        )
        self.assertTrue(result["exclude"])
        self.assertEqual(result["score"], 0)

    def test_generic_title_with_shipyard_context_is_included(self):
        result = analyse_job(
            "Project Manager",
            "Lead shipyard retrofit projects for offshore vessels and "
            "coordinate drydock work and sea trials.",
            TEST_CONFIG,
        )
        self.assertFalse(result["exclude"])
        self.assertGreaterEqual(result["score"], TEST_CONFIG["minimum_score"])
        self.assertIn("shipbuilding", result["route"])

    def test_offshore_wind_and_sov_role_is_included(self):
        result = analyse_job(
            "Operations Manager Offshore Wind",
            "Manage SOV-based offshore wind operations in the North Sea.",
            TEST_CONFIG,
        )
        self.assertFalse(result["exclude"])
        self.assertGreaterEqual(result["score"], TEST_CONFIG["minimum_score"])
        self.assertIn("offshore wind", result["route"])

    def test_onshore_wind_role_is_excluded(self):
        result = analyse_job(
            "Wind Turbine Service Engineer",
            "Service onshore wind turbines across southern Germany.",
            TEST_CONFIG,
        )
        self.assertTrue(result["exclude"])
        self.assertEqual(result["score"], 0)

    def test_land_based_chief_engineer_is_excluded(self):
        result = analyse_job(
            "Chief Engineer",
            "Lead maintenance at a land-based combined-cycle power plant.",
            TEST_CONFIG,
        )
        self.assertTrue(result["exclude"])
        self.assertEqual(result["tier"], "X — не морская тематика")

    def test_student_role_is_excluded_by_title(self):
        result = analyse_job(
            "Werkstudent Engineering",
            "Support the technical project team in Hamburg.",
            TEST_CONFIG,
        )
        self.assertTrue(result["exclude"])
        self.assertEqual(result["tier"], "X — исключить")

    def test_closed_vacancy_is_excluded(self):
        result = analyse_job(
            "Field Service Engineer Marine",
            "This job is no longer taking applications.",
            TEST_CONFIG,
        )
        self.assertTrue(result["exclude"])
        self.assertEqual(result["tier"], "X — вакансия закрыта")


if __name__ == "__main__":
    unittest.main()
