import re
from typing import Iterable


DEFAULT_SEA_TERMS = [
    "chief engineer",
    "relief chief engineer",
    "offshore chief engineer",
    "first engineer",
    "second engineer",
    "rov pilot technician",
    "senior rov pilot technician",
    "trainee rov pilot technician",
    "rov supervisor",
    "subsea technician",
    "subsea engineer",
]

DEFAULT_CLOSED_PHRASES = [
    "this job is no longer taking applications",
    "this position is no longer available",
    "this vacancy is no longer available",
    "applications are closed",
    "application period has ended",
    "position has been filled",
    "job posting is offline",
    "the job posting is offline",
    "job you are trying to apply for has been filled",
    "stelle steht leider nicht mehr zur verfügung",
    "diese stelle ist nicht mehr verfügbar",
    "bewerbungsfrist abgelaufen",
    "stelle wurde bereits besetzt",
    "stellenanzeige ist offline",
    "vacature is niet meer beschikbaar",
]

DIRECT_SHORE_TITLE_TERMS = [
    "technical superintendent",
    "fleet technical superintendent",
    "senior technical superintendent",
    "assistant technical superintendent",
    "marine superintendent",
    "fleet superintendent",
    "ship superintendent",
    "newbuilding superintendent",
    "drydock superintendent",
    "technical vessel manager",
    "technical fleet manager",
    "vessel manager",
    "fleet manager",
    "fleet maintenance manager",
    "fleet maintenance superintendent",
    "port engineer",
    "technical operations manager",
    "marine surveyor",
    "surveyor engineer",
    "approval engineer",
    "technical expert marine",
    "marine technical expert",
    "technical controller maritime",
    "marine assurance advisor",
    "dp assurance engineer",
    "dp fmea surveyor",
    "technischer superintendent",
    "technischer inspektor",
    "technischer flottenmanager",
    "technischer schiffsinspektor",
    "schiffsinspektor",
    "technischer experte marine",
    "technischer experte schifffahrt",
]

CLASS_SURVEY_TERMS = [
    "marine surveyor",
    "marine warranty surveyor",
    "surveyor engineer",
    "approval engineer",
    "technical inspector",
    "ship surveyor",
    "machinery surveyor",
    "marine inspector",
    "technical expert marine",
    "marine technical expert",
    "marine customer center",
    "technischer inspektor",
    "technischer experte marine",
    "besichtiger marine",
    "besichtiger schiff",
    "technischer sachverständiger schifffahrt",
    "sachverständiger schiffstechnik",
    "besichtiger schiffbau",
    "classification society",
    "class society",
    "klassifikationsgesellschaft",
]

OEM_SERVICE_TERMS = [
    "field service engineer",
    "senior field service engineer",
    "field service engineer marine",
    "service engineer",
    "service engineer marine",
    "marine service engineer",
    "service technician marine",
    "marine service technician",
    "service manager marine",
    "service project manager marine",
    "commissioning engineer",
    "commissioning manager",
    "technical support engineer",
    "project engineer technical support",
    "serviceingenieur",
    "serviceingenieur marine",
    "serviceingenieur schiff",
    "inbetriebnahmeingenieur",
    "inbetriebnahmetechniker",
    "servicetechniker",
    "service-techniker außendienst",
    "kundendienstingenieur",
    "leitender serviceingenieur",
    "projektingenieur technischer support",
    "chefmonteur",
]

PROJECT_OPERATIONS_TERMS = [
    "project engineer",
    "marine project engineer",
    "project engineer shipbuilding",
    "project manager",
    "project manager shipbuilding",
    "project manager marine projects",
    "marine projects manager",
    "shipbuilding project manager",
    "technical project manager",
    "maintenance engineer",
    "maintenance manager",
    "maintenance coordinator",
    "maintenance planner",
    "reliability engineer",
    "operations engineer",
    "operations governance manager",
    "asset manager",
    "fleet performance manager",
    "fleet performance engineer",
    "vessel performance manager",
    "vessel performance engineer",
    "site manager",
    "shipbuilding engineer",
    "naval architect",
    "projektingenieur",
    "projektingenieur schiffbau",
    "projektleiter",
    "projektleiter schiffbau",
    "projektleiter marineprojekte",
    "projektleitung marineprojekte international",
    "projektmanager schiffbau",
    "instandhaltungsingenieur",
    "instandhaltungskoordinator",
    "instandhaltungsmanager",
    "instandhaltungsleiter",
    "betriebsingenieur",
    "schiffsbetriebsingenieur",
    "schiffbauingenieur",
    "schiffbau-ingenieur",
    "technischer projektleiter",
    "bauleiter schiffbau",
    "bauleiter offshore",
    "terminplaner",
]

