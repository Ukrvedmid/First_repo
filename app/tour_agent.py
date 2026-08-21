from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

DEPARTURE_START = date.fromisoformat(os.getenv("TOUR_DEPARTURE_START", "2026-08-24"))
DEPARTURE_END = date.fromisoformat(os.getenv("TOUR_DEPARTURE_END", "2026-08-31"))
RETURN_BY = date.fromisoformat(os.getenv("TOUR_RETURN_BY", "2026-09-02"))
SCAN_INTERVAL_SECONDS = max(900, int(os.getenv("TOUR_SCAN_INTERVAL_SECONDS", "1800")))
DB_PATH = os.getenv("TOUR_DB_PATH", "/data/tour-deals.db")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
HTTP_TIMEOUT = max(8, int(os.getenv("TOUR_HTTP_TIMEOUT_SECONDS", "20")))
MAX_ITEMS_PER_SCAN = max(20, int(os.getenv("TOUR_MAX_ITEMS_PER_SCAN", "180")))
MAX_NOTIFICATIONS_PER_SCAN = max(1, int(os.getenv("TOUR_MAX_NOTIFICATIONS_PER_SCAN", "15")))
USER_AGENT = os.getenv("TOUR_USER_AGENT", "MindenRadar/1.0 (+personal package-tour monitor)")

# Direct public pages. Many tour sites render search results dynamically, so the
# broad web-discovery layer below is equally important and is not limited to this list.
SOURCES = (
    ("CHECK24 Reisen", "https://urlaub.check24.de/"),
    ("HolidayCheck Deals", "https://www.holidaycheck.de/deals?travelMonth=8"),
    ("weg.de Sommerferien", "https://www.weg.de/urlaub/sommerferien"),
    ("TUI Pauschalreisen", "https://www.tui.com/pauschalreisen/"),
    ("DERTOUR Pauschalreisen", "https://www.dertour.de/pauschalreisen"),
    ("Schauinsland Reisen", "https://www.schauinsland-reisen.de/"),
    ("alltours", "https://www.alltours.de/pauschalreisen"),
    ("ltur", "https://www.ltur.com/de/pauschalreisen"),
    ("Ab in den Urlaub", "https://www.ab-in-den-urlaub.de/pauschalreisen"),
    ("Urlaubsguru", "https://www.urlaubsguru.de/pauschalreisen/"),
    ("Urlaubspiraten", "https://www.urlaubspiraten.de/urlaub/pauschalreisen"),
    ("Sonnenklar.TV", "https://www.sonnenklar.tv/pauschalreisen.html"),
)

AIRPORT_TERMS = (
    "Hannover", "Düsseldorf", "Duesseldorf", "Köln/Bonn", "Koeln/Bonn", "Paderborn",
    "Dortmund", "Münster", "Muenster", "Bremen", "Hamburg", "Berlin", "Frankfurt",
    "Leipzig", "Nürnberg", "Nuernberg", "Stuttgart", "München", "Muenchen", "Karlsruhe",
    "Baden-Baden", "Memmingen", "Weeze", "Saarbrücken", "Saarbruecken", "Dresden",
    "Erfurt", "Friedrichshafen", "Deutschland - alle Flughäfen", "Alle Abflughäfen",
)

SEA_TERMS = (
    "strand", "strandurlaub", "meer", "beach", "küste", "kueste", "riviera", "insel",
    "mittelmeer", "adria", "adriatik", "ägäis", "aegeis", "atlantik", "kanaren",
    "mallorca", "menorca", "ibiza", "kreta", "rhodos", "kos", "korfu", "zakynthos",
    "chalkidiki", "thessaloniki", "zypern", "paphos", "larnaca", "antaly", "side",
    "alanya", "belek", "kemer", "bodrum", "marmaris", "hurghada", "safaga", "marsa alam",
    "sharm el sheikh", "kroatien", "istrien", "kvarner", "porec", "poreč", "pula", "rabac",
    "umag", "rovinj", "zadar", "split", "dubrovnik", "malta", "sardinien", "sizilien",
    "kalabrien", "apulien", "algarve", "costa del sol", "costa blanca", "teneriffa",
    "gran canaria", "fuerteventura", "lanzarote", "la palma", "madeira", "portugal",
)

