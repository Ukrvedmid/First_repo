import os
import requests


def send_telegram(text: str):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print(text)
        return
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    r = requests.post(url, json={
        'chat_id': chat_id,
        'text': text[:3900],
        'disable_web_page_preview': False,
    }, timeout=20)
    r.raise_for_status()
