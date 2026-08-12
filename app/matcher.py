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
    "stelle steht leider nicht mehr zur verfügung",
    "diese stelle ist nicht mehr verfügbar",
    "bewerbungsfrist abgelaufen",
    "stelle wurde bereits besetzt",
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
    "port engineer",
    "technical operations manager",
    "marine surveyor",
    "surveyor engineer",
    "approval engineer",
    "technischer superintendent",
    "technischer inspektor",
    "technischer flottenmanager",
    "technischer schiffsinspektor",
    "schiffsinspektor",
]

CLASS_SURVEY_TERMS = [
    "marine surveyor",
    "marine warranty surveyor",
    "surveyor engineer",
    "approval engineer",
    "technical inspector",
    "technischer inspektor",
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
    "commissioning engineer",
    "commissioning manager",
    "technical support engineer",
    "serviceingenieur",
    "serviceingenieur marine",
    "serviceingenieur schiff",
    "inbetriebnahmeingenieur",
    "inbetriebnahmetechniker",
    "servicetechniker",
    "kundendienstingenieur",
    "leitender serviceingenieur",
    "chefmonteur",
]

PROJECT_OPERATIONS_TERMS = [
    "project engineer",
    "marine project engineer",
    "project engineer shipbuilding",
    "project manager",
    "project manager shipbuilding",
    "shipbuilding project manager",
    "technical project manager",
    "maintenance engineer",
    "maintenance manager",
    "reliability engineer",
    "operations engineer",
    "asset manager",
    "site manager",
    "shipbuilding engineer",
    "naval architect",
    "projektingenieur",
    "projektingenieur schiffbau",
    "projektleiter",
    "projektleiter schiffbau",
    "projektmanager schiffbau",
    "instandhaltungsingenieur",
    "betriebsingenieur",
    "schiffsbetriebsingenieur",
    "schiffbauingenieur",
    "schiffbau-ingenieur",
    "technischer projektleiter",
    "bauleiter schiffbau",
    "bauleiter offshore",
]

OFFSHORE_WIND_TERMS = [
    "offshore wind",
    "offshore site manager",
    "offshore installation",
    "wind turbine",
    "windenergie",
    "windkraft",
    "offshore service technician",
    "bauleiter offshore",
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
        return "Берег / выезды: offshore wind"
    if _matches(title_text, OEM_SERVICE_TERMS):
        return "Берег / выезды: OEM service и commissioning"
    if _matches(title_text, PROJECT_OPERATIONS_TERMS):
        return "Берег: проекты, shipbuilding, maintenance и operations"
    return "Смежная инженерная вакансия"


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
        "locations": location_matches,
        "negative": negative_title + negative_body,
        "closed": closed_matches,
        "exclude": exclude,
    }


def score_job(title: str, description: str, config: dict) -> tuple[int, list[str]]:
    """Backward-compatible wrapper for older callers."""
    result = analyse_job(title, description, config)
    return result["score"], result["matched"]
