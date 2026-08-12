import unittest

from app.matcher import analyse_job


TEST_CONFIG = {
    "keywords": {
        "priority": [
            "technical superintendent",
            "field service engineer",
            "project manager",
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
        self.assertIn("shipbuilding", result["route"])

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
        self.assertLess(result["score"], TEST_CONFIG["minimum_score"])

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
