from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app import housing_agent as h

HOME_CITY = os.getenv("RADAR_HOME_CITY", "Minden").strip() or "Minden"
HOME_LAT = float(os.getenv("RADAR_HOME_LAT", "52.2895"))
HOME_LON = float(os.getenv("RADAR_HOME_LON", "8.9146"))
SALE_RADIUS_KM = float(os.getenv("HOUSING_SALE_RADIUS_KM", "10"))
SCAN_INTERVAL_SECONDS = max(900, int(os.getenv("HOUSING_SALE_SCAN_INTERVAL_SECONDS", "1800")))
DB_PATH = os.getenv("HOUSING_SALE_DB_PATH", "/data/housing-sale.db")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
HTTP_TIMEOUT = max(8, int(os.getenv("HOUSING_HTTP_TIMEOUT_SECONDS", "20")))
MAX_ITEMS_PER_SCAN = max(10, int(os.getenv("HOUSING_SALE_MAX_ITEMS_PER_SCAN", "120")))
MAX_NOTIFICATIONS_PER_SCAN = max(1, int(os.getenv("HOUSING_SALE_MAX_NOTIFICATIONS_PER_SCAN", "15")))
USER_AGENT = os.getenv("HOUSING_USER_AGENT", "MindenRadar/1.0 (+personal property monitor)")

SALE_HOUSE_TERMS = (
    "haus", "einfamilienhaus", "doppelhaushälfte", "doppelhaushaelfte", "doppelhaus",
    "reihenhaus", "reihenmittelhaus", "reiheneckhaus", "bungalow", "stadthaus",
    "landhaus", "bauernhaus", "wohnhaus", "zweifamilienhaus", "mehrfamilienhaus",
    "haushälfte", "haushaelfte", "villa",
)
SALE_TERMS = (
    "zum kauf", "zu verkaufen", "verkaufen", "verkauf", "kaufen", "kaufpreis",
    "hauskauf", "eigentum", "provisionsfrei",
)
SALE_REJECT_TERMS = (
    "mietgesuch", "gesucht zur miete", "haus gesucht", "wohnung gesucht",
    "haus zur miete", "haus mieten", "zu vermieten", "zur miete", "mietkauf",
    "ferienhaus mieten", "ferienwohnung", "wohnung zum kauf", "eigentumswohnung",
    "grundstück zum kauf", "grundstueck zum kauf", "baugrundstück", "baugrundstueck",
)

FEATURES = h.FEATURES | {
    "provisionsfrei": "без комісії покупця",
    "einliegerwohnung": "окрема додаткова квартира",
    "mehrfamilienhaus": "багатоквартирний будинок",
    "zweifamilienhaus": "будинок на дві сім’ї",
    "sanierungsbedürftig": "потребує ремонту",
    "sanierungsbeduerftig": "потребує ремонту",
    "modernisiert": "модернізований",
    "neubau": "новобудова",
}

# Direct portals. The web-discovery layer below supplements these with local agents,
# banks and any other indexed property site. No anti-bot protection is bypassed.
SALE_SOURCES = (
    ("Kleinanzeigen-Kauf", "https://www.kleinanzeigen.de/s-haus-kaufen/minden/sortierung:entfernung/haus/k0c208l1760r10"),
    ("ImmoScout24-Kauf", "https://www.immobilienscout24.de/Suche/de/nordrhein-westfalen/minden-luebbecke-kreis/minden/haus-kaufen"),
    ("ImmoScout24-Kreis-Kauf", "https://www.immobilienscout24.de/Suche/de/nordrhein-westfalen/minden-luebbecke-kreis/haus-kaufen"),
    ("Immowelt-Kauf", "https://www.immowelt.de/suche/kaufen/haus/nordrhein-westfalen/minden-32423/ad08de2409"),
    ("Immonet-Kauf", "https://www.immonet.de/suchen/kauf/haus/nordrhein-westfalen/minden-32423/ad08de2409"),
    ("Meinestadt-Kauf", "https://www.meinestadt.de/minden-westfalen/immobilien/haus-kaufen"),
    ("Ohne-Makler-Kauf", "https://www.ohne-makler.net/immobilien/haus-kaufen/nordrhein-westfalen/minden/"),
    ("Immobilien.de-Kauf", "https://www.immobilien.de/kaufen/haus/minden/"),
    ("Immosuchmaschine-Kauf", "https://www.immosuchmaschine.de/g/32423-minden/haus-kaufen"),
)

