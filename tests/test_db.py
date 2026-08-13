import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db


class SummaryCacheTests(unittest.TestCase):
    def test_summary_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "agent.db"
            summary = {
                "overview": "Короткий опис",
                "duties": ["Обов’язок"],
                "requirements": ["Вимога"],
                "conditions": [],
                "provider": "fallback",
                "model": "rules",
            }
            with patch.object(db, "DB_PATH", database_path):
                self.assertIsNone(db.get_cached_summary("missing"))
                db.save_cached_summary("key-1", summary)
                self.assertEqual(db.get_cached_summary("key-1"), summary)


if __name__ == "__main__":
    unittest.main()
