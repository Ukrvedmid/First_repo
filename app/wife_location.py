import re


WIFE_LOCATION_POLICY_VERSION = "minden-15km-v1"


def _normalise(value: str) -> str:
    text = (value or "").casefold()
    text = text.replace("\u00a0", " ")
    return " ".join(text.split())


def _contains(text: str, term: str) -> bool:
    term = _normalise(term)
    if not term:
        return False
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, flags=re.UNICODE) is not None


def _find_match(text: str, places: list[str], postcodes: list[str]) -> str:
    normalised = _normalise(text)
    for postcode in postcodes:
        if re.search(r"(?<!\d)" + re.escape(str(postcode)) + r"(?!\d)", normalised):
            return str(postcode)
    # Longest names first avoids a short generic place name winning over a more
    # specific rendered location.
    for place in sorted(places, key=len, reverse=True):
        if _contains(normalised, place):
            return place
    return ""


def analyse_minden_radius_location(
    title: str,
    description: str,
    explicit_location: str,
    config: dict,
) -> dict:
    """Strictly accept only locations configured for the Minden 15 km search."""

    location_cfg = config.get("location", {})
    places = [str(value) for value in location_cfg.get("allowed_places", [])]
    postcodes = [str(value) for value in location_cfg.get("allowed_postcodes", [])]

    explicit = _normalise(explicit_location)
    if explicit:
        marker = _find_match(explicit, places, postcodes)
        if marker:
            return {
                "eligible": True,
                "display": explicit_location.strip(),
                "evidence": marker,
                "reason": "structured location is within configured Minden radius",
            }
        return {
            "eligible": False,
            "display": explicit_location.strip(),
            "evidence": "",
            "reason": "structured location is outside configured Minden radius",
        }

    # Fallback only to the title and top of the vacancy page. This avoids company
    # footers with office lists causing a false local match.
    early = _normalise(f"{title} {description[:1800]}")
    marker = _find_match(early, places, postcodes)
    if marker:
        return {
            "eligible": True,
            "display": marker,
            "evidence": marker,
            "reason": "local place appears near the top of the vacancy",
        }

    return {
        "eligible": False,
        "display": explicit_location.strip() or "не визначено",
        "evidence": "",
        "reason": "Minden-area location is not confirmed",
    }