OFFSHORE_WIND_TERMS = [
    "offshore wind",
    "offshore site manager",
    "offshore installation",
    "wind turbine",
    "windenergie",
    "windkraft",
    "offshore service technician",
    "production manager sov",
    "sov manager",
    "service operation vessel",
    "offshore operations manager",
    "offshore production manager",
    "o&m concept expert",
    "o&m manager offshore",
    "operations governance manager",
    "offshore asset manager",
    "offshore maintenance manager",
    "offshore operations engineer",
    "offshore maintenance engineer",
    "marine operations manager",
    "marine operations coordinator",
    "bauleiter offshore",
]

# These rules do not reject a vacancy. They highlight likely barriers that need
# human review or a tailored CV. They reflect the current candidate profile:
# Chief Engineer / marine engineer, strong English, early-stage German, no
# confirmed LNG-superintendent or wind-turbine-specific shore experience.
POTENTIAL_GAP_RULES = [
    (
        "требуется сильный немецкий (обычно B2–C1)",
        [
            "verhandlungssicher deutsch",
            "verhandlungssichere deutschkenntnisse",
            "sehr gute deutschkenntnisse",
            "fließende deutschkenntnisse",
            "fliessende deutschkenntnisse",
            "deutsch auf muttersprachniveau",
            "german at native level",
            "fluent german",
            "german c1",
            "german b2",
        ],
    ),
    (
        "нужен подтверждённый опыт LNG/LNG-STS",
        [
            "lng bunker vessel",
            "lng bunker vessels",
            "lng carrier",
            "lng carriers",
            "lng sts",
            "ship-to-ship transfer",
        ],
    ),
    (
        "могут требовать прежний shore-опыт Technical Superintendent",
        [
            "experience as a technical superintendent",
            "professional experience as a technical superintendent",
            "years as a technical superintendent",
            "berufserfahrung als technical superintendent",
        ],
    ),
    (
        "может требоваться профильное образование по электрике/автоматике",
        [
            "degree in electrical engineering",
            "bachelor in electrical engineering",
            "master in electrical engineering",
            "studium der elektrotechnik",
            "abgeschlossenes studium der elektrotechnik",
            "elektrotechnik (bachelor",
            "informationstechnik (bachelor",
        ],
    ),
    (
        "может требоваться прямой опыт эксплуатации offshore wind/WTG",
        [
            "experience managing operations on offshore wind farms",
            "experience in offshore wind farm operations",
            "knowledge of wind turbine generators",
            "kenntnisse über die organisation und den betrieb von offshore-windparks",
            "kenntnisse über den betrieb und die wartung von windkraftanlagen",
        ],
    ),
    (
        "PMI/IPMA указана как желательная или обязательная",
        ["pmi certification", "ipma certification", "zertifizierung nach pmi", "zertifizierung nach ipma"],
    ),
    (
        "нужна специальная HSE-квалификация SiFa/NEBOSH",
        ["fachkraft für arbeitssicherheit", "sifa", "nebosh"],
    ),
    (
        "возможны ограничения security clearance/defence",
        [
            "security clearance",
            "national security vetting",
            "sicherheitsüberprüfung",
            "defence sector",
            "verteidigungssektor",
        ],
    ),
]


def _normalise(value: str) -> str:
    return " ".join((value or "").casefold().split())


def _contains(text: str, term: str) -> bool:
    normalised_term = _normalise(term)
    if not normalised_term:
        return False
    return re.search(
        r"(?<!\w)" + re.escape(normalised_term) + r"(?!\w)",
        text,
        flags=re.UNICODE,
    ) is not None


