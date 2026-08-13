import os

import requests


TELEGRAM_DELIVERY_POLICY_VERSION = "telegram-required-v2"


def telegram_enabled() -> bool:
    """Return True only when both Telegram settings are configured."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    return bool(token and chat_id)


def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    # Never silently treat console output as a successful Telegram delivery.
    # The main loop marks a vacancy as seen only after this function returns.
    # Raising here guarantees that a missing Telegram secret causes a retry on
    # the next scan instead of permanently losing the vacancy notification.
    if not token or not chat_id:
        raise RuntimeError(
            "Telegram delivery is not configured inside the agent container: "
            "TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID is missing"
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text[:3900],
            "disable_web_page_preview": False,
        },
        timeout=20,
    )
    response.raise_for_status()