SALE_DISCOVERY_QUERIES = (
    '"Haus kaufen" Minden',
    '"Haus zu verkaufen" Minden',
    '"Einfamilienhaus" "zum Kauf" Minden',
    '"Doppelhaushälfte" "zum Kauf" Minden',
    '"Reihenhaus" "zum Kauf" Minden',
    '"Bungalow" "zum Kauf" Minden',
    '"Haus kaufen" "Porta Westfalica"',
    '"Haus kaufen" Bückeburg',
    '"Haus kaufen" Petershagen Minden',
    '"Haus kaufen" Minden Immobilienmakler',
    '"Haus kaufen" Minden Immobilienagentur',
    '"Haus kaufen" Minden Hausverwaltung',
    'site:immobilienscout24.de/expose Minden "Haus" "Kauf"',
    'site:immowelt.de Minden "Haus kaufen"',
    'site:immonet.de Minden "Haus kaufen"',
    'site:immobilien.de/kaufen/haus Minden',
    'site:immosuchmaschine.de Minden "Haus kaufen"',
    'site:immobilien.sparkasse.de/expose Minden Haus',
    'site:immobilien.sparkasse.de/expose "Porta Westfalica" Haus',
    'site:sparkasse-minden-luebbecke.de Immobilien Haus Minden Verkauf',
    'site:spkbopw.de Immobilien Haus Porta Westfalica Kauf',
    '"Kellermeier & Salge" Minden Haus Kauf',
    '"ORANGE Immobilien" Minden Haus Kauf',
    '"WeserBergland Immobilien" Minden Haus Kauf',
    '"LBS Immobilien" Minden Haus Kauf',
    'Minden Haus kaufen Makler Immobilien "32423"',
    'Minden Haus kaufen Makler Immobilien "32425"',
    'Minden Haus kaufen Makler Immobilien "32427"',
    'Minden Haus kaufen Makler Immobilien "32429"',
)


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {message}", flush=True)


def db_connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        """CREATE TABLE IF NOT EXISTS seen_sale_listings (
               fingerprint TEXT PRIMARY KEY,
               cross_key TEXT,
               source TEXT NOT NULL,
               title TEXT NOT NULL,
               url TEXT NOT NULL,
               first_seen TEXT NOT NULL,
               last_seen TEXT NOT NULL
           )"""
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_seen_sale_cross_key ON seen_sale_listings(cross_key)")
    db.execute(
        """CREATE TABLE IF NOT EXISTS geocode_cache (
               query TEXT PRIMARY KEY,
               lat REAL,
               lon REAL,
               updated_at TEXT NOT NULL
           )"""
    )
    db.commit()
    return db


def is_house_sale(normalized_text: str) -> bool:
    if any(h.normalize(term) in normalized_text for term in SALE_REJECT_TERMS):
        return False
    has_house = any(h.normalize(term) in normalized_text for term in SALE_HOUSE_TERMS)
    has_sale = any(h.normalize(term) in normalized_text for term in SALE_TERMS)
    return has_house and has_sale


