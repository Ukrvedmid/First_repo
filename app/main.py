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
from app.summarizer import (
    SUMMARY_POLICY_VERSION,
    effective_summary_provider,
    summarize_job,
    summary_delivery_signature,
    translate_gap_to_ukrainian,
)

CONFIG_PATH = Path('/app/config.yaml')
EXTRA_SOURCES_PATH = Path('/app/extra_sources.yaml')
EXTRA_PROFILE_PATH = Path('/app/extra_profile.yaml')
SOURCE_OVERRIDES_PATH = Path('/app/source_overrides.yaml')

_TIER_UK = {
    'A — прямое попадание': 'A — пряме попадання',
    'A — высокая релевантность': 'A — висока релевантність',
    'B — хороший переход в морскую береговую роль': 'B — хороший перехід на морську берегову роль',
    'C — морская смежная': 'C — суміжна морська вакансія',
}

_ROUTE_UK = {
    'Море / offshore': 'Море / offshore',
    'Берег: морской класс, survey и инспекции': 'Берег: морський class, survey та інспекції',
    'Берег: управление флотом': 'Берег: технічне управління флотом',
    'Берег: shipbuilding, судоремонт и морские проекты': 'Берег: shipbuilding, судноремонт і морські проєкти',
    'Берег / ротация: offshore wind, SOV и marine operations': 'Берег / ротація: offshore wind, SOV і marine operations',
    'Берег / выезды: marine OEM service и commissioning': 'Берег / виїзди: marine OEM service і commissioning',
    'Берег: другая морская инженерная роль': 'Берег: інша морська інженерна роль',
}

_RECOMMENDATION_UK = {
    'ПОДАВАТЬ СРАЗУ': 'ПОДАВАТИСЯ ОДРАЗУ',
    'ПОДАВАТЬ, закрыв пробелы в CV/письме': 'ПОДАВАТИСЯ, пояснив прогалини у CV або супровідному листі',
    'РАССМОТРЕТЬ КАК ПЕРЕХОД НА МОРСКУЮ РАБОТУ НА БЕРЕГУ': 'РОЗГЛЯНУТИ ЯК ПЕРЕХІД НА МОРСЬКУ РОБОТУ НА БЕРЕЗІ',
    'РЕЗЕРВ — проверка вручную': 'РЕЗЕРВ — перевірити вручну',
}


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
    """Change the signature whenever matching or delivery settings change."""
    relevant = {
        'keywords': config.get('keywords', {}),
        'priority_locations': config.get('priority_locations', []),
        'minimum_score': config.get('minimum_score', 1),
        'location_policy': LOCATION_POLICY_VERSION,
        'summary_policy': SUMMARY_POLICY_VERSION,
        'summary_delivery': summary_delivery_signature(),
    }
    payload = yaml.safe_dump(relevant, allow_unicode=True, sort_keys=True)
    profile_signature = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]

    # Console-only diagnostics and Telegram delivery keep separate fingerprints.
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


def _trim(value: str, limit: int) -> str:
    text = ' '.join(str(value or '').split())
    if len(text) <= limit:
        return text
    return text[:max(1, limit - 1)].rstrip(' ,;:-') + '…'


def _bullet_block(items: list[str], max_items: int, item_limit: int) -> str:
    selected = [_trim(item, item_limit) for item in items[:max_items] if str(item).strip()]
    return '\n'.join(f'• {item}' for item in selected)


def _message_for_match(item: dict, summary: dict) -> str:
    analysis = item['analysis']
    location = item.get('location') or 'не визначено'
    tier = _TIER_UK.get(analysis.get('tier', ''), analysis.get('tier', ''))
    route = _ROUTE_UK.get(analysis.get('route', ''), analysis.get('route', ''))
    recommendation = _RECOMMENDATION_UK.get(
        analysis.get('recommendation', ''),
        analysis.get('recommendation', 'Перевірити вручну'),
    )

    duties = _bullet_block(summary.get('duties', []), 3, 230)
    requirements = _bullet_block(summary.get('requirements', []), 5, 230)
    conditions = _bullet_block(summary.get('conditions', []), 3, 190)
    matched = ', '.join(analysis.get('matched', [])[:9]) or 'морський профіль вакансії'
    gaps = [
        translate_gap_to_ukrainian(gap)
        for gap in analysis.get('potential_gaps', [])[:4]
    ]
    gaps_text = _bullet_block(gaps, 4, 210) or '• Критичних прогалин автоматично не виявлено.'

    sections = [
        f"{tier} — {analysis.get('score', 0)} балів",
        f"Рішення: {recommendation}",
        '',
        f"📌 {_trim(html.unescape(item['title']), 260)}",
        f"📍 {location}",
        f"🧭 {route}",
        '',
        '📝 Коротко про вакансію:',
        _trim(summary.get('overview', ''), 560),
    ]
    if duties:
        sections.extend(['', '🔧 Основні обов’язки:', duties])
    if requirements:
        sections.extend(['', '🎯 Ключові вимоги:', requirements])
    if conditions:
        sections.extend(['', '📋 Умови роботи:', conditions])

    sections.extend([
        '',
        '✅ Чому вам підходить:',
        _trim(matched, 430),
        '',
        '⚠️ Що перевірити:',
        gaps_text,
        '',
        '🇩🇪 Локація підтверджена: тільки Німеччина',
        f"Джерело: {item['source']}",
        item['url'],
    ])

    message = '\n'.join(section for section in sections if section is not None)
    # Telegram's limit is 4096 characters. Keep the direct link intact at the end.
    if len(message) > 3850:
        compact_sections = [
            f"{tier} — {analysis.get('score', 0)} балів",
            f"Рішення: {recommendation}",
            '',
            f"📌 {_trim(html.unescape(item['title']), 220)}",
            f"📍 {location}",
            '',
            '📝 Коротко про вакансію:',
            _trim(summary.get('overview', ''), 480),
            '',
            '🔧 Основні обов’язки:',
            _bullet_block(summary.get('duties', []), 3, 180),
            '',
            '🎯 Ключові вимоги:',
            _bullet_block(summary.get('requirements', []), 4, 180),
            '',
            f"Джерело: {item['source']}",
            item['url'],
        ]
        message = '\n'.join(compact_sections)
    return message


def run_once():
    config = load_config()
    minimum_score = int(config.get('minimum_score', 1))
    match_signature = matching_signature(config)
    pending: list[dict] = []
    pending_fingerprints: set[str] = set()
    germany_confirmed = 0
    location_rejected = 0

    print(
        f"[INFO] Ukrainian summary provider: {effective_summary_provider()}",
        flush=True,
    )

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
                    'description': description,
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
            summary = summarize_job(
                item['title'],
                item['description'],
                item['location'],
                item['analysis'],
            )
            print(
                '[INFO] Ukrainian summary ready: '
                f"provider={summary.get('provider')} cached={summary.get('cached', False)} "
                f"title={item['title']}",
                flush=True,
            )
            send_telegram(_message_for_match(item, summary))
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