PACKAGE_TERMS = (
    "pauschalreise", "pauschal", "flug", "hinflug", "rückflug", "rueckflug", "transfer",
    "all inclusive", "all-inclusive", "halbpension", "vollpension", "hotel", "veranstalter",
)

REJECT_TERMS = (
    "nur hotel", "eigene anreise", "ferienwohnung", "ferienhaus ohne flug", "städtereise",
    "staedtereise", "kreuzfahrt", "mietwagenreise", "camping", "hostel",
)

MONTHS = {
    "jan": 1, "januar": 1, "feb": 2, "februar": 2, "mär": 3, "maer": 3, "märz": 3,
    "apr": 4, "april": 4, "mai": 5, "jun": 6, "juni": 6, "jul": 7, "juli": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "okt": 10, "oktober": 10,
    "nov": 11, "november": 11, "dez": 12, "dezember": 12,
}

NUMERIC_RANGE_RE = re.compile(
    r"\b(\d{1,2})[.](\d{1,2})(?:[.]?(\d{2,4}))?\s*[-–—]\s*(\d{1,2})[.](\d{1,2})(?:[.]?(\d{2,4}))?"
)
TEXT_RANGE_RE = re.compile(
    r"\b(\d{1,2})[.]\s*([A-Za-zÄÖÜäöü]{3,10})[.]?\s*[-–—]\s*(\d{1,2})[.]\s*([A-Za-zÄÖÜäöü]{3,10})[.]?(?:\s*(20\d{2}))?",
    re.I,
)
PRICE_AB_RE = re.compile(r"\bab\s*([\d. ]{2,10}(?:,\d{1,2})?)\s*€", re.I)
PRICE_RE = re.compile(r"(?<!\d)([\d. ]{2,10}(?:,\d{1,2})?)\s*€")
PERSON_RE = re.compile(r"\b(\d+)\s*(?:personen|p\b|erwachsene)", re.I)
NIGHTS_RE = re.compile(r"\b(\d{1,2})\s*(?:nächte|naechte|nächten|naechten)\b", re.I)
DAYS_RE = re.compile(r"\b(\d{1,2})\s*(?:tage|tag)\b", re.I)
PERCENT_RE = re.compile(r"\b(\d{2,3})\s*%")


@dataclass
class TourDeal:
    source: str
    title: str
    url: str
    text: str
    departure: date
    return_date: date
    airport: str = ""
    price_eur: float | None = None
    persons: int | None = None
    nights: int | None = None
    board: str = ""
    destination: str = ""


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {message}", flush=True)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def norm(value: str) -> str:
    value = clean_text(value).casefold()
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return value


def parse_number(raw: str | None) -> float | None:
    if not raw:
        return None
    raw = raw.replace(" ", "").strip()
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") >= 1:
        raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _year(value: str | None, default: int = 2026) -> int:
    if not value:
        return default
    year = int(value)
    return 2000 + year if year < 100 else year


def parse_date_range(text: str) -> tuple[date, date] | None:
    match = NUMERIC_RANGE_RE.search(text)
    if match:
        d1, m1, y1, d2, m2, y2 = match.groups()
        try:
            return date(_year(y1), int(m1), int(d1)), date(_year(y2), int(m2), int(d2))
        except ValueError:
            pass

    match = TEXT_RANGE_RE.search(text)
    if match:
        d1, mon1, d2, mon2, year = match.groups()
        key1 = norm(mon1).rstrip(".")
        key2 = norm(mon2).rstrip(".")
        m1 = next((month for name, month in MONTHS.items() if key1.startswith(norm(name))), None)
        m2 = next((month for name, month in MONTHS.items() if key2.startswith(norm(name))), None)
        if m1 and m2:
            try:
                return date(_year(year), m1, int(d1)), date(_year(year), m2, int(d2))
            except ValueError:
                pass
    return None


def in_window(start: date, end: date) -> bool:
    return DEPARTURE_START <= start <= DEPARTURE_END and start < end <= RETURN_BY


def is_sea_package(text: str) -> bool:
    lowered = norm(text)
    if any(norm(term) in lowered for term in REJECT_TERMS):
        return False
    return any(norm(term) in lowered for term in SEA_TERMS) and any(norm(term) in lowered for term in PACKAGE_TERMS)


