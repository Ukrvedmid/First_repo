from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HOME_CITY = os.getenv("RADAR_HOME_CITY", "Minden").strip() or "Minden"
HOME_LAT = float(os.getenv("RADAR_HOME_LAT", "52.2895"))
HOME_LON = float(os.getenv("RADAR_HOME_LON", "8.9146"))
RADIUS_KM = float(os.getenv("RADAR_RADIUS_KM", "15"))
SCAN_INTERVAL_SECONDS = max(900, int(os.getenv("HOUSING_SCAN_INTERVAL_SECONDS", "1800")))
DB_PATH = os.getenv("HOUSING_DB_PATH", "/data/housing.db")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
HTTP_TIMEOUT = max(8, int(os.getenv("HOUSING_HTTP_TIMEOUT_SECONDS", "20")))
MAX_ITEMS_PER_SCAN = max(5, int(os.getenv("HOUSING_MAX_ITEMS_PER_SCAN", "80")))
MAX_NOTIFICATIONS_PER_SCAN = max(1, int(os.getenv("HOUSING_MAX_NOTIFICATIONS_PER_SCAN", "12")))
USER_AGENT = os.getenv(
    "HOUSING_USER_AGENT",
    "MindenRadar/1.0 (+personal rental monitor; contact via Telegram bot owner)",
)

HOUSE_TERMS = (
    "einfamilienhaus", "doppelhaushälfte", "doppelhaushaelfte", "doppelhaus",
    "reihenhaus", "reihenmittelhaus", "reiheneckhaus", "bungalow", "stadthaus",
    "landhaus", "bauernhaus", "wohnhaus", "haus zur miete", "haus mieten",
    "haushälfte", "haushaelfte", "miethaus",
)
REJECT_TERMS = (
    "mietgesuch", "gesucht", "wir suchen", "suche ein haus", "suche haus",
    "haus gesucht", "wohnung gesucht", "gesuche", "zum kauf", "zu verkaufen",
    "verkauf", "kaufpreis", "kaufen", "mietkauf", "ferienhaus", "ferienwohnung",
)
FEATURES = {
    "garten": "сад",
    "garage": "гараж",
    "stellplatz": "паркомісце",
    "einbauküche": "вбудована кухня",
    "einbaukueche": "вбудована кухня",
    "keller": "підвал",
    "terrasse": "тераса",
    "balkon": "балкон",
    "haustiere": "дозволені тварини",
    "wärmepumpe": "тепловий насос",
    "waermepumpe": "тепловий насос",
}

# Major public portals plus a general web-discovery feed for smaller/local sites.
# The crawler never attempts to bypass logins, CAPTCHAs, robots restrictions or anti-bot blocks.
SOURCES = (
    ("Kleinanzeigen", "https://www.kleinanzeigen.de/s-haus-mieten/minden/sortierung:entfernung/haus/k0c205l1760r15"),
    ("ImmoScout24", "https://www.immobilienscout24.de/Suche/de/nordrhein-westfalen/minden-luebbecke-kreis/minden/haus-mieten"),
    ("ImmoScout24-Kreis", "https://www.immobilienscout24.de/Suche/de/nordrhein-westfalen/minden-luebbecke-kreis/haus-mieten"),
    ("Immowelt", "https://www.immowelt.de/suche/mieten/haus/nordrhein-westfalen/minden-32423/ad08de2409"),
    ("Immowelt-Kreis", "https://www.immowelt.de/suche/mieten/haus/nordrhein-westfalen/minden-lubbecke-05770/ad06de104"),
    ("Immonet", "https://www.immonet.de/suchen/miete/haus/nordrhein-westfalen/minden-32423/ad08de2409"),
    ("Meinestadt", "https://www.meinestadt.de/minden-westfalen/immobilien/miethaus"),
    ("Ohne-Makler", "https://www.ohne-makler.net/immobilien/haus-mieten/nordrhein-westfalen/minden/"),
    ("Ohne-Makler-Kreis", "https://www.ohne-makler.net/immobilien/haus-mieten/nordrhein-westfalen/kreis-minden-luebbecke/"),
)

