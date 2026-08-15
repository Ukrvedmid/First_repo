from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus, urlparse


# Extra public property portals. The core agent already covers Kleinanzeigen,
# ImmoScout24, Immowelt, Immonet, Meinestadt and Ohne-Makler. These sources
# broaden direct coverage; the search-discovery layer below additionally finds
# local estate agents and smaller sites that are not practical to hard-code.
EXTRA_SOURCES = (
    ("Immobilien.de", "https://www.immobilien.de/mieten/haus/minden/"),
    ("Immosuchmaschine-Minden", "https://www.immosuchmaschine.de/g/32423-minden/haus-mieten"),
    ("Immosuchmaschine-Kreis", "https://www.immosuchmaschine.de/k/minden-luebbecke/haus-mieten"),
    ("WG-Gesucht", "https://www.wg-gesucht.de/haeuser-in-Minden.87.3.1.0.html"),
)

# These are intentionally redundant. Different search indexes surface different
# portals and local agencies for different wording, so several narrow queries
# improve recall while the core radius/filter/dedupe logic removes noise later.
EXTRA_DISCOVERY_QUERIES = (
    '"Haus zu vermieten" Minden',
    '"Haus zur Miete" Minden',
    '"Einfamilienhaus zur Miete" Minden',
    '"Doppelhaushälfte zur Miete" Minden',
    '"Reihenhaus zur Miete" Minden',
    '"Haus zu vermieten" "Porta Westfalica"',
    '"Haus zur Miete" "Porta Westfalica"',
    '"Haus zur Miete" "Bad Oeynhausen"',
    '"Haus zur Miete" Bückeburg',
    '"Haus zur Miete" Hille',
    '"Haus zur Miete" Petershagen',
    '"Haus mieten" Minden Immobilienmakler',
    '"Haus mieten" Minden Hausverwaltung',
    '"Haus vermieten" Minden Immobilienagentur',
    'site:immobilien.de/mieten/haus Minden',
    'site:immosuchmaschine.de Minden "Haus mieten"',
    'site:wg-gesucht.de Minden "Haus mieten"',
    'site:immobilien.sparkasse.de Minden "Haus" Miete',
    'site:sparkasse-minden-luebbecke.de Minden Immobilien Miete Haus',
    '"Kellermeier & Salge" Minden Haus Miete',
    '"ORANGE Immobilien" Minden Haus Miete',
    '"WeserBergland Immobilien" Minden Haus Miete',
    'Minden Porta Westfalica Haus Miete Immobilien "Makler"',
)


def _extra_listing_url(source: str, href: str) -> bool:
    if not href or href.startswith(("#", "javascript:", "mailto:")):
        return False
    parsed = urlparse(href)
    path = parsed.path.lower()
    lowered = source.lower()

    if lowered.startswith("immobilien.de"):
        return any(token in path for token in ("/expose/", "/immobilie/", "/mieten/haus/"))
    if lowered.startswith("immosuchmaschine"):
        return "/expose/" in path
    if lowered.startswith("wg-gesucht"):
        # Individual offers normally have a numeric id in a .html path.
        return bool(re.search(r"/[^/]*\d{5,}[^/]*\.html$", path))
    return False


def _extra_bing_discovery(agent, session) -> list:
    results = []
    seen_urls: set[str] = set()

    for query in EXTRA_DISCOVERY_QUERIES:
        url = f"https://www.bing.com/search?format=rss&count=30&q={quote_plus(query)}"
        response = agent.request(session, url)
        if response is None:
            continue
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            continue

        for item in root.findall(".//item"):
            title = agent.clean_text(item.findtext("title") or "")
            link = agent.clean_text(item.findtext("link") or "")
            desc = agent.clean_text(item.findtext("description") or "")
            combined = agent.clean_text(f"{title} {desc}")
            norm = agent.normalize(combined)

            if not link or link in seen_urls:
                continue
            if any(agent.normalize(term) in norm for term in agent.REJECT_TERMS):
                continue
            if not agent.is_house_offer(norm):
                continue

            host = urlparse(link).netloc.lower().removeprefix("www.")
            if host in {"bing.com", "microsoft.com"}:
                continue

            price_match = agent.PRICE_RE.search(combined)
            area_match = agent.AREA_RE.search(combined)
            rooms_match = agent.ROOMS_RE.search(combined)
            location, postcode = agent.extract_location(combined)
            results.append(
                agent.Listing(
                    source=f"Web/{host}",
                    title=title[:240],
                    url=link,
                    text=combined[:5000],
                    location=location,
                    postcode=postcode,
                    price_eur=agent.parse_number(price_match.group(1)) if price_match else None,
                    area_m2=agent.parse_number(area_match.group(1)) if area_match else None,
                    rooms=agent.parse_number(rooms_match.group(1)) if rooms_match else None,
                )
            )
            seen_urls.add(link)
        time.sleep(0.35)

    return results


def enable_broad_coverage(agent) -> None:
    """Extend the core housing agent without weakening its 15 km/rental filters."""
    existing_urls = {url for _, url in agent.SOURCES}
    extras = tuple(item for item in EXTRA_SOURCES if item[1] not in existing_urls)
    agent.SOURCES = tuple(agent.SOURCES) + extras

    original_url_matcher = agent.looks_like_listing_url

    def broad_url_matcher(source: str, href: str) -> bool:
        return original_url_matcher(source, href) or _extra_listing_url(source, href)

    agent.looks_like_listing_url = broad_url_matcher

    original_discovery = agent.bing_discovery

    def broad_discovery(session):
        combined = list(original_discovery(session))
        combined.extend(_extra_bing_discovery(agent, session))
        unique = {}
        for listing in combined:
            unique.setdefault(listing.url, listing)
        return list(unique.values())

    agent.bing_discovery = broad_discovery