def extract_airport(text: str) -> str:
    lowered = norm(text)
    for term in AIRPORT_TERMS:
        if norm(term) in lowered:
            return term
    match = re.search(r"\bab\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß/-]{2,25}(?:\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß/-]{2,25})?)", text)
    return clean_text(match.group(1)) if match else ""


def extract_board(text: str) -> str:
    lowered = norm(text)
    for raw, label in (
        ("ultra all inclusive", "Ultra All Inclusive"),
        ("all inclusive", "All Inclusive"),
        ("all-inclusive", "All Inclusive"),
        ("vollpension", "Vollpension"),
        ("halbpension", "Halbpension"),
        ("frühstück", "Frühstück"),
        ("fruehstueck", "Frühstück"),
    ):
        if norm(raw) in lowered:
            return label
    return ""


def extract_price(text: str) -> float | None:
    match = PRICE_AB_RE.search(text)
    if match:
        return parse_number(match.group(1))
    values = [parse_number(match.group(1)) for match in PRICE_RE.finditer(text)]
    values = [value for value in values if value is not None and 150 <= value <= 50000]
    return min(values) if values else None


def extract_destination(title: str, text: str) -> str:
    combined = f"{title} {text}"
    lowered = norm(combined)
    for term in SEA_TERMS:
        if norm(term) in lowered and len(term) >= 4 and term not in {"strand", "strandurlaub", "meer", "beach", "küste", "kueste", "insel", "mittelmeer", "atlantik"}:
            return term.title()
    return ""


def closest_card_text(anchor) -> str:
    node = getattr(anchor, "parent", None) or anchor
    best = clean_text(anchor.get_text(" ", strip=True))
    for _ in range(6):
        if node is None:
            break
        text = clean_text(node.get_text(" ", strip=True)) if hasattr(node, "get_text") else ""
        if len(best) < len(text) <= 3500:
            best = text
        if len(text) >= 100 and parse_date_range(text):
            return text
        node = getattr(node, "parent", None)
    return best


def build_deal(source: str, url: str, title: str, text: str) -> TourDeal | None:
    combined = clean_text(f"{title} {text}")
    dates = parse_date_range(combined)
    if not dates or not in_window(*dates) or not is_sea_package(combined):
        return None
    person_match = PERSON_RE.search(combined)
    nights_match = NIGHTS_RE.search(combined)
    if not nights_match:
        days_match = DAYS_RE.search(combined)
        nights = max(1, int(days_match.group(1)) - 1) if days_match else (dates[1] - dates[0]).days
    else:
        nights = int(nights_match.group(1))
    return TourDeal(
        source=source,
        title=clean_text(title)[:260] or combined[:260],
        url=url,
        text=combined[:8000],
        departure=dates[0],
        return_date=dates[1],
        airport=extract_airport(combined),
        price_eur=extract_price(combined),
        persons=int(person_match.group(1)) if person_match else None,
        nights=nights,
        board=extract_board(combined),
        destination=extract_destination(title, combined),
    )


def request(session: requests.Session, url: str):
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


def parse_source_page(source: str, response) -> list[TourDeal]:
    soup = BeautifulSoup(response.text, "html.parser")
    deals: list[TourDeal] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        card = closest_card_text(anchor)
        if not parse_date_range(card):
            continue
        url = urljoin(response.url, anchor.get("href", ""))
        if url in seen:
            continue
        title = clean_text(anchor.get("title", "") or anchor.get_text(" ", strip=True))
        deal = build_deal(source, url, title, card)
        if deal:
            deals.append(deal)
            seen.add(url)
        if len(deals) >= 60:
            break
    return deals


