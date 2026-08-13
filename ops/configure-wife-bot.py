#!/usr/bin/env python3
"""Securely connect the wife's Telegram bot to a group chat.

The token is requested with hidden input, validated against Telegram, and stored
only in the local .env file. The script discovers groups/supergroups from recent
Bot API updates, preserves all existing .env settings, sends a test message and
tries to restart only the wife-agent container so the new secrets are loaded.
"""

from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO_DIR = Path("/home/ultbear/job-agent")
ENV_PATH = REPO_DIR / ".env"
API_TIMEOUT_SECONDS = 25


class TelegramAPIError(RuntimeError):
    pass


def api_call(token: str, method: str, params: dict[str, Any] | None = None) -> Any:
    url = f"https://api.telegram.org/bot{token}/{method}"
    encoded = urllib.parse.urlencode(params or {}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={"User-Agent": "JobAgentWifeBotSetup/1.1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise TelegramAPIError(f"Telegram HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise TelegramAPIError(f"Telegram request failed: {exc}") from exc

    if not isinstance(payload, dict) or not payload.get("ok"):
        description = payload.get("description", "unknown Telegram API error") if isinstance(payload, dict) else "invalid response"
        raise TelegramAPIError(str(description))
    return payload.get("result")


def collect_group_chats(updates: Any) -> list[dict[str, Any]]:
    if not isinstance(updates, list):
        return []

    found: dict[int, dict[str, Any]] = {}
    for update in updates:
        if not isinstance(update, dict):
            continue

        chats: list[dict[str, Any]] = []
        for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
            value = update.get(key)
            if isinstance(value, dict) and isinstance(value.get("chat"), dict):
                chats.append(value["chat"])

        for key in ("my_chat_member", "chat_member", "chat_join_request"):
            value = update.get(key)
            if isinstance(value, dict) and isinstance(value.get("chat"), dict):
                chats.append(value["chat"])

        for chat in chats:
            chat_type = str(chat.get("type", ""))
            chat_id = chat.get("id")
            if chat_type not in {"group", "supergroup"} or not isinstance(chat_id, int):
                continue
            found[chat_id] = {
                "id": chat_id,
                "type": chat_type,
                "title": str(chat.get("title") or "Без названия"),
                "update_id": int(update.get("update_id", 0)),
            }

    return sorted(found.values(), key=lambda item: item["update_id"], reverse=True)


def choose_chat(chats: list[dict[str, Any]]) -> dict[str, Any]:
    if len(chats) == 1:
        return chats[0]

    print("Найдено несколько групп. Выберите нужную:")
    for index, chat in enumerate(chats, start=1):
        print(f"  {index}. {chat['title']} ({chat['type']}, ID {chat['id']})")

    while True:
        raw = input(f"Номер группы [1-{len(chats)}]: ").strip()
        try:
            choice = int(raw)
        except ValueError:
            choice = 0
        if 1 <= choice <= len(chats):
            return chats[choice - 1]
        print("Введите корректный номер.")


def update_env(path: Path, values: dict[str, str]) -> None:
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    result: list[str] = []
    written: set[str] = set()

    for line in existing_lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            result.append(line)
            continue

        key = line.split("=", 1)[0].strip()
        if key in values:
            result.append(f"{key}={values[key]}")
            written.add(key)
        else:
            result.append(line)

    if result and result[-1] != "":
        result.append("")
    for key, value in values.items():
        if key not in written:
            result.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(result).rstrip("\n") + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)


def restart_wife_agent() -> bool:
    try:
        completed = subprocess.run(
            ["docker", "compose", "up", "-d", "--build", "--force-recreate", "wife-agent"],
            cwd=REPO_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=240,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Автоперезапуск wife-agent не выполнен: {exc}")
        return False

    if completed.returncode == 0:
        print("wife-agent перезапущен и получил новые Telegram-настройки.")
        return True

    print("Не удалось автоматически перезапустить wife-agent.")
    print("Выполните отдельно:")
    print("  cd /home/ultbear/job-agent && sudo docker compose up -d --build --force-recreate wife-agent")
    return False


def main() -> int:
    print("Подключение второго Telegram-бота для вакансий жены.")
    token = getpass.getpass("Вставьте токен второго бота: ").strip()
    if not token:
        print("Токен не введён.", file=sys.stderr)
        return 1

    try:
        bot = api_call(token, "getMe")
        if not isinstance(bot, dict) or not bot.get("username"):
            raise TelegramAPIError("Telegram did not return the bot username")
        username = str(bot["username"])
        print(f"Бот подтверждён: @{username}")

        # getUpdates and webhooks are mutually exclusive. Preserve pending updates.
        api_call(token, "deleteWebhook", {"drop_pending_updates": "false"})
        updates = api_call(
            token,
            "getUpdates",
            {
                "timeout": "5",
                "allowed_updates": json.dumps(
                    ["message", "edited_message", "my_chat_member", "chat_member"],
                    separators=(",", ":"),
                ),
            },
        )
        chats = collect_group_chats(updates)
        if not chats:
            print()
            print("Группа пока не появилась в обновлениях Telegram.")
            print(f"Отправьте в общей группе команду /start@{username}")
            print("После этого запустите эту программу ещё раз.")
            return 2

        chat = choose_chat(chats)
        update_env(
            ENV_PATH,
            {
                "WIFE_TELEGRAM_BOT_TOKEN": token,
                "WIFE_TELEGRAM_CHAT_ID": str(chat["id"]),
            },
        )

        api_call(
            token,
            "sendMessage",
            {
                "chat_id": str(chat["id"]),
                "text": (
                    "✅ Family Job Agent подключён.\n"
                    "Пошук: Minden + 15 км, вакансії з німецькою не вище B1."
                ),
                "disable_web_page_preview": "true",
            },
        )
    except TelegramAPIError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    print()
    print("ГОТОВО")
    print(f"Бот: @{username}")
    print(f"Группа: {chat['title']}")
    print(f"Chat ID: {chat['id']}")
    print(f"Настройки сохранены в {ENV_PATH} с правами 600.")
    restart_wife_agent()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
