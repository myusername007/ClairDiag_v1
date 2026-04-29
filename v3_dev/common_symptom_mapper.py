"""
ClairDiag v3 — Common Symptom Mapper v3.2.0

Зміни v3.2.0:
  - check_all_urgent_and_triggers замість тільки CTRL-16
  - CTRL-16/18/19/20/21 всі перевіряються
  - AND-trigger з urgency=urgent виноситься перед основний urgent check
"""

import re
from typing import Dict, List, Tuple, Optional
from loader import (
    COMMON_SYMPTOM_MAPPING,
    URGENT_TRIGGERS,
    URGENT_MESSAGE,
)
from fuzzy_utils import fuzzy_match_phrase, fuzzy_check_urgent_triggers
from and_triggers import check_all_urgent_and_triggers, check_urinary_fever_back


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


# ── Negation ──────────────────────────────────────────────────────────────────
# Вікно збільшено до 30 символів, додані нові префікси
_NEGATION_PREFIXES = [
    "pas de", "pas d'", "pas du", "pas",
    "aucun", "aucune", "jamais", "sans",
    "ni ", "plus de", "plus d'",
    "ne … pas", "n'ai pas", "n'a pas",
]


def _is_negated(text: str, phrase: str) -> bool:
    idx = text.find(phrase)
    if idx == -1:
        return False
    window = text[max(0, idx - 30):idx]
    return any(neg in window for neg in _NEGATION_PREFIXES)


# ── Temporal / Duration / Intensity ───────────────────────────────────────────

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


# ── Main mapper ────────────────────────────────────────────────────────────────

def check_urgent_triggers(text: str) -> Optional[str]:
    """Urgent check з fuzzy matching."""
    return fuzzy_check_urgent_triggers(URGENT_TRIGGERS, text)


def common_symptom_mapper(free_text: str) -> Dict:
    text = normalize_text(free_text)

    # Urgent → короткий circuit
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
            "and_trigger": None,
        }

    # AND-triggers: CTRL-16/18/19/20/21
    ctrl16 = check_all_urgent_and_triggers(text)

    category_votes: Dict[str, int] = {}
    category_priority: Dict[str, int] = {}
    all_hits: List[Tuple[str, int, str]] = []

    for mapping in COMMON_SYMPTOM_MAPPING:
        cat = mapping["category"]
        priority = mapping["priority"]
        for phrase in mapping["patient_expressions"]:
            norm_phrase = normalize_phrase(phrase)
            # fuzzy match замість тільки точного
            if fuzzy_match_phrase(norm_phrase, text) and not _is_negated(text, norm_phrase):
                category_votes[cat] = category_votes.get(cat, 0) + 1
                if priority > category_priority.get(cat, 0):
                    category_priority[cat] = priority
                all_hits.append((cat, priority, phrase))

    # cat=None fallback → general_vague
    if not category_votes:
        return {
            "category": "general_vague",
            "category_matches": 0,
            "all_hits": [],
            "matched_symptoms": [],
            "urgent_trigger": None,
            "temporal": extract_temporal(text),
            "intensity": extract_intensity(text),
            "duration_days": extract_duration_days(text),
            "and_trigger": ctrl16,
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
        "and_trigger": ctrl16,
    }