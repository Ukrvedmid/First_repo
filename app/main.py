import hashlib
import html
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from app.db import has_seen, mark_seen
from app.matcher import analyse_job
from app.notify import send_telegram, telegram_enabled
from app.sources import crawl as crawl_source

CONFIG_PATH = Path('/app/config.yaml')


def load_config():
    with CONFIG_PATH.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def matching_signature(config: dict) -> str:
    """Change the signature whenever matching settings change.

    This makes existing vacancies get analysed again after the profile is edited,
    while still suppressing duplicates during normal recurring scans.
    """
    relevant = {
        'keywords': config.get('keywords', {}),
        'priority_locations': config.get('priority_locations', []),
        'minimum_score': config.get('minimum_score', 1),
    }
    payload = yaml.safe_dump(relevant, allow_unicode=True, sort_keys=True)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def fingerprint(
    source_name: str,
    title: str,
    url: str,
    match_signature: str,
) -> str:
    raw = (
        f'{match_signature}|{source_name}|'
        f'{title.strip().lower()}|{url.strip()}'
    )
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def fetch_source(source, session, config):
    kind = source.get('type')
    timeout = int(config.get('request_timeout_seconds', 20))
    ua = config.get('user_agent', 'PersonalJobAgent/1.0')
    if kind == 'crawl':
        return crawl_source.fetch(source, session, timeout, ua)
    raise ValueError(f'Unsupported source type: {kind}')


def _message_for_match(item: dict) -> str:
    analysis = item['analysis']
    locations = ', '.join(analysis['locations'][:4]) or 'не определено'
    matched = ', '.join(analysis['matched'][:10]) or '-'

    return (
        f"{analysis['tier']} — score {analysis['score']}\n\n"
        f"{html.unescape(item['title'])}\n\n"
        f"Маршрут: {analysis['route']}\n"
        f"География: {locations}\n"
        f"Почему подходит: {matched}\n"
        f"Источник: {item['source']}\n\n"
        f"{item['url']}"
    )


def run_once():
    config = load_config()
    minimum_score = int(config.get('minimum_score', 1))
    match_signature = matching_signature(config)
    pending: list[dict] = []
    pending_fingerprints: set[str] = set()

    with requests.Session() as session:
        for source in config.get('sources', []):
            if not source.get('enabled', True):
                continue

            name = source.get('name', source.get('url', 'source'))
            try:
                jobs = fetch_source(source, session, config)
            except Exception as exc:
                print(f'[ERROR] {name}: {exc}', flush=True)
                continue

            print(f'[INFO] {name}: fetched {len(jobs)} items', flush=True)

            for job in jobs:
                title = job.get('title', '').strip()
                url = job.get('url', '').strip()
                description = job.get('description', '')
                if not title or not url:
                    continue

                fp = fingerprint(name, title, url, match_signature)
                if fp in pending_fingerprints or has_seen(fp):
                    continue

                analysis = analyse_job(title, description, config)
                now = datetime.now(timezone.utc).isoformat()

                if analysis['score'] < minimum_score or analysis['negative']:
                    mark_seen(fp, name, title, url, now)
                    continue

                pending_fingerprints.add(fp)
                pending.append({
                    'fingerprint': fp,
                    'first_seen_at': now,
                    'source': name,
                    'title': title,
                    'url': url,
                    'analysis': analysis,
                })

    pending.sort(
        key=lambda item: (
            item['analysis']['score'],
            item['title'].casefold(),
        ),
        reverse=True,
    )

    print(f'[INFO] new matching jobs: {len(pending)}', flush=True)
    delay = float(config.get('notification_delay_seconds', 1.1))

    for item in pending:
        try:
            send_telegram(_message_for_match(item))
            mark_seen(
                item['fingerprint'],
                item['source'],
                item['title'],
                item['url'],
                item['first_seen_at'],
            )
            if telegram_enabled() and delay > 0:
                time.sleep(delay)
        except Exception as exc:
            # Do not mark the vacancy seen when delivery fails. It will be retried
            # on the next scan instead of being silently lost.
            print(
                f"[ERROR] notification failed for {item['title']}: {exc}",
                flush=True,
            )


def main():
    while True:
        config = load_config()
        interval = max(1, int(config.get('interval_minutes', 30)))
        print(
            f'[INFO] scan started {datetime.now(timezone.utc).isoformat()}',
            flush=True,
        )
        try:
            run_once()
        except Exception as exc:
            print(f'[FATAL-SCAN] {exc}', flush=True)
        time.sleep(interval * 60)


if __name__ == '__main__':
    main()
