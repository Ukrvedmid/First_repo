import re


def score_job(title: str, description: str, config: dict) -> tuple[int, list[str]]:
    text = f"{title}\n{description}".lower()
    score = 0
    matched = []
    for term in config.get('keywords', {}).get('strong', []):
        if re.search(r'\b' + re.escape(term.lower()) + r'\b', text):
            score += 4
            matched.append(term)
    for term in config.get('keywords', {}).get('weak', []):
        if re.search(r'\b' + re.escape(term.lower()) + r'\b', text):
            score += 1
            matched.append(term)
    return score, matched
