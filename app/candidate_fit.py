import re


DIRECT_SHORE_TITLES = [
    "technical superintendent",
    "assistant technical superintendent",
    "marine superintendent",
    "ship superintendent",
    "technical vessel manager",
    "vessel manager",
    "port engineer",
    "marine surveyor",
    "ship surveyor",
    "marine inspector",
    "schiffsinspektor",
    "technischer superintendent",
]

MACHINERY_TERMS = [
    "chief engineer",
    "marine engineer",
    "marine engineering",
    "ship machinery",
    "ship engine",
    "ship engines",
    "marine diesel",
    "diesel engine",
    "main engine",
    "auxiliary engine",
    "generator",
    "genset",
    "propulsion",
    "thruster",
    "azimuth thruster",
    "gearbox",
    "shaft line",
    "steering gear",
    "pumps",
    "hydraulics",
    "planned maintenance system",
    "pms",
    "drydock",
    "dry dock",
    "ship repair",
    "overhaul",
    "maintenance",
    "troubleshooting",
    "commissioning",
    "sea trials",
    "retrofit",
    "schiffsbetriebstechnik",
    "schiffsmaschine",
    "schiffsmaschinen",
    "schiffsmotor",
    "schiffsmotoren",
    "schiffsantrieb",
    "wartung",
    "instandhaltung",
    "reparatur",
    "fehlersuche",
    "störungsbehebung",
    "inbetriebnahme",
]

RESPONSIBILITY_TERMS = [
    "technical management",
    "fleet management",
    "vessel management",
    "technical support",
    "field service",
    "service engineer",
    "service technician",
    "maintenance planning",
    "repair planning",
    "drydock planning",
    "class survey",
    "classification society",
    "spares",
    "spare parts",
    "budget",
    "superintendent",
    "technical inspection",
    "technische betreuung",
    "technischer support",
    "außendienst",
    "instandhaltungsplanung",
    "ersatzteile",
    "werft",
]

HARD_MISMATCH_TITLE_TERMS = [
    "software developer",
    "software engineer",
    "data engineer",
    "sales manager",
    "account manager",
    "hr manager",
    "recruiter",
    "warehouse",
    "lager",
    "logistikmitarbeiter",
    "elektroniker für gebäudetechnik",
    "bauingenieur hochbau",
]

STRONG_GERMAN_TERMS = [
    "deutsch auf muttersprachniveau",
    "muttersprachliche deutschkenntnisse",
    "verhandlungssicheres deutsch",
    "verhandlungssichere deutschkenntnisse",
    "deutsch c1",
    "german c1",
    "german at native level",
]


def _normalise(value: str) -> str:
    return " ".join((value or "").casefold().split())


def _contains(text: str, term: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(_normalise(term)) + r"(?!\w)", text, flags=re.UNICODE) is not None


def _hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if _contains(text, term)]


def analyse_candidate_fit(title: str, description: str) -> dict:
    """Judge fit to a senior ship-engine / Chief Engineer background.

    Language policy is intentionally permissive: a German-language advert does
    not need to state that English is sufficient. Strong mandatory German is a
    warning, not an automatic rejection. The hard gate is professional fit.
    """
    title_text = _normalise(title)
    body_text = _normalise(description)
    combined = f"{title_text} {body_text}"

    mismatch = _hits(title_text, HARD_MISMATCH_TITLE_TERMS)
    if mismatch:
        return {
            "eligible": False,
            "score": 0,
            "reasons": [],
            "language_warning": False,
            "reject_reason": f"title mismatch: {', '.join(mismatch[:3])}",
        }

    direct = _hits(title_text, DIRECT_SHORE_TITLES)
    machinery = _hits(combined, MACHINERY_TERMS)
    responsibility = _hits(combined, RESPONSIBILITY_TERMS)
    language_warning = bool(_hits(combined, STRONG_GERMAN_TERMS))

    score = min(40, len(direct) * 20)
    score += min(36, len(machinery) * 6)
    score += min(24, len(responsibility) * 4)

    # Direct superintendent/survey roles need at least one technical machinery
    # signal. Generic project/service roles need broader machinery evidence.
    if direct:
        eligible = bool(machinery) and score >= 26
    else:
        eligible = len(machinery) >= 2 and len(responsibility) >= 1 and score >= 24

    reasons = []
    if direct:
        reasons.append("direct ship-to-shore title")
    if machinery:
        reasons.append("ship machinery/maintenance: " + ", ".join(machinery[:5]))
    if responsibility:
        reasons.append("relevant duties: " + ", ".join(responsibility[:4]))

    return {
        "eligible": eligible,
        "score": score,
        "reasons": reasons,
        "language_warning": language_warning,
        "reject_reason": "" if eligible else "insufficient fit to ship mechanical engineering / Chief Engineer background",
    }
