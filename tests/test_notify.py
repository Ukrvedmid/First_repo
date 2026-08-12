import os
import unittest
from unittest.mock import patch

from app.notify import telegram_enabled


class TelegramSettingsTests(unittest.TestCase):
    def test_disabled_when_settings_are_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(telegram_enabled())

    def test_disabled_when_only_token_is_present(self):
        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token"},
            clear=True,
        ):
            self.assertFalse(telegram_enabled())

    def test_enabled_when_token_and_chat_id_are_present(self):
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "token",
                "TELEGRAM_CHAT_ID": "12345",
            },
            clear=True,
        ):
            self.assertTrue(telegram_enabled())


if __name__ == "__main__":
    unittest.main()
