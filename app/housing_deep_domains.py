from __future__ import annotations

import collections
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup


# Major portals are already scanned directly. Deep intra-site crawling is aimed
# at local agents, banks, owner-direct sites, regional portals and other smaller
# public resources discovered dynamically. Avoid hammering large national sites.
SKIP_DEEP_HOST_SUFFIXES = (
    "immobilienscout24.de",
    "immowelt.de",
    "immonet.de",
    "kleinanzeigen.de",
    "immobilien.de",
    "immosuchmaschine.de",
    "wg-gesucht.de",
    "meinestadt.de",
    "ohne-makler.net",
    "bing.com",
    "microsoft.com",
    "google.com",
)

RELEVANT_PATH_TERMS = (
    "immobil",
    "haus",
    "haeuser",
    "miet",
    "kauf",
    "verkauf",
    "objekt",
    "expose",
    "anzeige",
    "angebot",
    "wohnen",
    "einfamilien",
    "doppelhaus",
    "reihenhaus",
    "bungalow",
    "zwangsversteiger",
    "zvg",
)

DETAIL_PATH_TERMS = (
    "expose",
    "objekt",
    "anzeige",
    "property",
    "detail",
    "angebot/",
)

IGNORE_PATH_TERMS = (
    "datenschutz",
    "impressum",
    "kontakt",
    "karriere",
    "jobs",
    "login",
    "anmelden",
    "agb",
    "cookie",
    "privacy",
    "terms",
    "wp-admin",
    "wp-login",
)

GENERIC_CATEGORY_PATHS = {
    "",
    "/",
    "/immobilien",
    "/immobilien/",
    "/immobilien-finden",
    "/immobilien-finden/",
    "/kaufen",
    "/kaufen/",
    "/mieten",
    "/mieten/",
    "/haus-kaufen",
    "/haus-kaufen/",
    "/haus-mieten",
    "/haus-mieten/",
}

# Verified regional/public resources worth seeding even before search-engine
# discovery. Search results still add arbitrary new domains dynamically.
COMMON_SEEDS = (
    "https://www.immobilien-minden.de/",
    "https://www.kellermeier-salge.de/immobilien-finden/",
    "https://immobilien.sparkasse.de/immobilien/nrw/minden.html",
    "https://www.sparkasse-minden-luebbecke.de/de/home/privatkunden/immobilien/immobilie-kaufen.html",
)

RENT_SEEDS = COMMON_SEEDS + (
    "https://www.immobilien-minden.de/",
)

SALE_SEEDS = COMMON_SEEDS + (
    "https://www.zvg-portal.de/",
    "https://www.immokralle.com/immobilien/de/haus%2Bminden%2Bl%C3%BCbbecke",
)

MAX_DOMAINS = 24
MAX_PAGES_PER_DOMAIN = 12
MAX_TOTAL_PAGES = 120
MAX_SITEMAPS_PER_DOMAIN = 4
MAX_SITEMAP_URLS_PER_DOMAIN = 180


