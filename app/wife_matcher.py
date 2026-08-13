import re


WIFE_MATCH_POLICY_VERSION = "wife-local-a1-b1-v1"


def _normalise(value: str) -> str:
    return " ".join((value or "").casefold().split())


def _contains(text: str, term: str) -> bool:
    term = _normalise(term)
    if not term:
        return False
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, flags=re.UNICODE) is not None


def _matches(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if _contains(text, str(term))]


def analyse_language(description: str, config: dict) -> dict:
    text = _normalise(description)
    profile = config.get("profile", {})
    rejected = _matches(text, profile.get("language_reject", []))
    allowed = _matches(text, profile.get("language_allowed", []))

    if rejected:
        return {
            "eligible": False,
            "level": "вище B1",
            "evidence": rejected[:3],
            "warning": "В оголошенні прямо вимагають німецьку вище B1.",
        }

    level = "не вказано"
    if any("b1" in term.casefold() for term in allowed):
        level = "B1"
    elif any("a2" in term.casefold() for term in allowed):
        level = "A2"
    elif any("a1" in term.casefold() for term in allowed):
        level = "A1"
    elif allowed:
        level = "A1–B1 / базова німецька"

    ambiguous = []
    for phrase in (
        "gute deutschkenntnisse",
        "gutes deutsch",
        "deutschkenntnisse erforderlich",
        "deutschkenntnisse notwendig",
        "kommunikationssichere deutschkenntnisse",
    ):
        if phrase in text:
            ambiguous.append(phrase)

    warning = ""
    if ambiguous and not allowed:
        level = "рівень не уточнений — перевірити"
        warning = "Німецька потрібна, але рівень A1/A2/B1 прямо не зазначений."
    elif not allowed and "deutsch" in text:
        level = "рівень не уточнений"
        warning = "У вакансії згадується німецька, але без конкретного рівня."
    elif not allowed:
        warning = "Рівень німецької в оголошенні не вказаний; це треба уточнити у роботодавця."

    return {
        "eligible": True,
        "level": level,
        "evidence": allowed[:4],
        "warning": warning,
    }


def analyse_wife_job(title: str, description: str, config: dict) -> dict:
    title_text = _normalise(title)
    body_text = _normalise(description)
    profile = config.get("profile", {})

    priority = _matches(title_text, profile.get("priority_titles", []))
    bridge = _matches(title_text, profile.get("bridge_titles", []))
    negatives = _matches(title_text, profile.get("negative_titles", []))
    positive_body = _matches(body_text, profile.get("positive_terms", []))
    language = analyse_language(description, config)

    if negatives:
        return {
            "exclude": True,
            "score": 0,
            "tier": "X",
            "category": "не підходить",
            "matched": negatives,
            "language": language,
            "gaps": ["Назва вакансії належить до виключеної категорії."],
        }

    if not language["eligible"]:
        return {
            "exclude": True,
            "score": 0,
            "tier": "X",
            "category": "німецька вище B1",
            "matched": [],
            "language": language,
            "gaps": [language["warning"]],
        }

    # Only role families explicitly selected for this agent are allowed. This
    # prevents the broad Quereinstieg search from flooding the family chat.
    if not priority and not bridge:
        return {
            "exclude": True,
            "score": 0,
            "tier": "X",
            "category": "поза профілем",
            "matched": [],
            "language": language,
            "gaps": [],
        }

    score = 0
    if priority:
        score += 15 + min(10, (len(priority) - 1) * 4)
    if bridge:
        score += 8 + min(6, (len(bridge) - 1) * 3)
    score += min(8, len(positive_body) * 2)

    if language["level"] == "A1":
        score += 6
    elif language["level"] == "A2":
        score += 5
    elif language["level"] == "B1":
        score += 4
    elif "A1–B1" in language["level"]:
        score += 3

    gaps: list[str] = []
    qualification_phrases = (
        "staatlich anerkannte erzieher",
        "staatlich anerkannter erzieher",
        "abgeschlossene ausbildung als erzieher",
        "abgeschlossene pädagogische ausbildung",
        "pädagogische fachkraft",
        "pflegefachkraft",
        "examinierte pflegefachkraft",
        "führerschein klasse b",
        "fuehrerschein klasse b",
    )
    for phrase in qualification_phrases:
        if phrase in body_text:
            if "führerschein" in phrase or "fuehrerschein" in phrase:
                gaps.append("Потрібні водійські права Klasse B — перевірити наявність.")
            elif "pflegefachkraft" in phrase:
                gaps.append("Може вимагатися визнана професійна кваліфікація у догляді.")
            else:
                gaps.append("Може вимагатися визнана педагогічна кваліфікація — перевірити формальні вимоги.")
            break

    if language.get("warning"):
        gaps.append(language["warning"])

    if priority:
        tier = "A"
        category = "пріоритетна вакансія"
    else:
        tier = "B"
        category = "реалістичний запасний варіант"

    matched = []
    for term in priority + bridge + positive_body:
        if term not in matched:
            matched.append(term)

    return {
        "exclude": False,
        "score": score,
        "tier": tier,
        "category": category,
        "matched": matched,
        "language": language,
        "gaps": gaps[:4],
    }