def _matches(text: str, terms: Iterable[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = _normalise(term)
        if key and key not in seen and _contains(text, term):
            found.append(term)
            seen.add(key)
    return found


def _new_matches(body_matches: list[str], title_matches: list[str]) -> list[str]:
    title_keys = {_normalise(term) for term in title_matches}
    return [term for term in body_matches if _normalise(term) not in title_keys]


def _route_for_job(title_text: str, body_text: str, sea_terms: list[str]) -> str:
    combined = f"{title_text} {body_text}"

    if _matches(title_text, sea_terms):
        return "Море / offshore"
    if _matches(title_text, CLASS_SURVEY_TERMS):
        return "Берег: класс, survey и инспекции"
    if _matches(title_text, DIRECT_SHORE_TITLE_TERMS):
        return "Берег: управление флотом"
    if _matches(title_text, OFFSHORE_WIND_TERMS) or _matches(combined, OFFSHORE_WIND_TERMS):
        return "Берег / ротация: offshore wind и SOV operations"
    if _matches(title_text, OEM_SERVICE_TERMS):
        return "Берег / выезды: OEM service и commissioning"
    if _matches(title_text, PROJECT_OPERATIONS_TERMS):
        return "Берег: проекты, shipbuilding, maintenance и operations"
    return "Смежная инженерная вакансия"


def _potential_gaps(title_text: str, body_text: str) -> list[str]:
    combined = f"{title_text} {body_text}"
    gaps: list[str] = []
    for label, phrases in POTENTIAL_GAP_RULES:
        if _matches(combined, phrases):
            gaps.append(label)
    return gaps


def analyse_job(title: str, description: str, config: dict) -> dict:
    title_text = _normalise(title)
    body_text = _normalise(description)
    early_body = body_text[:2500]

    keyword_groups = config.get("keywords", {})
    priority_terms = keyword_groups.get("priority", [])
    strong_terms = keyword_groups.get("strong", [])
    bridge_terms = keyword_groups.get("bridge", [])
    weak_terms = keyword_groups.get("weak", [])
    negative_terms = keyword_groups.get("negative", [])
    sea_terms = keyword_groups.get("sea", DEFAULT_SEA_TERMS)
    closed_terms = config.get("closed_phrases", DEFAULT_CLOSED_PHRASES)

    priority_title = _matches(title_text, priority_terms)
    priority_body = _new_matches(_matches(body_text, priority_terms), priority_title)
    sea_title = _matches(title_text, sea_terms)
    sea_body = _new_matches(_matches(body_text, sea_terms), sea_title)
    strong_title = _matches(title_text, strong_terms)
    strong_body = _new_matches(_matches(body_text, strong_terms), strong_title)
    bridge_title = _matches(title_text, bridge_terms)
    bridge_body = _new_matches(_matches(body_text, bridge_terms), bridge_title)
    weak_title = _matches(title_text, weak_terms)
    weak_body = _new_matches(_matches(body_text, weak_terms), weak_title)
    negative_title = _matches(title_text, negative_terms)
    negative_body = _new_matches(_matches(early_body, negative_terms), negative_title)
    closed_matches = _matches(body_text, closed_terms)

    location_matches = _matches(
        f"{title_text} {body_text}",
        config.get("priority_locations", []),
    )

    score = 0
    score += min(28, len(priority_title) * 14)
    score += min(14, len(priority_body) * 7)
    score += min(24, len(sea_title) * 12)
    score += min(12, len(sea_body) * 6)
    score += min(14, len(strong_title) * 7)
    score += min(12, len(strong_body) * 3)
    score += min(10, len(bridge_title) * 5)
    score += min(6, len(bridge_body) * 2)
    score += min(4, len(weak_title) * 2)
    score += min(6, len(weak_body))
    score += min(5, len(location_matches) * 3)
    score -= min(40, len(negative_title) * 30)
    score -= min(12, len(negative_body) * 6)

    # Generic project/service titles should not outrank marine-specific jobs unless
    # the description confirms relevant machinery, maritime, offshore,
    # maintenance, commissioning or energy experience.
    direct_shore = bool(_matches(title_text, DIRECT_SHORE_TITLE_TERMS))
    has_domain_evidence = bool(strong_title or strong_body or sea_title or sea_body)
    if priority_title and not direct_shore and not has_domain_evidence:
        score -= 9

    score = max(0, score)
    route = _route_for_job(title_text, body_text, sea_terms)
    gaps = _potential_gaps(title_text, body_text)
    exclude = bool(negative_title or closed_matches)

    if closed_matches:
        tier = "X — вакансия закрыта"
    elif negative_title:
        tier = "X — исключить"
    elif direct_shore or sea_title:
        tier = "A — прямое попадание"
    elif priority_title and has_domain_evidence:
        tier = "A — высокая релевантность"
    elif priority_title or bridge_title or (strong_title and location_matches):
        tier = "B — хороший переход"
    else:
        tier = "C — смежная"

    if tier.startswith("A") and not gaps:
        recommendation = "ПОДАВАТЬ СРАЗУ"
    elif tier.startswith("A"):
        recommendation = "ПОДАВАТЬ, закрыв пробелы в CV/письме"
    elif tier.startswith("B"):
        recommendation = "РАССМОТРЕТЬ КАК ПЕРЕХОД НА БЕРЕГ"
    else:
        recommendation = "РЕЗЕРВ — проверка вручную"

    matched: list[str] = []
    matched_keys: set[str] = set()
    for group in (
        priority_title,
        sea_title,
        strong_title,
        bridge_title,
        priority_body,
        sea_body,
        strong_body,
        bridge_body,
        weak_title,
        weak_body,
    ):
        for term in group:
            key = _normalise(term)
            if key not in matched_keys:
                matched.append(term)
                matched_keys.add(key)

    return {
        "score": score,
        "matched": matched,
        "route": route,
        "tier": tier,
        "recommendation": recommendation,
        "locations": location_matches,
        "potential_gaps": gaps,
        "negative": negative_title + negative_body,
        "closed": closed_matches,
        "exclude": exclude,
    }


def score_job(title: str, description: str, config: dict) -> tuple[int, list[str]]:
    """Backward-compatible wrapper for older callers."""
    result = analyse_job(title, description, config)
    return result["score"], result["matched"]