# Approximate municipality centres used only as a no-network fallback when a listing exposes a city
# but not coordinates. Exact addresses/postcodes are geocoded and cached when possible.
FALLBACK_COORDS = {
    "minden": (52.2895, 8.9146),
    "porta westfalica": (52.2296, 8.9168),
    "bad oeynhausen": (52.2065, 8.8037),
    "petershagen": (52.3752, 8.9650),
    "hille": (52.3330, 8.7500),
    "bueckeburg": (52.2606, 9.0494),
    "bückeburg": (52.2606, 9.0494),
    "rinteln": (52.1860, 9.0792),
}

POSTCODE_RE = re.compile(r"\b(3\d{4})\b")
PRICE_RE = re.compile(r"(?<!\d)((?:\d{1,3}(?:[. ]\d{3})+|\d{2,5})(?:,\d{1,2})?)\s*€")
AREA_RE = re.compile(r"(\d{2,3}(?:[.,]\d+)?)\s*m(?:²|2)\b", re.I)
ROOMS_RE = re.compile(r"(\d{1,2}(?:[.,]\d)?)\s*(?:zimmer|zi\.)", re.I)
DISTANCE_RE = re.compile(r"\((\d{1,2}(?:[.,]\d+)?)\s*km\)", re.I)


@dataclass
class Listing:
    source: str
    title: str
    url: str
    text: str
    location: str = ""
    postcode: str = ""
    price_eur: float | None = None
    area_m2: float | None = None
    rooms: float | None = None
    distance_km: float | None = None


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {message}", flush=True)


def db_connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        """CREATE TABLE IF NOT EXISTS seen_listings (
               fingerprint TEXT PRIMARY KEY,
               cross_key TEXT,
               source TEXT NOT NULL,
               title TEXT NOT NULL,
               url TEXT NOT NULL,
               first_seen TEXT NOT NULL,
               last_seen TEXT NOT NULL
           )"""
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_seen_cross_key ON seen_listings(cross_key)")
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


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def normalize(value: str) -> str:
    value = clean_text(value).lower()
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def parse_number(raw: str | None) -> float | None:
    if not raw:
        return None
    raw = raw.strip().replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") == 1 and len(raw.split(".")[-1]) == 3:
        raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def request(session: requests.Session, url: str) -> requests.Response | None:
    try:
        response = session.get(url, timeout=HTTP_TIMEOUT, allow_redirects=True)
        if response.status_code in (401, 403, 429):
            log(f"{urlparse(url).netloc}: access limited ({response.status_code}); skipping without bypass")
            return None
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        log(f"fetch failed {url}: {exc}")
        return None


def closest_card_text(anchor) -> str:
    node = getattr(anchor, "parent", None) or anchor
    best = clean_text(anchor.get_text(" ", strip=True))
    for _ in range(6):
        if node is None:
            break
        text = clean_text(node.get_text(" ", strip=True)) if hasattr(node, "get_text") else ""
        if len(text) > len(best) and len(text) <= 3000:
            best = text
        if len(text) >= 90:
            return text
        node = getattr(node, "parent", None)
    return best


def looks_like_listing_url(source: str, href: str) -> bool:
    if not href or href.startswith(("#", "javascript:", "mailto:")):
        return False
    path = urlparse(href).path.lower()
    rules = {
        "kleinanzeigen": ("/s-anzeige/",),
        "immoscout24": ("/expose/",),
        "immowelt": ("/expose/",),
        "immonet": ("/expose/", "/angebot/", "/immobilie/"),
        "meinestadt": ("/expose/",),
        "ohne-makler": ("/immobilie/", "/property/"),
    }
    lowered = source.lower()
    key = next((candidate for candidate in rules if lowered.startswith(candidate)), lowered)
    patterns = rules.get(key, ())
    if patterns and any(pattern in path for pattern in patterns):
        return True
    # Generic fallback: only anchors whose surrounding card clearly looks like a rental house are kept later.
    return False


def extract_location(text: str) -> tuple[str, str]:
    postcode_match = POSTCODE_RE.search(text)
    postcode = postcode_match.group(1) if postcode_match else ""
    lowered = normalize(text)
    for place in sorted(FALLBACK_COORDS, key=len, reverse=True):
        if normalize(place) in lowered:
            return place.title(), postcode
    # Typical German card sequence: "Ort ... 32423". Keep a compact context around the postcode.
    if postcode_match:
        start = max(0, postcode_match.start() - 55)
        end = min(len(text), postcode_match.end() + 35)
        return clean_text(text[start:end]), postcode
    return "", postcode