def looks_like_sale_url(source: str, href: str) -> bool:
    if not href or href.startswith(("#", "javascript:", "mailto:")):
        return False
    path = urlparse(href).path.lower()
    lowered = source.lower()
    if lowered.startswith("kleinanzeigen"):
        return "/s-anzeige/" in path
    if lowered.startswith("immoscout24"):
        return "/expose/" in path
    if lowered.startswith("immowelt"):
        return "/expose/" in path
    if lowered.startswith("immonet"):
        return any(token in path for token in ("/expose/", "/angebot/", "/immobilie/"))
    if lowered.startswith("meinestadt"):
        return "/expose/" in path
    if lowered.startswith("ohne-makler"):
        return any(token in path for token in ("/immobilie/", "/property/"))
    if lowered.startswith("immobilien.de"):
        return any(token in path for token in ("/expose/", "/immobilie/"))
    if lowered.startswith("immosuchmaschine"):
        return "/expose/" in path
    return False


def extract_sale_listing(source: str, base_url: str, anchor) -> h.Listing | None:
    href = h.clean_text(anchor.get("href", ""))
    if not href:
        return None
    url = urljoin(base_url, href)
    title = h.clean_text(anchor.get("title", "") or anchor.get_text(" ", strip=True))
    card = h.closest_card_text(anchor)
    if len(title) < 5:
        parent = anchor.parent
        heading = parent.find(["h2", "h3", "h4"]) if parent else None
        if heading:
            title = h.clean_text(heading.get_text(" ", strip=True))
    if len(title) < 5:
        title = card[:180]
    combined = h.clean_text(f"{title} {card}")
    norm = h.normalize(combined)
    if not is_house_sale(norm):
        return None
    price_match = h.PRICE_RE.search(combined)
    area_match = h.AREA_RE.search(combined)
    rooms_match = h.ROOMS_RE.search(combined)
    distance_match = h.DISTANCE_RE.search(combined)
    location, postcode = h.extract_location(combined)
    return h.Listing(
        source=source,
        title=title[:240],
        url=url,
        text=combined[:5000],
        location=location,
        postcode=postcode,
        price_eur=h.parse_number(price_match.group(1)) if price_match else None,
        area_m2=h.parse_number(area_match.group(1)) if area_match else None,
        rooms=h.parse_number(rooms_match.group(1)) if rooms_match else None,
        distance_km=h.parse_number(distance_match.group(1)) if distance_match else None,
    )


def parse_sale_page(source: str, url: str, html_text: str) -> list[h.Listing]:
    soup = BeautifulSoup(html_text, "html.parser")
    listings: list[h.Listing] = []
    seen_urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        if not looks_like_sale_url(source, href):
            continue
        listing = extract_sale_listing(source, url, anchor)
        if listing and listing.url not in seen_urls:
            listings.append(listing)
            seen_urls.add(listing.url)
        if len(listings) >= MAX_ITEMS_PER_SCAN:
            break
    return listings


def web_discovery(session: requests.Session) -> list[h.Listing]:
    results: list[h.Listing] = []
    seen_urls: set[str] = set()
    for query in SALE_DISCOVERY_QUERIES:
        url = f"https://www.bing.com/search?format=rss&count=30&q={quote_plus(query)}"
        response = h.request(session, url)
        if response is None:
            continue
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            continue
        for item in root.findall(".//item"):
            title = h.clean_text(item.findtext("title") or "")
            link = h.clean_text(item.findtext("link") or "")
            desc = h.clean_text(item.findtext("description") or "")
            combined = h.clean_text(f"{title} {desc}")
            norm = h.normalize(combined)
            if not link or link in seen_urls or not is_house_sale(norm):
                continue
            host = urlparse(link).netloc.lower().removeprefix("www.")
            if host in {"bing.com", "microsoft.com"}:
                continue
            price_match = h.PRICE_RE.search(combined)
            area_match = h.AREA_RE.search(combined)
            rooms_match = h.ROOMS_RE.search(combined)
            location, postcode = h.extract_location(combined)
            results.append(h.Listing(
                source=f"Web/{host}",
                title=title[:240],
                url=link,
                text=combined[:5000],
                location=location,
                postcode=postcode,
                price_eur=h.parse_number(price_match.group(1)) if price_match else None,
                area_m2=h.parse_number(area_match.group(1)) if area_match else None,
                rooms=h.parse_number(rooms_match.group(1)) if rooms_match else None,
            ))
            seen_urls.add(link)
        time.sleep(0.35)
    return results


