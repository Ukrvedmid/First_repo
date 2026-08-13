import hashlib
import html
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from app.db import has_seen, mark_seen
from app.location import LOCATION_POLICY_VERSION, analyse_germany_location
from app.matcher import analyse_job
from app.notify import send_telegram, telegram_enabled
from app.sources import crawl as crawl_source
from app.sources import workable as workable_source

CONFIG_PATH = Path('/app/config.yaml')
EXTRA_SOURCES_PATH = Path('/app/extra_sources.yaml')
EXTRA_PROFILE_PATH = Path('/app/extra_profile.yaml')
SOURCE_OVERRIDES_PATH = Path('/app/source_overrides.yaml')


def _extend_unique(target: list, values: list) -> None:
    seen = {str(item).casefold() for item in target}
    for value in values:
        key = str(value).casefold()
        if key not in seen:
            target.append(value)
            seen.add(key)


def _merge_source_overrides(config: dict, overrides: list[dict]) -> None:
    """Replace sources with the same name; append genuinely new sources."""
    sources = config.setdefault('sources', [])
    positions = {
        str(source.get('name', '')).casefold(): index
        for index, source in enumerate(sources)
        if source.get('name')
    }

    for override in overrides:
        if not isinstance(override, dict):
            continue
        name = str(override.get('name', '')).strip()
        key = name.casefold()
        if key and key in positions:
            sources[positions[key]] = override
        else:
            positions[key] = len(sources)
            sources.append(override)


def load_config():
    with CONFIG_PATH.open('r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}

    if EXTRA_PROFILE_PATH.exists():
        with EXTRA_PROFILE_PATH.open('r', encoding='utf-8') as f:
            profile = yaml.safe_load(f) or {}

        config.setdefault('keywords', {})
        for group, terms in profile.get('keywords', {}).items():
            target = config['keywords'].setdefault(group, [])
            _extend_unique(target, terms or [])

        location_target = config.setdefault('priority_locations', [])
        _extend_unique(location_target, profile.get('priority_locations', []) or [])

    if EXTRA_SOURCES_PATH.exists():
        with EXTRA_SOURCES_PATH.open('r', encoding='utf-8') as f:
            extra = yaml.safe_load(f) or {}
        config.setdefault('sources', []).extend(extra.get('sources', []))

    if SOURCE_OVERRIDES_PATH.exists():
        with SOURCE_OVERRIDES_PATH.open('r', encoding='utf-8') as f:
            overrides = yaml.safe_load(f) or {}
        _merge_source_overrides(config, overrides.get('sources', []) or [])

    return config


def matching_signature(config: dict) -> str:
    """Change the signature whenever matching settings change.

    This makes existing vacancies get analysed again after the profile is edited,
    while still suppressing duplicates during normal recurring scans.
    """
    relevant = {
        'keywords': config.get('keywords', {}),
        'priority_locations': config.get('priority_locations', []),
        'minimum_score': config.get('minimum_score', 1),
        'location_policy': LOCATION_POLICY_VERSION,
    }
    payload = yaml.safe_dump(relevant, allow_unicode=True, sort_keys=True)
    profile_signature = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]

    # Console-only diagnostics and Telegram delivery keep separate fingerprints.
    # Therefore vacancies printed before Telegram setup are delivered once again
    # when the bot token and chat ID are added later.
    delivery_channel = 'telegram' if telegram_enabled() else 'console'
    return f'{profile_signature}-{delivery_channel}'


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
    if kind == 'workable':
        return workable_source.fetch(source, session, timeout, ua)
    raise ValueError(f'Unsupported source type: {kind}')


def _message_for_match(item: dict) -> str:
    analysis = item['analysis']
    locations = item.get('location') or (
        ', '.join(analysis['locations'][:4]) or 'не определено'
    )
    matched = ', '.join(analysis['matched'][:10]) or '-'
    gaps = '; '.join(analysis.get('potential_gaps', [])[:5]) or 'автоматически не обнаружены'
    recommendation = analysis.get('recommendation', 'Проверить вручную')

    return (
        f"{analysis['tier']} — score {analysis['score']}\n"
        f"Решение: {recommendation}\n\n"
        f"{html.unescape(item['title'])}\n\n"
        f"Маршрут: {analysis['route']}\n"
        f"Локация: {locations}\n"
        f"Фильтр страны: только Германия ✅\n"
        f"Почему подходит: {matched}\n"
        f"Возможные пробелы: {gaps}\n"
        f"Источник: {item['source']}\n\n"
        f"{item['url']}"
    )


def run_once():
    config = load_config()
    minimum_score = int(config.get('minimum_score', 1))
    match_signature = matching_signature(config)
    pending: list[dict] = []
    pending_fingerprints: set[str] = set()
    germany_confirmed = 0
    location_rejected = 0

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
                location = job.get('location', '').strip()
                description = job.get('description', '')
                if not title or not url:
                    continue

                fp = fingerprint(name, title, url, match_signature)
                if fp in pending_fingerprints or has_seen(fp):
                    continue

                now = datetime.now(timezone.utc).isoformat()
                location_result = analyse_germany_location(
                    title,
                    description,
                    location,
                )
                if not location_result['eligible']:
                    location_rejected += 1
                    mark_seen(fp, name, title, url, now)
                    continue

                germany_confirmed += 1
                analysis = analyse_job(title, description, config)

                if analysis['score'] < minimum_score or analysis.get('exclude', False):
                    mark_seen(fp, name, title, url, now)
                    continue

                pending_fingerprints.add(fp)
                pending.append({
                    'fingerprint': fp,
                    'first_seen_at': now,
                    'source': name,
                    'title': title,
                    'url': url,
                    'location': location_result['display'],
                    'analysis': analysis,
                })

    pending.sort(
        key=lambda item: (
            item['analysis']['score'],
            item['title'].casefold(),
        ),
        reverse=True,
    )

    print(
        '[INFO] Germany-only location filter: '
        f'confirmed {germany_confirmed}, rejected {location_rejected}',
        flush=True,
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


def _run_scan_with_logging() -> None:
    print(
        f'[INFO] scan started {datetime.now(timezone.utc).isoformat()}',
        flush=True,
    )
    try:
        run_once()
    except Exception as exc:
        print(f'[FATAL-SCAN] {exc}', flush=True)
        if os.getenv('RUN_ONCE', '').casefold() in {'1', 'true', 'yes'}:
            raise


def main():
    if os.getenv('RUN_ONCE', '').casefold() in {'1', 'true', 'yes'}:
        _run_scan_with_logging()
        return

    while True:
        config = load_config()
        interval = max(1, int(config.get('interval_minutes', 30)))
        _run_scan_with_logging()
        time.sleep(interval * 60)


if __name__ == '__main__':
    main()
