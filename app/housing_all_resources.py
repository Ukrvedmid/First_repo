from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup


# Generic searches deliberately avoid a site allow-list. They are the fallback
# for local estate agents, banks, housing companies, owner-direct ads, auction
# pages and any other public/indexed property resource that is not hard-coded.
RENT_ALL_RESOURCE_QUERIES = (
    'Minden Haus mieten Immobilien privat',
    'Minden Haus vermieten privat Eigentümer',
    'Minden Haus Miete Immobilienmakler',
    'Minden Haus Miete Hausverwaltung',
    'Minden Haus Miete Wohnungsunternehmen',
    'Minden Haus Miete Wohnungsgenossenschaft',
    'Minden Haus Miete Sparkasse Immobilien',
    'Minden Haus Miete Volksbank Immobilien',
    'Minden Haus Miete LBS Immobilien',
    'Minden Haus Miete "32423" OR "32425" OR "32427" OR "32429"',
    'Porta Westfalica Haus mieten privat Makler Immobilien',
    'Bückeburg Haus mieten privat Makler Immobilien',
    'Hille Haus mieten privat Makler Immobilien',
    'Petershagen Haus mieten privat Makler Immobilien',
    'Bad Oeynhausen Haus mieten Minden Nähe Immobilien',
    'Minden Haus mieten Kleinanzeigen Portal Makler privat',
    'Minden Haus mieten Facebook Marketplace Immobilien',
    'Minden Haus mieten nebenan Immobilien',
    'Minden Haus mieten markt.de Immobilien',
    'Minden Haus mieten Quoka Immobilien',
)

SALE_ALL_RESOURCE_QUERIES = (
    'Minden Haus kaufen Immobilien privat',
    'Minden Haus zu verkaufen privat Eigentümer',
    'Minden Haus Kauf Immobilienmakler',
    'Minden Haus Kauf Hausverwaltung',
    'Minden Haus Kauf Sparkasse Immobilien',
    'Minden Haus Kauf Volksbank Immobilien',
    'Minden Haus Kauf LBS Immobilien',
    'Minden Haus Kauf Deutsche Bank Immobilien',
    'Minden Haus Kauf Postbank Immobilien',
    'Minden Haus kaufen "32423" OR "32425" OR "32427" OR "32429"',
    'Porta Westfalica Haus kaufen privat Makler Immobilien',
    'Bückeburg Haus kaufen privat Makler Immobilien',
    'Hille Haus kaufen privat Makler Immobilien',
    'Petershagen Haus kaufen privat Makler Immobilien',
    'Minden Haus Zwangsversteigerung Immobilien',
    'Minden Haus ZVG Portal Versteigerung',
    'Minden Haus kaufen Kleinanzeigen Portal Makler privat',
    'Minden Haus kaufen Facebook Marketplace Immobilien',
    'Minden Haus kaufen markt.de Immobilien',
    'Minden Haus kaufen Quoka Immobilien',
)

SEARCH_RESULT_LIMIT = 30
DEEP_FETCH_LIMIT = 50


def _page_text(agent, response) -> tuple[str, str]:
    content_type = (response.headers.get("content-type") or "").lower()
    if "html" not in content_type and content_type:
        return "", ""
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()

    title = ""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = agent.clean_text(og_title.get("content"))
    if not title:
        heading = soup.find("h1")
        if heading:
            title = agent.clean_text(heading.get_text(" ", strip=True))
    if not title and soup.title:
        title = agent.clean_text(soup.title.get_text(" ", strip=True))

    meta_bits = []
    for attrs in (
        {"name": "description"},
        {"property": "og:description"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            meta_bits.append(agent.clean_text(tag.get("content")))

    body = agent.clean_text(soup.get_text(" ", strip=True))
    combined = agent.clean_text(" ".join([title, *meta_bits, body]))
    return title, combined[:18000]


def _listing_from_text(agent, source: str, url: str, title: str, text: str):
    price_match = agent.PRICE_RE.search(text)
    area_match = agent.AREA_RE.search(text)
    rooms_match = agent.ROOMS_RE.search(text)
    location, postcode = agent.extract_location(text)
    return agent.Listing(
        source=source,
        title=(title or text[:180])[:240],
        url=url,
        text=text[:10000],
        location=location,
        postcode=postcode,
        price_eur=agent.parse_number(price_match.group(1)) if price_match else None,
        area_m2=agent.parse_number(area_match.group(1)) if area_match else None,
        rooms=agent.parse_number(rooms_match.group(1)) if rooms_match else None,
    )


def _deep_discovery(agent, session, queries, predicate, source_prefix: str):
    candidates: dict[str, tuple[str, str]] = {}
    for query in queries:
        url = f"https://www.bing.com/search?format=rss&count={SEARCH_RESULT_LIMIT}&q={quote_plus(query)}"
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
            if not link or link in candidates:
                continue
            host = urlparse(link).netloc.lower().removeprefix("www.")
            if host in {"bing.com", "microsoft.com"}:
                continue
            candidates[link] = (title, desc)
        time.sleep(0.25)

    results = []
    for index, (link, (search_title, search_desc)) in enumerate(candidates.items()):
        if index >= DEEP_FETCH_LIMIT:
            break
        host = urlparse(link).netloc.lower().removeprefix("www.") or "unknown"
        fallback_text = agent.clean_text(f"{search_title} {search_desc}")
        fallback_norm = agent.normalize(fallback_text)

        page_title = ""
        page_text = ""
        response = agent.request(session, link)
        if response is not None:
            page_title, page_text = _page_text(agent, response)
        combined = agent.clean_text(f"{fallback_text} {page_text}")
        norm = agent.normalize(combined)

        if not predicate(norm):
            # Dynamic/login-only pages may expose useful text only in the search
            # index. Keep them when the search snippet itself is sufficiently clear.
            if not predicate(fallback_norm):
                continue
            combined = fallback_text

        listing = _listing_from_text(
            agent,
            f"{source_prefix}/{host}",
            link,
            page_title or search_title,
            combined,
        )
        results.append(listing)
        time.sleep(0.2)
    return results


def enable_all_resource_rent(agent) -> None:
    original = agent.bing_discovery

    def all_resource_discovery(session):
        combined = list(original(session))
        combined.extend(
            _deep_discovery(
                agent,
                session,
                RENT_ALL_RESOURCE_QUERIES,
                agent.is_house_offer,
                "WebDeep-Rent",
            )
        )
        unique = {}
        for listing in combined:
            unique.setdefault(listing.url, listing)
        return list(unique.values())

    agent.bing_discovery = all_resource_discovery


def enable_all_resource_sale(sale_agent) -> None:
    original = sale_agent.web_discovery
    agent = sale_agent.h

    def all_resource_discovery(session):
        combined = list(original(session))
        combined.extend(
            _deep_discovery(
                agent,
                session,
                SALE_ALL_RESOURCE_QUERIES,
                sale_agent.is_house_sale,
                "WebDeep-Sale",
            )
        )
        unique = {}
        for listing in combined:
            unique.setdefault(listing.url, listing)
        return list(unique.values())

    sale_agent.web_discovery = all_resource_discovery