def is_house_offer(normalized_text: str) -> bool:
    if any(normalize(term) in normalized_text for term in HOUSE_TERMS):
        return True
    tokens = set(normalized_text.split())
    return (
        "haus" in tokens
        and (
            "miete" in tokens
            or "mieten" in tokens
            or "vermieten" in tokens
            or "vermietung" in tokens
            or "vermietet" in tokens
        )
    )


def extract_listing(source: str, base_url: str, anchor) -> Listing | None:
    href = clean_text(anchor.get("href", ""))
    if not href:
        return None
    url = urljoin(base_url, href)
    title = clean_text(anchor.get("title", "") or anchor.get_text(" ", strip=True))
    card = closest_card_text(anchor)
    if len(title) < 5:
        # Prefer the first prominent heading inside the card.
        parent = anchor.parent
        heading = parent.find(["h2", "h3", "h4"]) if parent else None
        if heading:
            title = clean_text(heading.get_text(" ", strip=True))
    if len(title) < 5:
        title = card[:180]

    combined = clean_text(f"{title} {card}")
    normalized = normalize(combined)
    if any(normalize(term) in normalized for term in REJECT_TERMS):
        return None
    if not is_house_offer(normalized):
        return None

    price_match = PRICE_RE.search(combined)
    area_match = AREA_RE.search(combined)
    rooms_match = ROOMS_RE.search(combined)
    distance_match = DISTANCE_RE.search(combined)
    location, postcode = extract_location(combined)
    return Listing(
        source=source,
        title=title[:240],
        url=url,
        text=combined[:5000],
        location=location,
        postcode=postcode,
        price_eur=parse_number(price_match.group(1)) if price_match else None,
        area_m2=parse_number(area_match.group(1)) if area_match else None,
        rooms=parse_number(rooms_match.group(1)) if rooms_match else None,
        distance_km=parse_number(distance_match.group(1)) if distance_match else None,
    )


def parse_portal_page(source: str, url: str, html_text: str) -> list[Listing]:
    soup = BeautifulSoup(html_text, "html.parser")
    listings: list[Listing] = []
    seen_urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        if not looks_like_listing_url(source, href):
            continue
        listing = extract_listing(source, url, anchor)
        if listing and listing.url not in seen_urls:
            listings.append(listing)
            seen_urls.add(listing.url)
        if len(listings) >= MAX_ITEMS_PER_SCAN:
            break
    return listings


def bing_discovery(session: requests.Session) -> list[Listing]:
    queries = (
        '"Haus" "Miete" Minden 32423',
        '"Einfamilienhaus" mieten Minden',
        '"Doppelhaushälfte" mieten Minden',
        '"Reihenhaus" mieten Minden',
        'Haus mieten "Porta Westfalica"',
        'Haus mieten "Bad Oeynhausen"',
        'Haus mieten Bückeburg',
        'Haus mieten Petershagen Hille Minden',
        'site:immobilien.sparkasse.de/expose Haus mieten Minden Porta Westfalica',
    )
    results: list[Listing] = []
    for query in queries:
        url = f"https://www.bing.com/search?format=rss&count=25&q={quote_plus(query)}"
        response = request(session, url)
        if response is None:
            continue
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            continue
        for item in root.findall(".//item"):
            title = clean_text(item.findtext("title") or "")
            link = clean_text(item.findtext("link") or "")
            desc = clean_text(item.findtext("description") or "")
            combined = clean_text(f"{title} {desc}")
            norm = normalize(combined)
            if not link or any(normalize(term) in norm for term in REJECT_TERMS):
                continue
            if not is_house_offer(norm):
                continue
            host = urlparse(link).netloc.lower().removeprefix("www.")
            if host in {"bing.com", "microsoft.com"}:
                continue
            price_match = PRICE_RE.search(combined)
            area_match = AREA_RE.search(combined)
            rooms_match = ROOMS_RE.search(combined)
            location, postcode = extract_location(combined)
            results.append(Listing(
                source=f"Web/{host}", title=title[:240], url=link, text=combined[:5000],
                location=location, postcode=postcode,
                price_eur=parse_number(price_match.group(1)) if price_match else None,
                area_m2=parse_number(area_match.group(1)) if area_match else None,
                rooms=parse_number(rooms_match.group(1)) if rooms_match else None,
            ))
        time.sleep(0.4)
    return results


