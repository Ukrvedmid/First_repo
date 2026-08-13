import os
import unittest
from unittest.mock import patch

from app.summarizer import (
    _extract_output_text,
    _fallback_summary,
    _normalise_summary,
    effective_summary_provider,
    summary_delivery_signature,
)


class SummarizerTests(unittest.TestCase):
    def test_fallback_summary_is_ukrainian_and_structured(self):
        analysis = {
            "route": "Берег: управление флотом",
            "potential_gaps": [],
        }
        summary = _fallback_summary(
            "Technical Superintendent",
            "Hamburg, Germany. Chief Engineer qualification required. "
            "Manage planned maintenance, drydock, class and spare parts. "
            "Very good English and willingness to travel.",
            "Hamburg, Germany",
            analysis,
        )

        self.assertEqual(summary["provider"], "fallback")
        self.assertIn("Німеччині", summary["overview"])
        self.assertIn("технічний суперінтендант", summary["overview"].casefold())
        self.assertGreaterEqual(len(summary["duties"]), 2)
        self.assertTrue(any("Chief Engineer" in item for item in summary["requirements"]))
        self.assertTrue(any("англійська" in item.casefold() for item in summary["requirements"]))

    def test_auto_provider_uses_fallback_without_api_key(self):
        with patch.dict(os.environ, {"JOB_SUMMARY_PROVIDER": "auto"}, clear=True):
            self.assertEqual(effective_summary_provider(), "fallback")
            self.assertIn(":fallback:rules", summary_delivery_signature())

    def test_auto_provider_uses_openai_with_api_key(self):
        with patch.dict(
            os.environ,
            {
                "JOB_SUMMARY_PROVIDER": "auto",
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "gpt-5-nano",
            },
            clear=True,
        ):
            self.assertEqual(effective_summary_provider(), "openai")
            self.assertIn(":openai:gpt-5-nano", summary_delivery_signature())

    def test_extracts_responses_api_output_text(self):
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"overview":"Коротко","duties":[],"requirements":[],"conditions":[]}',
                        }
                    ],
                }
            ]
        }
        text = _extract_output_text(payload)
        self.assertIn('"overview":"Коротко"', text)

    def test_normalises_and_limits_summary_fields(self):
        payload = {
            "overview": "  Стисле пояснення вакансії українською мовою.  ",
            "duties": ["Обов’язок 1"] * 8,
            "requirements": ["Вимога 1", "Вимога 2"],
            "conditions": ["Умова 1"],
        }
        result = _normalise_summary(payload, "openai", "gpt-5-nano")
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(len(result["duties"]), 1)
        self.assertTrue(result["duties"][0].endswith("."))


if __name__ == "__main__":
    unittest.main()