def determine_distance(db: sqlite3.Connection, session: requests.Session, listing: h.Listing) -> float | None:
    if listing.distance_km is not None:
        return listing.distance_km
    queries: list[str] = []
    if listing.postcode and listing.location:
        queries.append(f"{listing.postcode} {listing.location}")
    if listing.postcode:
        queries.append(listing.postcode)
    if listing.location:
        queries.append(listing.location)
    for query in queries:
        coords = h.geocode(db, session, query)
        if coords:
            return round(h.haversine_km(HOME_LAT, HOME_LON, coords[0], coords[1]), 1)
    norm = h.normalize(f"{listing.title} {listing.location}")
    for place, coords in h.FALLBACK_COORDS.items():
        if h.normalize(place) in norm:
            return round(h.haversine_km(HOME_LAT, HOME_LON, coords[0], coords[1]), 1)
    # Accept Minden itself only when it is in the title/location, not merely in a generic
    # Kreis/portal description, which avoids false positives from farther towns.
    if re.search(r"(?<!\w)minden(?!\w)", norm):
        return 0.0
    return None


def fingerprint(listing: h.Listing) -> str:
    raw = f"sale|{listing.source}|{listing.url}".encode("utf-8", "ignore")
    return hashlib.sha256(raw).hexdigest()


def cross_key(listing: h.Listing) -> str:
    price = int(round(listing.price_eur or 0))
    area = int(round(listing.area_m2 or 0))
    rooms = int(round((listing.rooms or 0) * 2))
    location = listing.postcode or h.normalize(listing.location)[:30]
    if not any((price, area, rooms)):
        return ""
    raw = f"sale|{location}|{price}|{area}|{rooms}".encode("utf-8", "ignore")
    return hashlib.sha256(raw).hexdigest()


def seen_reason(db: sqlite3.Connection, listing: h.Listing) -> str:
    now = datetime.now(timezone.utc).isoformat()
    fp = fingerprint(listing)
    ck = cross_key(listing)
    row = db.execute("SELECT 1 FROM seen_sale_listings WHERE fingerprint = ?", (fp,)).fetchone()
    if row:
        db.execute("UPDATE seen_sale_listings SET last_seen = ? WHERE fingerprint = ?", (now, fp))
        db.commit()
        return "same-url"
    if ck:
        duplicate = db.execute("SELECT 1 FROM seen_sale_listings WHERE cross_key = ? LIMIT 1", (ck,)).fetchone()
        if duplicate:
            db.execute(
                "INSERT OR IGNORE INTO seen_sale_listings(fingerprint,cross_key,source,title,url,first_seen,last_seen) VALUES (?,?,?,?,?,?,?)",
                (fp, ck, listing.source, listing.title, listing.url, now, now),
            )
            db.commit()
            return "cross-portal"
    return "new"


def record_seen(db: sqlite3.Connection, listing: h.Listing) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT OR REPLACE INTO seen_sale_listings(fingerprint,cross_key,source,title,url,first_seen,last_seen) VALUES (?,?,?,?,?,?,?)",
        (fingerprint(listing), cross_key(listing), listing.source, listing.title, listing.url, now, now),
    )
    db.commit()


def ukrainian_summary(listing: h.Listing) -> str:
    bits: list[str] = []
    if listing.area_m2:
        bits.append(f"площа близько {listing.area_m2:g} м²")
    if listing.rooms:
        bits.append(f"{listing.rooms:g} кімн.")
    found_features: list[str] = []
    norm = h.normalize(listing.text)
    for german, ukrainian in FEATURES.items():
        if h.normalize(german) in norm and ukrainian not in found_features:
            found_features.append(ukrainian)
    core = "Будинок продається"
    if bits:
        core += ", " + ", ".join(bits)
    core += "."
    if found_features:
        core += " З оголошення: " + ", ".join(found_features[:5]) + "."
    if listing.distance_km is not None:
        core += f" Приблизно {listing.distance_km:g} км від центру Minden."
    return core


