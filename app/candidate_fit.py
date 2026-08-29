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

# Evidence that the vacancy itself belongs to the maritime/ship domain. Generic
# words such as maintenance, service, commissioning or machinery do NOT count.
MARITIME_CORE_TERMS = [
    "marine",
    "maritime",
    "ship",
    "ships",
    "shipping",
    "shipowner",
    "ship management",
    "vessel",
    "vessels",
    "vessel management",
    "ship machinery",
    "marine engine",
    "ship engine",
    "ship engines",
    "marine propulsion",
    "ship propulsion",
    "shipbuilding",
    "shipyard",
    "ship repair",
    "drydock",
    "dry dock",
    "class society",
    "classification society",
    "sea-going",
    "seagoing",
    "merchant navy",
    "merchant marine",
    "offshore vessel",
    "offshore vessels",
    "offshore fleet",
    "ahts",
    "psv",
    "osv",
    "dsv",
    "mpsv",
    "dp vessel",
    "dynamic positioning",
    "schiff",
    "schiffe",
    "schifffahrt",
    "seeschifffahrt",
    "seefahrt",
    "schiffbau",
    "schiffsbetrieb",
    "schiffsbetriebstechnik",
    "schiffstechnik",
    "schiffsmaschine",
    "schiffsmaschinen",
    "schiffsmotor",
    "schiffsmotoren",
    "schiffsantrieb",
    "schiffswerft",
    "werftzeit",
    "trockendock",
    "klassifikationsgesellschaft",
]

# Strong signs that the employer explicitly values experience brought ashore
# from ships. These should receive extra weight.
SEA_TO_SHORE_TERMS = [
    "chief engineer",
    "second engineer",
    "senior engineer officer",
    "engineer officer",
    "marine engineer certificate",
    "chief engineer certificate",
    "certificate of competency",
    "coc",
    "seagoing experience",
    "sea-going experience",
    "sailing experience",
    "experience at sea",
    "experience on board",
    "onboard experience",
    "shipboard experience",
    "former chief engineer",
    "marine engineering background",
    "schiffsbetriebstechniker",
    "schiffsbetriebsingenieur",
    "seefahrtserfahrung",
    "bord-erfahrung",
    "borderfahrung",
    "fahrenszeit",
    "patent als leitender ingenieur",
    "leitender ingenieur",
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

# Hard rejects for industries that can share technical vocabulary with marine
# engineering but are not a realistic sea-to-shore transition for this search.
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
    "mechatroniker",
    "mechatronics technician",
    "automotive technician",
    "vehicle technician",
    "kfz-mechatroniker",
    "kfz mechatroniker",
    "fahrzeugmechatroniker",
    "production technician",
    "manufacturing technician",
]

HARD_MISMATCH_COMPANY_TERMS = [
    "tesla gigafactory",
    "tesla manufacturing",
    "automotive production",
    "automobilproduktion",
    "fahrzeugproduktion",
    "car manufacturing",
    "vehicle manufacturing",
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
    key = _normalise(term)
    if not key:
        return False
    return re.search(
        r"(?<!\w)" + re.escape(key) + r"(?!\w)",
        text,
        flags=re.UNICODE,
    ) is not None


def _hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if _contains(text, term)]


def analyse_candidate_fit(title: str, description: str) -> dict:
    """Judge fit to a senior ship-engine / Chief Engineer sea-to-shore profile.

    The vacancy must be genuinely maritime. German-language adverts are fully
    acceptable and do not need to state that English alone is sufficient.
    Strong mandatory German is reported as a warning, while non-maritime
    automotive/industrial roles are rejected even when technical vocabulary
    overlaps with ship engineering.
    """
    title_text = _normalise(title)
    body_text = _normalise(description)
    combined = f"{title_text} {body_text}"

    mismatch = _hits(title_text, HARD_MISMATCH_TITLE_TERMS)
    mismatch_company = _hits(combined, HARD_MISMATCH_COMPANY_TERMS)
    if mismatch or mismatch_company:
        reasons = mismatch + mismatch_company
        return {
            "eligible": False,
            "score": 0,
            "reasons": [],
            "language_warning": False,
            "reject_reason": f"non-maritime/automotive mismatch: {', '.join(reasons[:3])}",
        }

    direct = _hits(title_text, DIRECT_SHORE_TITLES)
    maritime = _hits(combined, MARITIME_CORE_TERMS)
    sea_to_shore = _hits(combined, SEA_TO_SHORE_TERMS)
    machinery = _hits(combined, MACHINERY_TERMS)
    responsibility = _hits(combined, RESPONSIBILITY_TERMS)
    language_warning = bool(_hits(combined, STRONG_GERMAN_TERMS))

    # Absolute domain gate: no explicit ship/marine evidence means no delivery.
    # Direct maritime shore titles are accepted as maritime evidence themselves.
    maritime_domain = bool(direct or maritime)
    if not maritime_domain:
        return {
            "eligible": False,
            "score": 0,
            "reasons": [],
            "language_warning": language_warning,
            "reject_reason": "no explicit ship/marine domain evidence",
        }

    score = min(40, len(direct) * 20)
    score += min(24, len(maritime) * 4)
    score += min(30, len(sea_to_shore) * 10)
    score += min(30, len(machinery) * 5)
    score += min(20, len(responsibility) * 4)

    # Direct superintendent/survey roles still need technical-engineering
    # evidence. Generic service/project roles need both maritime evidence and a
    # clear machinery/maintenance/technical responsibility connection.
    if direct:
        eligible = bool(machinery or sea_to_shore) and score >= 30
    else:
        eligible = (
            len(maritime) >= 1
            and len(machinery) >= 2
            and len(responsibility) >= 1
            and score >= 32
        )

    reasons = []
    if direct:
        reasons.append("direct maritime shore title")
    if sea_to_shore:
        reasons.append("sea-going experience valued: " + ", ".join(sea_to_shore[:4]))
    if maritime:
        reasons.append("maritime domain: " + ", ".join(maritime[:4]))
    if machinery:
        reasons.append("ship machinery/maintenance fit: " + ", ".join(machinery[:5]))
    if responsibility:
        reasons.append("relevant shore duties: " + ", ".join(responsibility[:4]))

    return {
        "eligible": eligible,
        "score": score,
        "reasons": reasons,
        "language_warning": language_warning,
        "reject_reason": "" if eligible else "insufficient sea-to-shore / ship mechanical engineering fit",
    }
