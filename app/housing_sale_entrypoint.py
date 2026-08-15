from __future__ import annotations

import os


def _copy_first(target: str, *sources: str) -> None:
    if os.environ.get(target, "").strip():
        return
    for source in sources:
        value = os.environ.get(source, "").strip()
        if value:
            os.environ[target] = value
            return


# Reuse the existing Minden Radar Telegram settings without exposing secrets.
_copy_first("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN", "TG_BOT_TOKEN", "BOT_TOKEN")
_copy_first("TELEGRAM_CHAT_ID", "TG_CHAT_ID", "CHAT_ID")

from app.housing_sale_agent import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