def search_queries() -> list[str]:
    base = [
        'Pauschalreise Strandurlaub Deutschland "24. Aug." "02. Sept." 2026',
        'Pauschalreise Meer Deutschland "25. Aug." "01. Sept." 2026',
        'Pauschalreise Meer Deutschland "26. Aug." "02. Sept." 2026',
        'Pauschalreise Strand Deutschland "27. Aug." "02. Sept." 2026',
        'Pauschalreise Strand Deutschland "28. Aug." "01. Sept." 2026',
        'Last Minute Pauschalreise Deutschland Meer Ende August 2026',
        'Familien Pauschalreise Deutschland Strand Ende August 2026',
        'All Inclusive Pauschalreise Deutschland Meer 24 25 26 27 28 August 2026',
        'Kreta Mallorca Rhodos Zypern Kroatien Pauschalreise Deutschland Ende August 2026',
        'Türkei Antalya Side Pauschalreise Deutschland Ende August 2026 02 September',
        'Kanaren Pauschalreise Deutschland Ende August 2026 02 September',
    ]
    airport_queries = [
        f'Pauschalreise Strand ab {airport} 24 August 2026 02 September 2026'
        for airport in ("Hannover", "Düsseldorf", "Paderborn", "Köln Bonn", "Dortmund", "Bremen", "Hamburg", "Berlin", "Frankfurt", "Stuttgart", "München", "Weeze")
    ]
    source_queries = [
        f'site:{domain} Pauschalreise Strand 24 25 26 27 28 August 2026 01 02 September 2026'
        for domain in (
            "check24.de", "holidaycheck.de", "weg.de", "tui.com", "dertour.de",
            "schauinsland-reisen.de", "alltours.de", "ltur.com", "ab-in-den-urlaub.de",
            "urlaubsguru.de", "urlaubspiraten.de", "sonnenklar.tv",
        )
    ]
    return base + airport_queries + source_queries


def web_discovery(session: requests.Session) -> list[TourDeal]:
    candidates: dict[str, tuple[str, str]] = {}
    for query in search_queries():
        url = f"https://www.bing.com/search?format=rss&count=30&q={quote_plus(query)}"
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
            if not link or link in candidates:
                continue
            host = urlparse(link).netloc.lower().removeprefix("www.")
            if host in {"bing.com", "microsoft.com"}:
                continue
            candidates[link] = (title, desc)
        time.sleep(0.2)

    deals: list[TourDeal] = []
    for index, (link, (search_title, search_desc)) in enumerate(candidates.items()):
        if index >= 100:
            break
        source = urlparse(link).netloc.lower().removeprefix("www.") or "web"
        fallback = clean_text(f"{search_title} {search_desc}")
        page_text = ""
        response = request(session, link)
        if response is not None:
            ctype = (response.headers.get("content-type") or "").lower()
            if not ctype or "html" in ctype:
                soup = BeautifulSoup(response.text, "html.parser")
                for node in soup(["script", "style", "noscript", "svg"]):
                    node.decompose()
                page_text = clean_text(soup.get_text(" ", strip=True))[:12000]
        deal = build_deal(f"Web/{source}", link, search_title, clean_text(f"{fallback} {page_text}"))
        if deal:
            deals.append(deal)
        time.sleep(0.15)
    return deals


def db_connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        """CREATE TABLE IF NOT EXISTS seen_tours (
               fingerprint TEXT PRIMARY KEY,
               cross_key TEXT,
               source TEXT NOT NULL,
               title TEXT NOT NULL,
               url TEXT NOT NULL,
               first_seen TEXT NOT NULL,
               last_seen TEXT NOT NULL
           )"""
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_seen_tours_cross_key ON seen_tours(cross_key)")
    db.commit()
    return db


def fingerprint(deal: TourDeal) -> str:
    return hashlib.sha256(f"{deal.source}|{deal.url}".encode()).hexdigest()


def cross_key(deal: TourDeal) -> str:
    title = re.sub(r"\W+", " ", norm(deal.title))[:80]
    airport = norm(deal.airport)
    price = int(round(deal.price_eur or 0))
    raw = f"{deal.departure}|{deal.return_date}|{airport}|{price}|{title}".encode()
    return hashlib.sha256(raw).hexdigest()


def seen_reason(db: sqlite3.Connection, deal: TourDeal) -> str:
    now = datetime.now(timezone.utc).isoformat()
    fp = fingerprint(deal)
    row = db.execute("SELECT 1 FROM seen_tours WHERE fingerprint=?", (fp,)).fetchone()
    if row:
        db.execute("UPDATE seen_tours SET last_seen=? WHERE fingerprint=?", (now, fp))
        db.commit()
        return "same-url"
    ck = cross_key(deal)
    row = db.execute("SELECT 1 FROM seen_tours WHERE cross_key=? LIMIT 1", (ck,)).fetchone()
    if row:
        return "cross-source"
    return "new"


