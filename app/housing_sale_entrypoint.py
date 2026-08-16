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

from app import housing_sale_agent  # noqa: E402
from app.housing_all_resources import enable_all_resource_sale  # noqa: E402
from app.housing_deep_domains import enable_deep_domain_sale  # noqa: E402

# Search all public/indexed resources, then deeply crawl relevant internal pages
# on dynamically discovered local/regional property domains. Login/CAPTCHA and
# robots restrictions are never bypassed.
enable_all_resource_sale(housing_sale_agent)
enable_deep_domain_sale(housing_sale_agent)


if __name__ == "__main__":
    raise SystemExit(housing_sale_agent.main())
