import json
import re
from collections import deque
from html import unescape
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup


def _contains_any(value: str, needles: list[str]) -> bool:
    value = value.lower()
    return any(n.lower() in value for n in needles)


def _same_allowed_domain(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or '').lower()
    return any(host == d.lower() or host.endswith('.' + d.lower()) for d in domains)


def _normalise_url(url: str) -> str:
    # Some career sites render href values with indentation/newlines. Strip them
    # before requests percent-encodes the whitespace into a broken URL.
    cleaned = unescape(str(url)).strip()
    parsed = urlparse(cleaned)
    # Fragments never change the vacancy content and create crawler duplicates.
    return urlunparse(parsed._replace(fragment=''))


def _is_job_url(url: str, source: dict) -> bool:
    pattern = source.get('job_url_regex')
    if pattern:
        return re.search(pattern, url, flags=re.IGNORECASE) is not None

    contains = source.get('job_url_contains', [])
    excludes = source.get('job_url_excludes', [])
    return (
        bool(contains)
        and _contains_any(url, contains)
        and not _contains_any(url, excludes)
    )


def _should_follow(url: str, source: dict) -> bool:
    patterns = source.get('follow_url_contains', [])
    regex = source.get('follow_url_regex')
    return (
        _is_job_url(url, source)
        or _contains_any(url, patterns)
        or (bool(regex) and re.search(regex, url, flags=re.IGNORECASE) is not None)
    )


def _clean_text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return ' '.join(unescape(value).split())
    return ' '.join(str(value).split())


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_text(value)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            result.append(cleaned)
            seen.add(key)
    return result


def _json_type_contains(value, expected: str) -> bool:
    if isinstance(value, str):
        return value.casefold() == expected.casefold()
    if isinstance(value, list):
        return any(_json_type_contains(item, expected) for item in value)
    return False


def _walk_job_postings(value):
    if isinstance(value, dict):
        if _json_type_contains(value.get('@type'), 'JobPosting'):
            yield value
        for child in value.values():
            yield from _walk_job_postings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_job_postings(child)


def _render_country(value) -> str:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        return _clean_text(
            value.get('name')
            or value.get('addressCountry')
            or value.get('identifier')
        )
    return ''


def _render_location(value) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, list):
        return '; '.join(
            part for part in (_render_location(item) for item in value) if part
        )
    if not isinstance(value, dict):
        return _clean_text(value)

    address = value.get('address')
    if address is not None:
        rendered_address = _render_location(address)
        if rendered_address:
            return rendered_address

    parts = [
        _clean_text(value.get('addressLocality') or value.get('city')),
        _clean_text(value.get('addressRegion') or value.get('region')),
        _clean_text(value.get('postalCode')),
        _render_country(
            value.get('addressCountry')
            or value.get('country')
        ),
    ]
    rendered = ', '.join(part for part in parts if part)
    if rendered:
        return rendered

    return _clean_text(value.get('name'))


