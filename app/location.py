import re
from typing import Iterable


LOCATION_POLICY_VERSION = "germany-only-v3-strict-labelled"

GERMANY_COUNTRY_TERMS = [
    "germany",
    "deutschland",
    "deutschlandweit",
    "bundesrepublik deutschland",
    "federal republic of germany",
]

GERMAN_STATE_TERMS = [
    "baden-württemberg", "baden wurttemberg", "bavaria", "bayern", "berlin",
    "brandenburg", "bremen", "hamburg", "hesse", "hessen", "lower saxony",
    "niedersachsen", "mecklenburg-vorpommern", "mecklenburg vorpommern",
    "north rhine-westphalia", "north rhine westphalia", "nordrhein-westfalen",
    "nordrhein westfalen", "rhineland-palatinate", "rhineland palatinate",
    "rheinland-pfalz", "rheinland pfalz", "saarland", "saxony", "sachsen",
    "saxony-anhalt", "saxony anhalt", "sachsen-anhalt", "sachsen anhalt",
    "schleswig-holstein", "schleswig holstein", "thuringia", "thüringen",
    "thueringen",
]

GERMAN_CITY_TERMS = [
    "aachen", "augsburg", "berlin", "bielefeld", "bochum", "bonn",
    "braunschweig", "bremen", "bremerhaven", "brunsbüttel", "brunsbuettel",
    "chemnitz", "cologne", "cuxhaven", "dortmund", "dresden", "duisburg",
    "düsseldorf", "duesseldorf", "eckernförde", "eckernfoerde", "emden",
    "erfurt", "erlangen", "essen", "flensburg", "frankfurt", "friedrichshafen",
    "gelsenkirchen", "geesthacht", "greifswald", "hamburg", "hanover",
    "hannover", "heidelberg", "heilbronn", "husum", "ingolstadt", "itzehoe",
    "jena", "karlsruhe", "kassel", "kiel", "koblenz", "köln", "koeln",
    "krefeld", "leer", "leipzig", "lingen", "lübeck", "luebeck", "magdeburg",
    "mainz", "mannheim", "meppen", "minden", "mülheim", "muelheim", "munich",
    "münchen", "muenchen", "münster", "muenster", "neumünster", "neumuenster",
    "norderstedt", "nordenham", "nuremberg", "nürnberg", "nuernberg",
    "oldenburg", "osnabrück", "osnabrueck", "papenburg", "pinneberg", "potsdam",
    "ravensburg", "regensburg", "rendsburg", "rostock", "saarbrücken",
    "saarbruecken", "sassnitz", "schwerin", "spay", "stade", "stralsund",
    "stuttgart", "ulm", "wedel", "wilhelmshaven", "wismar", "wolfsburg",
    "wolgast", "würzburg", "wuerzburg",
]

LOCATION_LABELS = [
    "location", "job location", "primary location", "work location", "based in",
    "base location", "standort", "arbeitsort", "dienstort", "einsatzort",
]


def _normalise(value: str) -> str:
    text = (value or "").casefold()
    text = re.sub(r"[\u00a0\t\r\n]+", " ", text)
    return " ".join(text.split())


def _contains(text: str, term: str) -> bool:
    term = _normalise(term)
    if not term:
        return False
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, flags=re.UNICODE) is not None


def _first_match(text: str, terms: Iterable[str]) -> str:
    for term in terms:
        if _contains(text, term):
            return term
    return ""


def _germany_marker(text: str, *, allow_city: bool) -> str:
    normalised = _normalise(text)
    if not normalised:
        return ""
    country = _first_match(normalised, GERMANY_COUNTRY_TERMS)
    if country:
        return country
    if re.search(r"(?:^|[,;/|()\s])(?:de|deu)(?:$|[,;/|()\s])", normalised):
        return "DE"
    state = _first_match(normalised, GERMAN_STATE_TERMS)
    if state:
        return state
    if allow_city:
        city = _first_match(normalised, GERMAN_CITY_TERMS)
        if city:
            return city
    return ""


def _labelled_location_snippets(text: str) -> list[str]:
    normalised = _normalise(text)
    snippets: list[str] = []
    for label in LOCATION_LABELS:
        pattern = r"(?<!\w)" + re.escape(label) + r"(?!\w)\s*(?::|[-–—|])?\s*([^.;•|]{2,120})"
        for match in re.finditer(pattern, normalised, flags=re.UNICODE):
            snippets.append(match.group(1).strip())
    return snippets


def analyse_germany_location(title: str, description: str, explicit_location: str = "") -> dict:
    """Strict Germany-only decision.

    A structured source location is authoritative. If it is absent, a vacancy
    passes only when Germany/a German city is in the title or in an explicit
    Location/Standort/Arbeitsort-style field near the top of the posting.
    Mere mentions of Germany in prose, travel markets or company descriptions
    are deliberately ignored.
    """
    explicit = _normalise(explicit_location)
    if explicit:
        marker = _germany_marker(explicit, allow_city=True)
        if marker:
            return {"eligible": True, "display": explicit_location.strip(), "evidence": marker, "reason": "structured location is in Germany"}
        return {"eligible": False, "display": explicit_location.strip(), "evidence": "", "reason": "structured location is outside Germany or not Germany-specific"}

    title_text = _normalise(title)
    marker = _germany_marker(title_text, allow_city=True)
    if marker:
        return {"eligible": True, "display": marker, "evidence": marker, "reason": "German location appears in the vacancy title"}

    early_body = _normalise(description)[:1800]
    for snippet in _labelled_location_snippets(early_body):
        marker = _germany_marker(snippet, allow_city=True)
        if marker:
            return {"eligible": True, "display": snippet, "evidence": marker, "reason": "labelled vacancy location is in Germany"}

    return {"eligible": False, "display": explicit_location.strip() or "не определено", "evidence": "", "reason": "Germany is not confirmed by a structured or labelled job location"}
