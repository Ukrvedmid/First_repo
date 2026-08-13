import os

import requests


TELEGRAM_DELIVERY_POLICY_VERSION = "telegram-required-v3-multi-agent"


def telegram_enabled() -> bool:
    """Return True only when both primary Telegram settings are configured."""
    return telegram_env_enabled("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")


def telegram_env_enabled(token_env: str, chat_id_env: str) -> bool:
    token = os.getenv(token_env, "").strip()
    chat_id = os.getenv(chat_id_env, "").strip()
    return bool(token and chat_id)


def send_telegram_to_env(text: str, token_env: str, chat_id_env: str) -> None:
    token = os.getenv(token_env, "").strip()
    chat_id = os.getenv(chat_id_env, "").strip()

    # Never silently treat console output as a successful Telegram delivery.
    # Callers mark vacancies seen only after this function returns successfully.
    if not token or not chat_id:
        raise RuntimeError(
            "Telegram delivery is not configured inside the agent container: "
            f"{token_env} and/or {chat_id_env} is missing"
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


def send_telegram(text: str) -> None:
    send_telegram_to_env(text, "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
