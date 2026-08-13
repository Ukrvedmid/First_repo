import unittest

from app.main import _message_for_match


class TelegramMessageTests(unittest.TestCase):
    def test_message_contains_ukrainian_summary_and_direct_link(self):
        item = {
            "title": "Technical Superintendent",
            "location": "Hamburg, Germany",
            "source": "Example Careers",
            "url": "https://example.com/job/123",
            "analysis": {
                "tier": "A — прямое попадание",
                "score": 31,
                "route": "Берег: управление флотом",
                "recommendation": "ПОДАВАТЬ СРАЗУ",
                "matched": ["technical superintendent", "chief engineer", "drydock"],
                "potential_gaps": [],
            },
        }
        summary = {
            "overview": "Берегова морська роль із технічного управління суднами.",
            "duties": ["Контролювати технічний стан суден."],
            "requirements": ["Досвід роботи Chief Engineer."],
            "conditions": ["Повна зайнятість."],
            "provider": "fallback",
            "model": "rules",
        }

        message = _message_for_match(item, summary)

        self.assertIn("Коротко про вакансію", message)
        self.assertIn("Основні обов’язки", message)
        self.assertIn("Ключові вимоги", message)
        self.assertIn("тільки Німеччина", message)
        self.assertTrue(message.endswith("https://example.com/job/123"))
        self.assertLess(len(message), 4096)


if __name__ == "__main__":
    unittest.main()