def geocode(db: sqlite3.Connection, session: requests.Session, query: str) -> tuple[float, float] | None:
    query = clean_text(query)
    if not query:
        return None
    key = normalize(query)
    if key in FALLBACK_COORDS:
        return FALLBACK_COORDS[key]
    row = db.execute("SELECT lat, lon FROM geocode_cache WHERE query = ?", (key,)).fetchone()
    if row:
        if row[0] is None or row[1] is None:
            return None
        return float(row[0]), float(row[1])

    params = {"q": f"{query}, Germany", "format": "jsonv2", "limit": 1, "countrycodes": "de"}
    try:
        response = session.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code in (403, 429):
            return None
        response.raise_for_status()
        data = response.json()
        coords = (float(data[0]["lat"]), float(data[0]["lon"])) if data else None
    except (requests.RequestException, ValueError, KeyError, IndexError, json.JSONDecodeError):
        coords = None

    db.execute(
        "INSERT OR REPLACE INTO geocode_cache(query, lat, lon, updated_at) VALUES (?, ?, ?, ?)",
        (key, coords[0] if coords else None, coords[1] if coords else None, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    time.sleep(1.05)  # Nominatim public-service courtesy limit; queries are cached.
    return coords


def determine_distance(db: sqlite3.Connection, session: requests.Session, listing: Listing) -> float | None:
    if listing.distance_km is not None:
        return listing.distance_km
    queries: list[str] = []
    if listing.postcode and listing.location:
        queries.append(f"{listing.postcode} {listing.location}")
    if listing.postcode:
        queries.append(listing.postcode)
    if listing.location:
        queries.append(listing.location)
    norm_text = normalize(listing.text)
    for query in queries:
        coords = geocode(db, session, query)
        if coords:
            return round(haversine_km(HOME_LAT, HOME_LON, coords[0], coords[1]), 1)
    # Direct named-municipality fallback from the card text if geocoding is unavailable.
    for place, coords in FALLBACK_COORDS.items():
        if normalize(place) in norm_text:
            return round(haversine_km(HOME_LAT, HOME_LON, coords[0], coords[1]), 1)
    # Minden-only pages are safe if the card itself explicitly mentions Minden.
    if "minden" in norm_text:
        return 0.0
    return None


def fingerprint(listing: Listing) -> str:
    raw = f"{listing.source}|{listing.url}".encode("utf-8", "ignore")
    return hashlib.sha256(raw).hexdigest()


def cross_key(listing: Listing) -> str:
    # Cross-portal dedupe without relying on exact titles.
    price = int(round(listing.price_eur or 0))
    area = int(round(listing.area_m2 or 0))
    rooms = int(round((listing.rooms or 0) * 2))
    location = listing.postcode or normalize(listing.location)[:30]
    if not any((price, area, rooms)):
        return ""
    raw = f"{location}|{price}|{area}|{rooms}".encode("utf-8", "ignore")
    return hashlib.sha256(raw).hexdigest()


def seen_reason(db: sqlite3.Connection, listing: Listing) -> str:
    now = datetime.now(timezone.utc).isoformat()
    fp = fingerprint(listing)
    ck = cross_key(listing)
    row = db.execute("SELECT 1 FROM seen_listings WHERE fingerprint = ?", (fp,)).fetchone()
    if row:
        db.execute("UPDATE seen_listings SET last_seen = ? WHERE fingerprint = ?", (now, fp))
        db.commit()
        return "same-url"
    if ck:
        duplicate = db.execute("SELECT 1 FROM seen_listings WHERE cross_key = ? LIMIT 1", (ck,)).fetchone()
        if duplicate:
            # Store the alternate portal URL so the same property is not reconsidered every scan.
            db.execute(
                "INSERT OR IGNORE INTO seen_listings(fingerprint,cross_key,source,title,url,first_seen,last_seen) VALUES (?,?,?,?,?,?,?)",
                (fp, ck, listing.source, listing.title, listing.url, now, now),
            )
            db.commit()
            return "cross-portal"
    return "new"


def record_seen(db: sqlite3.Connection, listing: Listing) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT OR REPLACE INTO seen_listings(fingerprint,cross_key,source,title,url,first_seen,last_seen) VALUES (?,?,?,?,?,?,?)",
        (fingerprint(listing), cross_key(listing), listing.source, listing.title, listing.url, now, now),
    )
    db.commit()


def format_eur(value: float | None) -> str:
    if value is None:
        return "не вказано"
    if abs(value - round(value)) < 0.01:
        return f"{int(round(value)):,}".replace(",", ".") + " €"
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def ukrainian_summary(listing: Listing) -> str:
    bits: list[str] = []
    if listing.area_m2:
        bits.append(f"площа близько {listing.area_m2:g} м²")
    if listing.rooms:
        bits.append(f"{listing.rooms:g} кімн.")
    found_features = []
    norm = normalize(listing.text)
    for german, ukrainian in FEATURES.items():
        if normalize(german) in norm and ukrainian not in found_features:
            found_features.append(ukrainian)
    core = "Будинок здається в оренду"
    if bits:
        core += ", " + ", ".join(bits)
    core += "."
    if found_features:
        core += " З оголошення: " + ", ".join(found_features[:4]) + "."
    if listing.distance_km is not None:
        core += f" Приблизно {listing.distance_km:g} км від центру Minden."
    return core


def send_telegram(session: requests.Session, listing: Listing) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("Telegram token/chat id missing; notification skipped")
        return False
    location = listing.location or (f"PLZ {listing.postcode}" if listing.postcode else "локація в оголошенні")
    price = format_eur(listing.price_eur)
    details = []
    if listing.area_m2:
        details.append(f"{listing.area_m2:g} м²")
    if listing.rooms:
        details.append(f"{listing.rooms:g} кімн.")
    details_text = " · ".join(details) if details else "параметри див. в оголошенні"
    distance = f" · ~{listing.distance_km:g} км від Minden" if listing.distance_km is not None else ""
    text = (
        "🏠 НОВИЙ БУДИНОК В ОРЕНДУ\n"
        f"📍 {location}{distance}\n"
        f"💶 {price} (перевірити Kalt/Warmmiete в оголошенні)\n"
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
    found: list[Listing] = []
    for source, url in SOURCES:
        response = request(session, url)
        if response is None:
            continue
        items = parse_portal_page(source, response.url, response.text)
        log(f"{source}: parsed {len(items)} candidate house-rental listings")
        found.extend(items)
        time.sleep(0.5)
    try:
        discovery = bing_discovery(session)
        log(f"web discovery: parsed {len(discovery)} candidate listings")
        found.extend(discovery)
    except Exception as exc:  # discovery is supplementary; never take down the radar
        log(f"web discovery failed: {exc}")

    # URL dedupe before geocoding.
    unique: dict[str, Listing] = {}
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
        if distance > RADIUS_KM + 0.15:
            continue
        accepted += 1
        reason = seen_reason(db, listing)
        if reason != "new":
            continue
        if notified >= MAX_NOTIFICATIONS_PER_SCAN:
            log("notification cap reached; remaining new items will be retried on the next scan")
            continue
        if send_telegram(session, listing):
            record_seen(db, listing)
            notified += 1
            log(f"notified: {listing.source} | {listing.title[:100]}")
        else:
            log(f"Telegram send failed; listing left unseen for retry: {listing.url}")
    db.close()
    return len(unique), accepted, notified


def main() -> int:
    log(f"Minden housing radar starting: city={HOME_CITY}, radius={RADIUS_KM:g} km, interval={SCAN_INTERVAL_SECONDS}s")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID are required")
        return 2
    run_once = os.getenv("RUN_ONCE", "").lower() in {"1", "true", "yes"}
    while True:
        try:
            scanned, accepted, notified = scan_once()
            log(f"scan complete: unique={scanned}, within_radius={accepted}, notified={notified}")
        except Exception as exc:
            log(f"scan failed safely: {type(exc).__name__}: {exc}")
        if run_once:
            return 0
        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
