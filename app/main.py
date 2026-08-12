import hashlib
import html
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from app.db import has_seen, mark_seen
from app.matcher import score_job
from app.notify import send_telegram
from app.sources import crawl as crawl_source

CONFIG_PATH = Path('/app/config.yaml')


def load_config():
    with CONFIG_PATH.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def fingerprint(source_name: str, title: str, url: str) -> str:
    raw = f'{source_name}|{title.strip().lower()}|{url.strip()}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def fetch_source(source, session, config):
    kind = source.get('type')
    timeout = int(config.get('request_timeout_seconds', 20))
    ua = config.get('user_agent', 'PersonalJobAgent/1.0')
    if kind == 'crawl':
        return crawl_source.fetch(source, session, timeout, ua)
    raise ValueError(f'Unsupported source type: {kind}')


def run_once():
    config = load_config()
    minimum_score = int(config.get('minimum_score', 1))
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
                title = job.get('title', '')
                url = job.get('url', '')
                description = job.get('description', '')
                fp = fingerprint(name, title, url)
                if has_seen(fp):
                    continue
                now = datetime.now(timezone.utc).isoformat()
                mark_seen(fp, name, title, url, now)
                score, matched = score_job(title, description, config)
                if score < minimum_score:
                    continue
                message = (
                    f'NEW JOB — score {score}\n\n'
                    f'{html.unescape(title)}\n'
                    f'Source: {name}\n'
                    f'Matched: {", ".join(matched) or "-"}\n'
                    f'{url}'
                )
                send_telegram(message)


def main():
    while True:
        config = load_config()
        interval = max(1, int(config.get('interval_minutes', 30)))
        print(f'[INFO] scan started {datetime.now(timezone.utc).isoformat()}', flush=True)
        try:
            run_once()
        except Exception as exc:
            print(f'[FATAL-SCAN] {exc}', flush=True)
        time.sleep(interval * 60)


if __name__ == '__main__':
    main()