def _canonical(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    # Fragments do not identify a different property. Keep functional query
    # strings because some local sites identify an object only by ?id=...
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", "", parsed.query, ""))


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _same_host(a: str, b: str) -> bool:
    return _host(a) == _host(b)


def _skip_deep_host(host: str) -> bool:
    return any(host == suffix or host.endswith("." + suffix) for suffix in SKIP_DEEP_HOST_SUFFIXES)


def _relevant_link(url: str) -> bool:
    parsed = urlparse(url)
    text = f"{parsed.path} {parsed.query}".lower()
    if any(term in text for term in IGNORE_PATH_TERMS):
        return False
    if parsed.path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip", ".mp4", ".mp3")):
        return False
    return any(term in text for term in RELEVANT_PATH_TERMS)


def _likely_detail_page(agent, url: str, text: str) -> bool:
    path = urlparse(url).path.lower()
    if path in GENERIC_CATEGORY_PATHS:
        return False
    if any(term in path for term in DETAIL_PATH_TERMS):
        return True

    # Some small agents use opaque slugs/IDs instead of /expose/ or /objekt/.
    # In that case accept only pages that look like one property, not a results
    # grid containing many prices and areas.
    prices = agent.PRICE_RE.findall(text)
    areas = agent.AREA_RE.findall(text)
    rooms = agent.ROOMS_RE.findall(text)
    depth = len([part for part in path.split("/") if part])
    return (
        depth >= 2
        and 1 <= len(prices) <= 3
        and 1 <= len(areas) <= 3
        and len(rooms) <= 3
    )


def _page_text(agent, response) -> tuple[str, str, BeautifulSoup | None]:
    ctype = (response.headers.get("content-type") or "").lower()
    if ctype and "html" not in ctype and "xhtml" not in ctype:
        return "", "", None
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    title = ""
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        title = agent.clean_text(og.get("content"))
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = agent.clean_text(h1.get_text(" ", strip=True))
    if not title and soup.title:
        title = agent.clean_text(soup.title.get_text(" ", strip=True))
    meta = []
    for attrs in ({"name": "description"}, {"property": "og:description"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            meta.append(agent.clean_text(tag.get("content")))
    body = agent.clean_text(soup.get_text(" ", strip=True))
    return title, agent.clean_text(" ".join([title, *meta, body]))[:22000], soup


def _listing_from_text(agent, source: str, url: str, title: str, text: str):
    price_match = agent.PRICE_RE.search(text)
    area_match = agent.AREA_RE.search(text)
    rooms_match = agent.ROOMS_RE.search(text)
    location, postcode = agent.extract_location(text)
    return agent.Listing(
        source=source,
        title=(title or text[:180])[:240],
        url=url,
        text=text[:12000],
        location=location,
        postcode=postcode,
        price_eur=agent.parse_number(price_match.group(1)) if price_match else None,
        area_m2=agent.parse_number(area_match.group(1)) if area_match else None,
        rooms=agent.parse_number(rooms_match.group(1)) if rooms_match else None,
    )


def _robots_policy(agent, session, base_url: str):
    host = _host(base_url)
    scheme = urlparse(base_url).scheme or "https"
    robots_url = f"{scheme}://{host}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    sitemaps: list[str] = []
    try:
        response = agent.request(session, robots_url)
        if response is not None:
            lines = response.text.splitlines()
            parser.parse(lines)
            for line in lines:
                if line.lower().startswith("sitemap:"):
                    value = line.split(":", 1)[1].strip()
                    if value.startswith(("http://", "https://")):
                        sitemaps.append(value)
        else:
            parser = None
    except Exception:
        parser = None
    return parser, sitemaps


def _can_fetch(parser, user_agent: str, url: str) -> bool:
    if parser is None:
        return True
    try:
        return parser.can_fetch(user_agent, url)
    except Exception:
        return True


def _sitemap_candidates(agent, session, seed: str, explicit_sitemaps: list[str]) -> list[str]:
    parsed = urlparse(seed)
    default_sitemap = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    queue = collections.deque(dict.fromkeys([*explicit_sitemaps, default_sitemap]))
    seen_maps: set[str] = set()
    candidates: list[str] = []

    while queue and len(seen_maps) < MAX_SITEMAPS_PER_DOMAIN and len(candidates) < MAX_SITEMAP_URLS_PER_DOMAIN:
        sitemap_url = queue.popleft()
        if sitemap_url in seen_maps:
            continue
        seen_maps.add(sitemap_url)
        response = agent.request(session, sitemap_url)
        if response is None:
            continue
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            continue
        for loc in root.findall(".//{*}loc"):
            value = (loc.text or "").strip()
            if not value.startswith(("http://", "https://")) or not _same_host(seed, value):
                continue
            if value.lower().endswith(".xml"):
                if len(seen_maps) + len(queue) < MAX_SITEMAPS_PER_DOMAIN:
                    queue.append(value)
                continue
            if _relevant_link(value):
                candidates.append(value)
                if len(candidates) >= MAX_SITEMAP_URLS_PER_DOMAIN:
                    break
    return candidates


def _crawl_domain(agent, session, seed_urls: list[str], predicate, source_prefix: str) -> list:
    if not seed_urls:
        return []
    host = _host(seed_urls[0])
    if not host or _skip_deep_host(host):
        return []

    parser, sitemaps = _robots_policy(agent, session, seed_urls[0])
    queue = collections.deque()
    for url in seed_urls:
        canonical = _canonical(url)
        if canonical:
            queue.append(canonical)
    for url in _sitemap_candidates(agent, session, seed_urls[0], sitemaps):
        canonical = _canonical(url)
        if canonical:
            queue.append(canonical)

    seen: set[str] = set()
    results = []
    pages = 0
    user_agent = getattr(agent, "USER_AGENT", "MindenRadar/1.0")

    while queue and pages < MAX_PAGES_PER_DOMAIN:
        url = queue.popleft()
        if url in seen or not _same_host(seed_urls[0], url):
            continue
        seen.add(url)
        if not _can_fetch(parser, user_agent, url):
            continue
        response = agent.request(session, url)
        if response is None:
            continue
        pages += 1
        title, text, soup = _page_text(agent, response)
        if text and predicate(agent.normalize(text)) and _likely_detail_page(agent, response.url, text):
            results.append(_listing_from_text(agent, f"{source_prefix}/{host}", response.url, title, text))

        if soup is None:
            continue
        for anchor in soup.find_all("a", href=True):
            target = _canonical(urljoin(response.url, anchor.get("href", "")))
            if not target or target in seen or not _same_host(response.url, target):
                continue
            if _relevant_link(target):
                queue.append(target)
    return results


def _deep_domains(agent, session, base_results: list, predicate, source_prefix: str, extra_seeds: tuple[str, ...]):
    seeds_by_host: dict[str, list[str]] = collections.OrderedDict()
    for url in extra_seeds:
        host = _host(url)
        if host and not _skip_deep_host(host):
            seeds_by_host.setdefault(host, []).append(url)
    for listing in base_results:
        url = getattr(listing, "url", "")
        host = _host(url)
        if not host or _skip_deep_host(host):
            continue
        seeds_by_host.setdefault(host, []).append(url)
        if len(seeds_by_host) >= MAX_DOMAINS:
            break

    results = []
    total_pages_estimate = 0
    for host, seeds in list(seeds_by_host.items())[:MAX_DOMAINS]:
        if total_pages_estimate >= MAX_TOTAL_PAGES:
            break
        domain_results = _crawl_domain(agent, session, list(dict.fromkeys(seeds)), predicate, source_prefix)
        results.extend(domain_results)
        total_pages_estimate += MAX_PAGES_PER_DOMAIN
    return results


def enable_deep_domain_rent(agent) -> None:
    original = agent.bing_discovery

    def discovery(session):
        combined = list(original(session))
        combined.extend(_deep_domains(agent, session, combined, agent.is_house_offer, "DomainDeep-Rent", RENT_SEEDS))
        unique = {}
        for listing in combined:
            unique.setdefault(listing.url, listing)
        return list(unique.values())

    agent.bing_discovery = discovery


def enable_deep_domain_sale(sale_agent) -> None:
    original = sale_agent.web_discovery
    agent = sale_agent.h

    def discovery(session):
        combined = list(original(session))
        combined.extend(_deep_domains(agent, session, combined, sale_agent.is_house_sale, "DomainDeep-Sale", SALE_SEEDS))
        unique = {}
        for listing in combined:
            unique.setdefault(listing.url, listing)
        return list(unique.values())

    sale_agent.web_discovery = discovery
