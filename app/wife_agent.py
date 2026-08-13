import hashlib
import html
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from app.db import has_seen, mark_seen
from app.notify import send_telegram_to_env, telegram_env_enabled
from app.sources import crawl as crawl_source
from app.wife_location import WIFE_LOCATION_POLICY_VERSION, analyse_minden_radius_location
from app.wife_matcher import WIFE_MATCH_POLICY_VERSION, analyse_wife_job
from app.wife_summarizer import (
    WIFE_SUMMARY_POLICY_VERSION,
    effective_wife_summary_provider,
    summarize_wife_job,
    wife_summary_signature,
)

CONFIG_PATH = Path('/app/wife_config.yaml')
TOKEN_ENV = 'WIFE_TELEGRAM_BOT_TOKEN'
CHAT_ENV = 'WIFE_TELEGRAM_CHAT_ID'


def load_config() -> dict:
    with CONFIG_PATH.open('r', encoding='utf-8') as stream:
        return yaml.safe_load(stream) or {}


def _signature(config: dict) -> str:
    material = yaml.safe_dump(
        {
            'profile': config.get('profile', {}),
            'location': config.get('location', {}),
            'minimum_score': config.get('minimum_score', 1),
            'location_policy': WIFE_LOCATION_POLICY_VERSION,
            'match_policy': WIFE_MATCH_POLICY_VERSION,
            'summary_policy': WIFE_SUMMARY_POLICY_VERSION,
            'summary_delivery': wife_summary_signature(),
        },
        allow_unicode=True,
        sort_keys=True,
    )
    return hashlib.sha256(material.encode('utf-8')).hexdigest()[:18]


def _fingerprint(title: str, url: str, signature: str) -> str:
    # Do not include source name: the same vacancy can appear in several search
    # queries on the Bundesagentur site and should still be delivered only once.
    raw = f"wife|{signature}|{title.strip().casefold()}|{url.strip()}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _fetch_source(source: dict, session: requests.Session, config: dict) -> list[dict]:
    kind = source.get('type')
    timeout = int(config.get('request_timeout_seconds', 25))
    ua = config.get('user_agent', 'MindenFamilyJobAgent/1.0')
    if kind == 'crawl':
        return crawl_source.fetch(source, session, timeout, ua)
    raise ValueError(f"Unsupported wife source type: {kind}")


def _trim(value: str, limit: int) -> str:
    text = ' '.join(str(value or '').split())
    if len(text) <= limit:
        return text
    return text[:max(1, limit - 1)].rstrip(' ,;:-') + '…'


def _bullets(items: list[str], max_items: int, limit: int) -> str:
    values = [_trim(item, limit) for item in items[:max_items] if str(item).strip()]
    return '\n'.join(f"• {value}" for value in values)


def _message(item: dict, summary: dict) -> str:
    analysis = item['analysis']
    tier = analysis.get('tier', 'B')
    language = analysis.get('language', {})
    category = analysis.get('category', 'вакансія')

    duties = _bullets(summary.get('duties', []), 4, 220)
    requirements = _bullets(summary.get('requirements', []), 6, 220)
    conditions = _bullets(summary.get('conditions', []), 4, 200)
    gaps = _bullets(analysis.get('gaps', []), 4, 220)

    if tier == 'A':
        decision = 'ПРІОРИТЕТ — варто розглянути'
    else:
        decision = 'ЗАПАСНИЙ ВАРІАНТ — перевірити умови'

    sections = [
        f"👩 {tier} — {category} — {analysis.get('score', 0)} балів",
        f"Рішення: {decision}",
        '',
        f"📌 {_trim(html.unescape(item['title']), 260)}",
        f"📍 {_trim(item['location'], 240)}",
        f"🗣 Німецька: {language.get('level', 'не вказано')}",
        '📏 Пошук: Minden + до 15 км',
        '',
        '📝 Коротко про вакансію:',
        _trim(summary.get('overview', ''), 560),
    ]
    if duties:
        sections.extend(['', '🔧 Що потрібно робити:', duties])
    if requirements:
        sections.extend(['', '🎯 Основні вимоги:', requirements])
    if conditions:
        sections.extend(['', '📋 Умови:', conditions])
    if gaps:
        sections.extend(['', '⚠️ Що перевірити:', gaps])

    matched = ', '.join(analysis.get('matched', [])[:8])
    if matched:
        sections.extend(['', '✅ Чому потрапила у відбір:', _trim(matched, 400)])

    sections.extend([
        '',
        f"Джерело: {item['source']}",
        item['url'],
    ])

    result = '\n'.join(sections)
    if len(result) > 3850:
        result = '\n'.join([
            f"👩 {tier} — {category}",
            f"📌 {_trim(html.unescape(item['title']), 220)}",
            f"📍 {_trim(item['location'], 220)}",
            f"🗣 Німецька: {language.get('level', 'не вказано')}",
            '',
            '📝 Коротко:',
            _trim(summary.get('overview', ''), 480),
            '',
            '🎯 Вимоги:',
            _bullets(summary.get('requirements', []), 4, 180),
            '',
            item['url'],
        ])
    return result


