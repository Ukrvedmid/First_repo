from __future__ import annotations

from html import unescape
from typing import Any

from bs4 import BeautifulSoup


def _plain_text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return BeautifulSoup(unescape(value), 'html.parser').get_text(' ', strip=True)
    if isinstance(value, dict):
        return ' '.join(
            part for part in (_plain_text(item) for item in value.values()) if part
        )
    if isinstance(value, (list, tuple, set)):
        return ' '.join(
            part for part in (_plain_text(item) for item in value) if part
        )
    return str(value).strip()


def _location_text(job: dict) -> str:
    location = job.get('location')
    if isinstance(location, dict):
        explicit = location.get('location_str') or location.get('name')
        if explicit:
            return _plain_text(explicit)
        parts = [
            location.get('city'),
            location.get('region') or location.get('state'),
            location.get('country') or location.get('country_name'),
        ]
        return ', '.join(str(part).strip() for part in parts if part)
    if location:
        return _plain_text(location)

    locations = job.get('locations')
    if isinstance(locations, list):
        rendered = []
        for item in locations:
            if not isinstance(item, dict):
                text = _plain_text(item)
            else:
                parts = [
                    item.get('city'),
                    item.get('state_code') or item.get('region'),
                    item.get('country_name') or item.get('country'),
                ]
                text = ', '.join(str(part).strip() for part in parts if part)
            if text:
                rendered.append(text)
        return '; '.join(rendered)

    return ''


def _jobs_from_payload(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ('jobs', 'results', 'positions'):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def fetch(source: dict, session, timeout: int, user_agent: str) -> list[dict]:
    account = str(source['account']).strip()
    endpoint = source.get(
        'api_url',
        f'https://www.workable.com/api/accounts/{account}?details=true',
    )

    response = session.get(
        endpoint,
        timeout=timeout,
        headers={
            'User-Agent': user_agent,
            'Accept': 'application/json',
        },
        allow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()

    jobs: list[dict] = []
    for item in _jobs_from_payload(payload):
        title = _plain_text(item.get('title') or item.get('full_title'))
        shortcode = _plain_text(item.get('shortcode'))
        url = _plain_text(
            item.get('shortlink')
            or item.get('url')
            or item.get('application_url')
        )
        if not url and shortcode:
            url = f'https://apply.workable.com/{account}/j/{shortcode}/'
        if not title or not url:
            continue

        location = _location_text(item)
        description_parts = [
            location,
            _plain_text(item.get('department')),
            _plain_text(item.get('employment_type')),
            _plain_text(item.get('workplace_type')),
            _plain_text(item.get('description')),
            _plain_text(item.get('requirements')),
            _plain_text(item.get('benefits')),
        ]
        description = ' '.join(part for part in description_parts if part)

        jobs.append({
            'title': title[:300],
            'url': url,
            'description': description[:30000],
        })

    return jobs
