"""
ClairDiag v3 — Common Symptom Mapper v3.0.2

Фікси:
  - нормалізація апострофів до єдиного формату
  - matched_phrases зберігаються в all_hits
  - matched_symptoms повертається окремо
  - ВИПРАВЛЕНО: рахуємо ВСІ matched phrases всередині entry (без break)
"""

import re
from typing import Dict, List, Tuple, Optional
from loader import (
    COMMON_SYMPTOM_MAPPING,
    URGENT_TRIGGERS,
    URGENT_MESSAGE,
)


def normalize_text(text: str) -> str:
    text = text.lower()
    for ch in ["\u2019", "\u2018", "\u02bc", "\u0060", "\u00b4"]:
        text = text.replace(ch, "'")
    text = re.sub(r"[^\w\sàâäéèêëîïôöùûüç\-']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_phrase(phrase: str) -> str:
    phrase = phrase.lower()
    for ch in ["\u2019", "\u2018", "\u02bc", "\u0060", "\u00b4"]:
        phrase = phrase.replace(ch, "'")
    return phrase


_NEGATION_PREFIXES = ["pas de", "pas", "aucun", "aucune", "jamais", "sans"]


def _is_negated(text: str, phrase: str) -> bool:
    idx = text.find(phrase)
    if idx == -1:
        return False
    window = text[max(0, idx - 25):idx]
    return any(neg in window for neg in _NEGATION_PREFIXES)


_TEMPORAL_MAP = {
    "brutal": "acute",
    "d'un coup": "acute",
    "soudain": "acute",
    "depuis aujourd'hui": "acute",
    "depuis hier": "acute",
    "depuis 2 jours": "subacute",
    "depuis quelques jours": "subacute",
    "depuis 10 jours": "subacute",
    "depuis 2 semaines": "chronic",
    "depuis quelques semaines": "chronic",
    "depuis plusieurs semaines": "chronic",
    "depuis 3 semaines": "chronic",
    "depuis 1 mois": "chronic",
    "depuis plusieurs mois": "chronic",
    "depuis longtemps": "chronic",
    "depuis 2 mois": "chronic",
    "depuis des mois": "chronic",
    "depuis quelques mois": "chronic",
}

_DURATION_PATTERNS = [
    (r"depuis\s+(\d+)\s+jour", 1),
    (r"depuis\s+(\d+)\s+semaine", 7),
    (r"depuis\s+(\d+)\s+mois", 30),
]


def extract_temporal(text: str) -> str:
    for phrase, value in _TEMPORAL_MAP.items():
        if phrase in text:
            return value
    return "unknown"


def extract_duration_days(text: str) -> Optional[int]:
    for pattern, multiplier in _DURATION_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return int(m.group(1)) * multiplier
    if "depuis hier" in text:
        return 1
    if "depuis aujourd'hui" in text:
        return 0
    if "depuis quelques jours" in text:
        return 3
    if "depuis quelques semaines" in text:
        return 21
    if "depuis plusieurs mois" in text:
        return 90
    return None


_INTENSITY_MAP = {
    "très mal": "high",
    "très fort": "high",
    "intense": "high",
    "insupportable": "high",
    "un peu": "low",
    "léger": "low",
    "légère": "low",
    "petite": "low",
    "petit peu": "low",
}


def extract_intensity(text: str) -> str:
    for phrase in sorted(_INTENSITY_MAP, key=len, reverse=True):
        if phrase in text:
            return _INTENSITY_MAP[phrase]
    return "normal"


def check_urgent_triggers(text: str) -> Optional[str]:
    for expr in URGENT_TRIGGERS:
        if normalize_phrase(expr) in text:
            return expr
    return None


def common_symptom_mapper(free_text: str) -> Dict:
    text = normalize_text(free_text)

    urgent = check_urgent_triggers(text)
    if urgent:
        return {
            "category": None,
            "category_matches": 0,
            "all_hits": [],
            "matched_symptoms": [],
            "urgent_trigger": urgent,
            "urgent_message": URGENT_MESSAGE,
            "temporal": extract_temporal(text),
            "intensity": extract_intensity(text),
            "duration_days": extract_duration_days(text),
        }

    category_votes: Dict[str, int] = {}
    category_priority: Dict[str, int] = {}
    all_hits: List[Tuple[str, int, str]] = []

    for mapping in COMMON_SYMPTOM_MAPPING:
        cat = mapping["category"]
        priority = mapping["priority"]
        # ФІКС: рахуємо ВСІ matched phrases в entry, не тільки першу
        for phrase in mapping["patient_expressions"]:
            norm_phrase = normalize_phrase(phrase)
            if norm_phrase in text and not _is_negated(text, norm_phrase):
                category_votes[cat] = category_votes.get(cat, 0) + 1
                if priority > category_priority.get(cat, 0):
                    category_priority[cat] = priority
                all_hits.append((cat, priority, phrase))
                # НЕ break — продовжуємо рахувати всі матчі в цьому entry

    if not category_votes:
        return {
            "category": None,
            "category_matches": 0,
            "all_hits": [],
            "matched_symptoms": [],
            "urgent_trigger": None,
            "temporal": extract_temporal(text),
            "intensity": extract_intensity(text),
            "duration_days": extract_duration_days(text),
        }

    dominant = max(
        category_votes.keys(),
        key=lambda c: (category_priority.get(c, 0), category_votes[c])
    )

    matched_symptoms = [phrase for c, _, phrase in all_hits if c == dominant]

    return {
        "category": dominant,
        "category_matches": category_votes[dominant],
        "all_hits": all_hits,
        "matched_symptoms": matched_symptoms,
        "urgent_trigger": None,
        "temporal": extract_temporal(text),
        "intensity": extract_intensity(text),
        "duration_days": extract_duration_days(text),
    }