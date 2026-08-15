import unittest

from app.wife_location import analyse_minden_radius_location
from app.wife_matcher import analyse_wife_job


CONFIG = {
    "minimum_score": 5,
    "profile": {
        "priority_titles": ["kita assistenz", "schulbegleitung", "betreuungskraft"],
        "bridge_titles": ["reinigungskraft", "lagerhelfer", "produktionshelfer"],
        "positive_terms": ["quereinstieg", "teilzeit", "kita", "betreuung"],
        "language_allowed": [
            "deutsch a1", "deutsch a2", "deutsch b1",
            "grundkenntnisse deutsch", "einfache deutschkenntnisse",
        ],
        "language_reject": [
            "deutsch b2", "deutsch c1", "deutsch c2",
            "sehr gute deutschkenntnisse", "verhandlungssicher deutsch",
        ],
        "negative_titles": ["ausbildung", "teamleitung"],
    },
    "location": {
        "allowed_places": ["minden", "porta westfalica", "bad oeynhausen", "bückeburg"],
        "allowed_postcodes": ["32423", "32457", "32545", "31675"],
    },
}


class WifeAgentPolicyTests(unittest.TestCase):
    def test_priority_childcare_a2_in_minden_is_included(self):
        location = analyse_minden_radius_location(
            "Kita Assistenz",
            "Arbeitsort: Minden. Deutsch A2. Teilzeit, Quereinstieg möglich.",
            "Minden, Westfalen",
            CONFIG,
        )
        self.assertTrue(location["eligible"])

        result = analyse_wife_job(
            "Kita Assistenz",
            "Deutsch A2. Teilzeit, Quereinstieg möglich. Betreuung von Kindern.",
            CONFIG,
        )
        self.assertFalse(result["exclude"])
        self.assertEqual(result["tier"], "A")
        self.assertEqual(result["language"]["level"], "A2")

    def test_b2_job_is_rejected(self):
        result = analyse_wife_job(
            "Schulbegleitung",
            "Für diese Stelle benötigen Sie Deutsch B2.",
            CONFIG,
        )
        self.assertTrue(result["exclude"])
        self.assertEqual(result["category"], "німецька вище B1")

    def test_non_child_helper_job_is_rejected(self):
        result = analyse_wife_job(
            "Reinigungskraft",
            "Quereinstieg möglich. Einfache Deutschkenntnisse. Teilzeit.",
            CONFIG,
        )
        self.assertTrue(result["exclude"])
        self.assertEqual(result["category"], "поза дитячим профілем")

    def test_unrelated_quereinstieg_job_is_rejected(self):
        result = analyse_wife_job(
            "Call Center Agent",
            "Quereinstieg möglich. Deutsch A2.",
            CONFIG,
        )
        self.assertTrue(result["exclude"])
        self.assertEqual(result["category"], "поза профілем")

    def test_outside_radius_location_is_rejected(self):
        result = analyse_minden_radius_location(
            "Kita Assistenz",
            "Kinderbetreuung.",
            "Bielefeld, Germany",
            CONFIG,
        )
        self.assertFalse(result["eligible"])

    def test_local_postcode_is_accepted(self):
        result = analyse_minden_radius_location(
            "Betreuungskraft",
            "Arbeitsort 32457.",
            "32457 Porta Westfalica",
            CONFIG,
        )
        self.assertTrue(result["eligible"])


if __name__ == "__main__":
    unittest.main()