def record_seen(db: sqlite3.Connection, deal: TourDeal) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT OR REPLACE INTO seen_tours(fingerprint,cross_key,source,title,url,first_seen,last_seen) VALUES (?,?,?,?,?,?,?)",
        (fingerprint(deal), cross_key(deal), deal.source, deal.title, deal.url, now, now),
    )
    db.commit()


def format_price(value: float | None) -> str:
    if value is None:
        return "ціна в оголошенні"
    return f"{int(round(value)):,}".replace(",", ".") + " €"


def ukrainian_summary(deal: TourDeal) -> str:
    parts = [f"Пакетний тур на море з Німеччини на {deal.nights or (deal.return_date - deal.departure).days} ноч." ]
    if deal.destination:
        parts.append(f"напрямок: {deal.destination}")
    if deal.airport:
        parts.append(f"виліт: {deal.airport}")
    if deal.board:
        parts.append(f"харчування: {deal.board}")
    if deal.persons:
        parts.append(f"ціна в джерелі вказана для {deal.persons} осіб")
    return ". ".join(parts) + "."


def send_telegram(session: requests.Session, deal: TourDeal) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    dates = f"{deal.departure.strftime('%d.%m')}–{deal.return_date.strftime('%d.%m')}"
    airport = deal.airport or "аеропорт у джерелі"
    text = (
        "🌊 ТУР НА МОРЕ — КІНЕЦЬ СЕРПНЯ\n"
        f"📅 {dates}\n"
        f"✈️ {airport}\n"
        f"🏨 {deal.title[:220]}\n"
        f"💶 {format_price(deal.price_eur)}"
        + (f" · {deal.persons} ос." if deal.persons else "")
        + (f"\n🍽 {deal.board}" if deal.board else "")
        + f"\n\n🇺🇦 {ukrainian_summary(deal)}\n\n🌐 {deal.source}\n🔗 {deal.url}"
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


def sort_key(deal: TourDeal):
    preferred = ("hannover", "paderborn", "duesseldorf", "düsseldorf", "dortmund", "muenster", "münster", "bremen", "koeln", "köln", "weeze")
    airport_score = 0 if any(term in norm(deal.airport) for term in preferred) else 1
    return (airport_score, deal.price_eur if deal.price_eur is not None else 999999, deal.departure, deal.title)


def scan_once() -> tuple[int, int]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    db = db_connect()
    found: list[TourDeal] = []

    for source, url in SOURCES:
        response = request(session, url)
        if response is None:
            continue
        items = parse_source_page(source, response)
        log(f"{source}: parsed {len(items)} matching tours")
        found.extend(items)
        time.sleep(0.4)

    try:
        discovery = web_discovery(session)
        log(f"tour web discovery: parsed {len(discovery)} matching tours")
        found.extend(discovery)
    except Exception as exc:
        log(f"tour web discovery failed safely: {type(exc).__name__}: {exc}")

    unique: dict[str, TourDeal] = {}
    for deal in found:
        unique.setdefault(deal.url, deal)

    notified = 0
    for deal in sorted(unique.values(), key=sort_key)[:MAX_ITEMS_PER_SCAN]:
        if seen_reason(db, deal) != "new":
            continue
        if notified >= MAX_NOTIFICATIONS_PER_SCAN:
            break
        if send_telegram(session, deal):
            record_seen(db, deal)
            notified += 1
            log(f"tour notified: {deal.departure} {deal.return_date} | {deal.source} | {deal.title[:90]}")
    db.close()
    return len(unique), notified


def main() -> int:
    log(f"Minden tour radar: departures {DEPARTURE_START}..{DEPARTURE_END}, return by {RETURN_BY}, all Germany")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID are required")
        return 2
    run_once = os.getenv("RUN_ONCE", "").lower() in {"1", "true", "yes"}
    while True:
        today = datetime.now(timezone.utc).date()
        if today > RETURN_BY:
            log("tour monitoring window is over; no further alerts")
            if run_once:
                return 0
            time.sleep(21600)
            continue
        try:
            total, notified = scan_once()
            log(f"tour scan complete: unique={total}, notified={notified}")
        except Exception as exc:
            log(f"tour scan failed safely: {type(exc).__name__}: {exc}")
        if run_once:
            return 0
        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
