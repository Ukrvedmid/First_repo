from collections import deque
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup


def _contains_any(value: str, needles: list[str]) -> bool:
    value = value.lower()
    return any(n.lower() in value for n in needles)


def _same_allowed_domain(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or '').lower()
    return any(host == d.lower() or host.endswith('.' + d.lower()) for d in domains)


def _job_from_page(url: str, response) -> dict:
    soup = BeautifulSoup(response.text, 'html.parser')
    h1 = soup.find('h1')
    title = h1.get_text(' ', strip=True) if h1 else ''
    if not title and soup.title:
        title = soup.title.get_text(' ', strip=True)
    main = soup.find('main') or soup.body or soup
    description = main.get_text(' ', strip=True)
    return {'title': title[:300], 'url': url, 'description': description[:30000]}


def fetch(source: dict, session, timeout: int, user_agent: str) -> list[dict]:
    start_urls = source.get('start_urls') or [source['url']]
    allowed_domains = source.get('allowed_domains') or [urlparse(start_urls[0]).hostname]
    follow_contains = source.get('follow_url_contains', [])
    job_contains = source.get('job_url_contains', [])
    max_pages = int(source.get('max_pages', 80))
    max_jobs = int(source.get('max_jobs', 250))

    queue = deque(start_urls)
    seen = set()
    jobs = []

    while queue and len(seen) < max_pages and len(jobs) < max_jobs:
        url = queue.popleft()
        if url in seen or not _same_allowed_domain(url, allowed_domains):
            continue
        seen.add(url)
        try:
            response = session.get(url, timeout=timeout, headers={'User-Agent': user_agent}, allow_redirects=True)
            response.raise_for_status()
        except Exception as exc:
            print(f'[WARN] crawl fetch failed {url}: {exc}')
            continue

        final_url = response.url
        ctype = response.headers.get('content-type', '')
        if 'text/html' not in ctype and 'application/xhtml' not in ctype:
            continue

        if job_contains and _contains_any(final_url, job_contains):
            job = _job_from_page(final_url, response)
            if job['title']:
                jobs.append(job)
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            candidate = urljoin(final_url, a['href'].split('#', 1)[0])
            if not candidate.startswith(('http://', 'https://')):
                continue
            if not _same_allowed_domain(candidate, allowed_domains):
                continue
            if _contains_any(candidate, job_contains) or _contains_any(candidate, follow_contains):
                if candidate not in seen:
                    queue.append(candidate)

    return jobs
