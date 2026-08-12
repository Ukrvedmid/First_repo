import re
from collections import deque
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup


def _contains_any(value: str, needles: list[str]) -> bool:
    value = value.lower()
    return any(n.lower() in value for n in needles)


def _same_allowed_domain(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or '').lower()
    return any(host == d.lower() or host.endswith('.' + d.lower()) for d in domains)


def _normalise_url(url: str) -> str:
    parsed = urlparse(url)
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
