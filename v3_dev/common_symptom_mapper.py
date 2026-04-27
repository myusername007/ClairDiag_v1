"""
ClairDiag v3 — Common Symptom Mapper

Rule-based маппінг вільного тексту пацієнта → категорія + medical tokens.
Логіка:
  1. normalize text
  2. check urgent triggers (ПЕРШИЙ — завжди)
  3. match phrases → categories + tokens
  4. vote by priority + count → dominant category
  5. extract temporal / intensity / negation context

Зміни v3.0.2:
  - all_hits тепер зберігає (category, priority, matched_phrase)
  - matched_symptoms повертається окремо — список реальних виразів пацієнта
"""

import re
from typing import Dict, List, Tuple, Optional
from loader import (
    COMMON_SYMPTOM_MAPPING,
    URGENT_TRIGGERS,
    URGENT_MESSAGE,
)

# ──────────────────────────────────────────────
# NORMALIZATION
# ──────────────────────────────────────────────

def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = re.sub(r"[^\w\sàâäéèêëîïôöùûüç\-']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ──────────────────────────────────────────────
# NEGATION DETECTION
# ──────────────────────────────────────────────

_NEGATION_PREFIXES = ["pas de", "pas", "aucun", "aucune", "jamais", "sans"]


def _is_negated(text: str, phrase: str) -> bool:
    idx = text.find(phrase)
    if idx == -1:
        return False
    window = text[max(0, idx - 25):idx]
    return any(neg in window for neg in _NEGATION_PREFIXES)


# ──────────────────────────────────────────────
# TEMPORAL
# ──────────────────────────────────────────────

_TEMPORAL_MAP = {
    "brutal": "acute",
    "d'un coup": "acute",
    "soudain": "acute",
    "depuis aujourd'hui": "acute",
    "depuis hier": "acute",
    "depuis 2 jours": "subacute",
    "depuis quelques jours": "subacute",
    "depuis 2 semaines": "chronic",
    "depuis 1 mois": "chronic",
    "depuis plusieurs mois": "chronic",
    "depuis longtemps": "chronic",
    "depuis 2 mois": "chronic",
    "depuis des mois": "chronic",
    "depuis 10 jours": "subacute",
    "depuis 3 semaines": "chronic",
    "depuis plusieurs semaines": "chronic",
    "depuis quelques semaines": "chronic",
}

# Парсинг числових значень тривалості → дні
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
    """Витягує тривалість у днях з тексту для логіки danger exposure."""
    import re as _re
    for pattern, multiplier in _DURATION_PATTERNS:
        m = _re.search(pattern, text)
        if m:
            return int(m.group(1)) * multiplier
    # Словникові паттерни
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


# ──────────────────────────────────────────────
# INTENSITY
# ──────────────────────────────────────────────

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


# ──────────────────────────────────────────────
# URGENT CHECK
# ──────────────────────────────────────────────

def check_urgent_triggers(text: str) -> Optional[str]:
    """Повертає matched trigger або None. ЗАВЖДИ викликати першим."""
    for expr in URGENT_TRIGGERS:
        if expr in text:
            return expr
    return None


# ──────────────────────────────────────────────
# CATEGORY MAPPING
# ──────────────────────────────────────────────

def common_symptom_mapper(free_text: str) -> Dict:
    """
    Повертає:
      {
        "category": str | None,
        "category_matches": int,
        "all_hits": [(category, priority, matched_phrase)],
        "matched_symptoms": [str],   # реальні вирази пацієнта для домінантної категорії
        "urgent_trigger": str | None,
        "temporal": str,
        "intensity": str,
        "duration_days": int | None,
      }
    """
    text = normalize_text(free_text)

    # 1. urgent check
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

    # 2. phrase matching
    category_votes: Dict[str, int] = {}
    category_priority: Dict[str, int] = {}
    # all_hits: (category, priority, matched_phrase)
    all_hits: List[Tuple[str, int, str]] = []

    for mapping in COMMON_SYMPTOM_MAPPING:
        cat = mapping["category"]
        priority = mapping["priority"]
        for phrase in mapping["patient_expressions"]:
            if phrase in text and not _is_negated(text, phrase):
                category_votes[cat] = category_votes.get(cat, 0) + 1
                if priority > category_priority.get(cat, 0):
                    category_priority[cat] = priority
                all_hits.append((cat, priority, phrase))
                break  # один матч на mapping entry достатньо

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

    # 3. домінантна категорія
    dominant = max(
        category_votes.keys(),
        key=lambda c: (category_priority.get(c, 0), category_votes[c])
    )

    # 4. matched_symptoms — реальні фрази для домінантної категорії
    matched_symptoms = [
        phrase for cat, _, phrase in all_hits
        if cat == dominant
    ]

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