def send_telegram(session: requests.Session, listing: h.Listing) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("Telegram token/chat id missing; notification skipped")
        return False
    location = listing.location or (f"PLZ {listing.postcode}" if listing.postcode else "локація в оголошенні")
    price = h.format_eur(listing.price_eur)
    details = []
    if listing.area_m2:
        details.append(f"{listing.area_m2:g} м²")
    if listing.rooms:
        details.append(f"{listing.rooms:g} кімн.")
    details_text = " · ".join(details) if details else "параметри див. в оголошенні"
    distance = f" · ~{listing.distance_km:g} км від Minden" if listing.distance_km is not None else ""
    text = (
        "🏡 НОВИЙ БУДИНОК НА ПРОДАЖ\n"
        f"📍 {location}{distance}\n"
        f"💶 {price} (ціна продажу; комісію перевірити в оголошенні)\n"
        f"📐 {details_text}\n\n"
        f"🇺🇦 {ukrainian_summary(listing)}\n\n"
        f"🌐 {listing.source}\n"
        f"🔗 {listing.url}"
    )
    try:
        response = session.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text[:4090], "disable_web_page_preview": "false"},
            timeout=HTTP_TIMEOUT,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        log(f"Telegram send failed: {exc}")
        return False


def scan_once() -> tuple[int, int, int]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    db = db_connect()
    found: list[h.Listing] = []
    for source, url in SALE_SOURCES:
        response = h.request(session, url)
        if response is None:
            continue
        items = parse_sale_page(source, response.url, response.text)
        log(f"{source}: parsed {len(items)} candidate sale listings")
        found.extend(items)
        time.sleep(0.5)
    try:
        discovery = web_discovery(session)
        log(f"sale web discovery: parsed {len(discovery)} candidate listings")
        found.extend(discovery)
    except Exception as exc:
        log(f"sale web discovery failed safely: {exc}")

    unique: dict[str, h.Listing] = {}
    for item in found:
        unique.setdefault(item.url, item)

    accepted = 0
    notified = 0
    for listing in list(unique.values())[:MAX_ITEMS_PER_SCAN]:
        distance = determine_distance(db, session, listing)
        if distance is None:
            log(f"skip unknown distance: {listing.source} | {listing.title[:80]}")
            continue
        listing.distance_km = distance
        if distance > SALE_RADIUS_KM + 0.15:
            continue
        accepted += 1
        reason = seen_reason(db, listing)
        if reason != "new":
            continue
        if notified >= MAX_NOTIFICATIONS_PER_SCAN:
            log("sale notification cap reached; remaining new items will retry next scan")
            continue
        if send_telegram(session, listing):
            record_seen(db, listing)
            notified += 1
            log(f"sale notified: {listing.source} | {listing.title[:100]}")
        else:
            log(f"Telegram send failed; sale listing left unseen for retry: {listing.url}")
    db.close()
    return len(unique), accepted, notified


def main() -> int:
    log(f"Minden house-sale radar starting: city={HOME_CITY}, radius={SALE_RADIUS_KM:g} km, interval={SCAN_INTERVAL_SECONDS}s")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID are required")
        return 2
    run_once = os.getenv("RUN_ONCE", "").lower() in {"1", "true", "yes"}
    while True:
        try:
            scanned, accepted, notified = scan_once()
            log(f"sale scan complete: unique={scanned}, within_radius={accepted}, notified={notified}")
        except Exception as exc:
            log(f"sale scan failed safely: {type(exc).__name__}: {exc}")
        if run_once:
            return 0
        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
