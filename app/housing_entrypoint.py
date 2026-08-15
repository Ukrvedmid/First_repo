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


# Reuse the existing Minden Radar .env even if the original bot used a shorter
# Telegram variable name. Never prints or exposes the token/chat id.
_copy_first("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN", "TG_BOT_TOKEN", "BOT_TOKEN")
_copy_first("TELEGRAM_CHAT_ID", "TG_CHAT_ID", "CHAT_ID")

from app import housing_agent  # noqa: E402  (env aliases must be set first)
from app.housing_coverage import enable_broad_coverage  # noqa: E402

# Kleinanzeigen is only one source. Add further public portals plus broad web
# discovery for smaller/local property sites and estate agents.
enable_broad_coverage(housing_agent)


if __name__ == "__main__":
    raise SystemExit(housing_agent.main())
