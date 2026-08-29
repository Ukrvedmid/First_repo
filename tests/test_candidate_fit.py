import unittest

from app.candidate_fit import analyse_candidate_fit


class CandidateFitTests(unittest.TestCase):
    def test_rejects_tesla_mechatroniker(self):
        result = analyse_candidate_fit(
            "Mechatroniker (m/w/d) Tesla Gigafactory",
            "Wartung, Instandhaltung und Fehlersuche an automatisierten Produktionsanlagen in der Fahrzeugproduktion.",
        )
        self.assertFalse(result["eligible"])

    def test_rejects_generic_industrial_service_engineer(self):
        result = analyse_candidate_fit(
            "Field Service Engineer",
            "Commissioning, pumps, hydraulics and maintenance of industrial factory equipment.",
        )
        self.assertFalse(result["eligible"])

    def test_accepts_technical_superintendent_for_chief_engineer(self):
        result = analyse_candidate_fit(
            "Technical Superintendent",
            "Manage vessel machinery and planned maintenance. Chief Engineer certificate and seagoing experience required. Coordinate drydock, repairs and class surveys for the shipping fleet.",
        )
        self.assertTrue(result["eligible"])

    def test_accepts_german_marine_service_role_without_english_phrase(self):
        result = analyse_candidate_fit(
            "Serviceingenieur Schiffsantrieb",
            "Wartung, Reparatur, Fehlersuche und Inbetriebnahme von Schiffsantrieben und Schiffsmaschinen bei Werften und an Bord von Schiffen.",
        )
        self.assertTrue(result["eligible"])

    def test_accepts_sea_to_shore_port_engineer(self):
        result = analyse_candidate_fit(
            "Port Engineer",
            "Technical management of offshore vessels, main engines, generators and propulsion. Previous Chief Engineer or Second Engineer sailing experience preferred.",
        )
        self.assertTrue(result["eligible"])


if __name__ == "__main__":
    unittest.main()