def _json_ld_locations(soup: BeautifulSoup) -> list[str]:
    locations: list[str] = []
    for script in soup.find_all('script', attrs={'type': re.compile('ld\+json', re.I)}):
        raw = script.string or script.get_text('', strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

        for posting in _walk_job_postings(payload):
            job_location = _render_location(posting.get('jobLocation'))
            if job_location:
                locations.append(job_location)

            applicant_location = _render_location(
                posting.get('applicantLocationRequirements')
            )
            if applicant_location:
                locations.append(applicant_location)

    return _dedupe(locations)


def _meta_locations(soup: BeautifulSoup) -> list[str]:
    names = {
        'job-location',
        'job_location',
        'joblocation',
        'location',
        'twitter:data1',
    }
    properties = {
        'job:location',
        'og:job_location',
        'og:job-location',
    }
    values: list[str] = []
    for meta in soup.find_all('meta'):
        name = _clean_text(meta.get('name')).casefold()
        prop = _clean_text(meta.get('property')).casefold()
        if name in names or prop in properties:
            content = _clean_text(meta.get('content'))
            if content and len(content) <= 200:
                values.append(content)
    return _dedupe(values)


def _dom_locations(root) -> list[str]:
    values: list[str] = []
    location_tokens = (
        'job-location',
        'job_location',
        'joblocation',
        'location-info',
        'location_info',
        'jobgeo',
        'job-geo',
    )

    for node in root.find_all(True):
        attributes = ' '.join(
            [
                _clean_text(node.get('id')),
                _clean_text(' '.join(node.get('class', []))),
                _clean_text(node.get('data-automation-id')),
                _clean_text(node.get('data-testid')),
            ]
        ).casefold()
        if not any(token in attributes for token in location_tokens):
            continue
        text = node.get_text(' ', strip=True)
        if 2 <= len(text) <= 200:
            values.append(text)
        if len(values) >= 10:
            break

    labelled_text = root.get_text('\n', strip=True)
    pattern = re.compile(
        r'(?im)^\s*(?:job\s+location|primary\s+location|work\s+location|'
        r'location|standort|arbeitsort|dienstort|einsatzort)\s*[:\-–—]\s*'
        r'([^\n|•]{2,160})'
    )
    values.extend(match.group(1) for match in pattern.finditer(labelled_text))
    return _dedupe(values)


def _extract_location(soup: BeautifulSoup) -> str:
    root = soup.find('main') or soup.body or soup
    candidates = _dedupe(
        _json_ld_locations(soup)
        + _meta_locations(soup)
        + _dom_locations(root)
    )
    return '; '.join(candidates[:6])


def _job_from_page(url: str, response) -> dict:
    soup = BeautifulSoup(response.text, 'html.parser')
    h1 = soup.find('h1')
    title = h1.get_text(' ', strip=True) if h1 else ''
    if not title and soup.title:
        title = soup.title.get_text(' ', strip=True)
    main = soup.find('main') or soup.body or soup
    description = main.get_text(' ', strip=True)
    return {
        'title': title[:300],
        'url': url,
        'location': _extract_location(soup)[:1000],
        'description': description[:30000],
    }


def fetch(source: dict, session, timeout: int, user_agent: str) -> list[dict]:
    start_urls = source.get('start_urls') or [source['url']]
    allowed_domains = source.get('allowed_domains') or [
        urlparse(start_urls[0]).hostname
    ]
    max_pages = int(source.get('max_pages', 80))
    max_jobs = int(source.get('max_jobs', 250))

    queue = deque(_normalise_url(url) for url in start_urls)
    seen: set[str] = set()
    job_urls: set[str] = set()
    jobs: list[dict] = []

    while queue and len(seen) < max_pages and len(jobs) < max_jobs:
        url = queue.popleft()
        if url in seen or not _same_allowed_domain(url, allowed_domains):
            continue
        seen.add(url)

        try:
            response = session.get(
                url,
                timeout=timeout,
                headers={'User-Agent': user_agent},
                allow_redirects=True,
            )
            response.raise_for_status()
        except Exception as exc:
            print(f'[WARN] crawl fetch failed {url}: {exc}', flush=True)
            continue

        final_url = _normalise_url(response.url)
        content_type = response.headers.get('content-type', '')
        if (
            'text/html' not in content_type
            and 'application/xhtml' not in content_type
        ):
            continue

        if _is_job_url(final_url, source):
            if final_url not in job_urls:
                job = _job_from_page(final_url, response)
                if job['title']:
                    jobs.append(job)
                    job_urls.add(final_url)
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        for anchor in soup.find_all('a', href=True):
            candidate = _normalise_url(urljoin(final_url, anchor['href']))
            if not candidate.startswith(('http://', 'https://')):
                continue
            if not _same_allowed_domain(candidate, allowed_domains):
                continue
            if _should_follow(candidate, source) and candidate not in seen:
                queue.append(candidate)

    return jobs
