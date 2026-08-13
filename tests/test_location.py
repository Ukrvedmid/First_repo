import unittest

from app.location import analyse_germany_location


class GermanyLocationPolicyTests(unittest.TestCase):
    def test_accepts_structured_hamburg_germany(self):
        result = analyse_germany_location(
            "Technical Superintendent",
            "Marine fleet management role.",
            "Hamburg, Germany",
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["display"], "Hamburg, Germany")

    def test_accepts_structured_german_city_without_country(self):
        result = analyse_germany_location(
            "Marine Service Engineer",
            "Service of ship propulsion equipment.",
            "Spay",
        )
        self.assertTrue(result["eligible"])

    def test_rejects_mumbai_even_if_description_mentions_germany(self):
        result = analyse_germany_location(
            "Marine Project Engineer",
            "Work with customers in Germany and other European markets.",
            "Mumbai, India",
        )
        self.assertFalse(result["eligible"])

    def test_rejects_spain_location(self):
        result = analyse_germany_location(
            "Technical Superintendent",
            "Offshore vessel management.",
            "Madrid, Spain",
        )
        self.assertFalse(result["eligible"])

    def test_rejects_remote_europe_without_germany(self):
        result = analyse_germany_location(
            "Marine Surveyor",
            "Remote role covering Europe.",
            "Remote - Europe",
        )
        self.assertFalse(result["eligible"])

    def test_accepts_remote_germany(self):
        result = analyse_germany_location(
            "Marine Surveyor",
            "Remote maritime inspection role.",
            "Remote, Germany",
        )
        self.assertTrue(result["eligible"])

    def test_accepts_germany_in_title_when_structured_location_missing(self):
        result = analyse_germany_location(
            "Field Service Engineer Marine - Hamburg",
            "Commissioning of marine propulsion systems.",
            "",
        )
        self.assertTrue(result["eligible"])

    def test_accepts_labelled_german_location_near_top(self):
        result = analyse_germany_location(
            "Project Manager Shipbuilding",
            "Location: Kiel, Schleswig-Holstein. Lead shipyard retrofit projects.",
            "",
        )
        self.assertTrue(result["eligible"])

    def test_rejects_unknown_location(self):
        result = analyse_germany_location(
            "Technical Superintendent",
            "Manage a global offshore fleet and travel internationally.",
            "",
        )
        self.assertFalse(result["eligible"])

    def test_late_footer_reference_to_germany_does_not_pass(self):
        description = (
            "Marine role based in Mumbai, India. "
            + ("Operational responsibilities. " * 80)
            + "Our company also has an office in Germany."
        )
        result = analyse_germany_location(
            "Marine Engineer",
            description,
            "",
        )
        self.assertFalse(result["eligible"])


if __name__ == "__main__":
    unittest.main()