def run_once() -> None:
    config = load_config()
    if not telegram_env_enabled(TOKEN_ENV, CHAT_ENV):
        print(
            '[WARN] Wife agent waiting for Telegram setup: '
            f'{TOKEN_ENV}/{CHAT_ENV} not configured',
            flush=True,
        )
        return

    minimum_score = int(config.get('minimum_score', 5))
    signature = _signature(config)
    pending: list[dict] = []
    pending_keys: set[str] = set()
    local_confirmed = 0
    outside_rejected = 0
    language_rejected = 0
    profile_rejected = 0

    print(
        f"[INFO] Wife agent summary provider: {effective_wife_summary_provider()}",
        flush=True,
    )

    with requests.Session() as session:
        for source in config.get('sources', []):
            if not source.get('enabled', True):
                continue
            name = source.get('name', source.get('url', 'source'))
            try:
                jobs = _fetch_source(source, session, config)
            except Exception as exc:
                print(f"[ERROR] Wife source {name}: {exc}", flush=True)
                continue

            print(f"[INFO] Wife source {name}: fetched {len(jobs)} items", flush=True)
            for job in jobs:
                title = job.get('title', '').strip()
                url = job.get('url', '').strip()
                description = job.get('description', '')
                explicit_location = job.get('location', '').strip()
                if not title or not url:
                    continue

                fp = _fingerprint(title, url, signature)
                if fp in pending_keys or has_seen(fp):
                    continue

                now = datetime.now(timezone.utc).isoformat()
                location = analyse_minden_radius_location(
                    title,
                    description,
                    explicit_location,
                    config,
                )
                if not location['eligible']:
                    outside_rejected += 1
                    mark_seen(fp, name, title, url, now)
                    continue
                local_confirmed += 1

                analysis = analyse_wife_job(title, description, config)
                if analysis.get('exclude', False):
                    if analysis.get('category') == 'німецька вище B1':
                        language_rejected += 1
                    else:
                        profile_rejected += 1
                    mark_seen(fp, name, title, url, now)
                    continue
                if analysis.get('score', 0) < minimum_score:
                    profile_rejected += 1
                    mark_seen(fp, name, title, url, now)
                    continue

                pending_keys.add(fp)
                pending.append({
                    'fingerprint': fp,
                    'first_seen_at': now,
                    'source': name,
                    'title': title,
                    'url': url,
                    'description': description,
                    'location': location['display'],
                    'analysis': analysis,
                })

    pending.sort(key=lambda item: (item['analysis']['score'], item['title'].casefold()), reverse=True)

    print(
        '[INFO] Wife filters: '
        f"local_confirmed={local_confirmed} outside={outside_rejected} "
        f"language_above_B1={language_rejected} profile_rejected={profile_rejected}",
        flush=True,
    )
    print(f"[INFO] Wife new matching jobs: {len(pending)}", flush=True)

    for item in pending:
        try:
            summary = summarize_wife_job(
                item['title'],
                item['description'],
                item['location'],
                item['analysis'].get('language', {}),
            )
            send_telegram_to_env(_message(item, summary), TOKEN_ENV, CHAT_ENV)
            mark_seen(
                item['fingerprint'],
                item['source'],
                item['title'],
                item['url'],
                item['first_seen_at'],
            )
            time.sleep(1.1)
        except Exception as exc:
            print(f"[ERROR] Wife notification failed for {item['title']}: {exc}", flush=True)


def main() -> None:
    while True:
        config = load_config()
        interval = max(1, int(config.get('interval_minutes', 30)))
        print(f"[INFO] Wife scan started {datetime.now(timezone.utc).isoformat()}", flush=True)
        try:
            run_once()
        except Exception as exc:
            print(f"[FATAL-WIFE-SCAN] {exc}", flush=True)
        time.sleep(interval * 60)


if __name__ == '__main__':
    main()
