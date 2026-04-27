"""
ClairDiag v3 — Common Symptom Mapper

Rule-based маппінг вільного тексту пацієнта → категорія + medical tokens.
Логіка:
  1. normalize text
  2. check urgent triggers (ПЕРШИЙ — завжди)
  3. match phrases → categories + tokens
  4. vote by priority + count → dominant category
  5. extract temporal / intensity / negation context
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
}


def extract_temporal(text: str) -> str:
    for phrase, value in _TEMPORAL_MAP.items():
        if phrase in text:
            return value
    return "unknown"


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
    # довгі фрази спочатку
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
        "all_hits": [(category, priority)],
        "urgent_trigger": str | None,
        "temporal": str,
        "intensity": str,
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
            "urgent_trigger": urgent,
            "urgent_message": URGENT_MESSAGE,
            "temporal": extract_temporal(text),
            "intensity": extract_intensity(text),
        }

    # 2. phrase matching
    category_votes: Dict[str, int] = {}
    category_priority: Dict[str, int] = {}
    all_hits = []

    for mapping in COMMON_SYMPTOM_MAPPING:
        cat = mapping["category"]
        priority = mapping["priority"]
        for phrase in mapping["patient_expressions"]:
            if phrase in text and not _is_negated(text, phrase):
                category_votes[cat] = category_votes.get(cat, 0) + 1
                # зберігаємо максимальний пріоритет для категорії
                if priority > category_priority.get(cat, 0):
                    category_priority[cat] = priority
                all_hits.append((cat, priority))
                break  # один матч на mapping entry достатньо

    if not category_votes:
        return {
            "category": None,
            "category_matches": 0,
            "all_hits": [],
            "urgent_trigger": None,
            "temporal": extract_temporal(text),
            "intensity": extract_intensity(text),
        }

    # 3. домінантна категорія: спочатку по пріоритету, потім по кількості
    dominant = max(
        category_votes.keys(),
        key=lambda c: (category_priority.get(c, 0), category_votes[c])
    )

    return {
        "category": dominant,
        "category_matches": category_votes[dominant],
        "all_hits": all_hits,
        "urgent_trigger": None,
        "temporal": extract_temporal(text),
        "intensity": extract_intensity(text),
    }