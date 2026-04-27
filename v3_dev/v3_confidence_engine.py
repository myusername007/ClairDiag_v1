"""
ClairDiag v3 — Confidence Engine
Розраховує рівень впевненості орієнтації v3.

Score 0-10:
  +2  category detected
  +2  ≥2 matched symptoms
  +2  clinical combination matched
  +1  duration provided (temporal != unknown)
  +1  patient_context provided
  -2  only vague symptoms (general_vague)
  -3  red flag present but handled by fallback only
  -2  conflicting categories (>2 different categories in hits)

Levels:
  0-3  → low
  4-6  → medium
  7-10 → high
"""

from typing import Dict, List, Optional


def compute_v3_confidence(
    category: Optional[str],
    category_matches: int,
    all_hits: List,
    combination_matched: bool,
    temporal: str,
    patient_context: Optional[Dict],
    urgent_trigger: Optional[str],
) -> Dict:

    score = 0
    reasons = []

    if urgent_trigger:
        return {
            "level": "high",
            "score": 10,
            "reasons": ["urgent trigger detected — v2 priority"],
        }

    if category:
        score += 2
        reasons.append(f"category detected: {category}")
    else:
        reasons.append("no category detected")

    if category_matches >= 2:
        score += 2
        reasons.append(f"{category_matches} matching symptoms")
    elif category_matches == 1:
        score += 1
        reasons.append("1 matching symptom")

    if combination_matched:
        score += 2
        reasons.append("clinical combination rule matched")

    if temporal != "unknown":
        score += 1
        reasons.append(f"duration context: {temporal}")

    if patient_context and any(
        patient_context.get(k) for k in ("age", "sex", "duration_days")
    ):
        score += 1
        reasons.append("patient context provided")

    if category == "general_vague":
        score -= 2
        reasons.append("only vague symptoms — reduced confidence")

    unique_cats = len(set(cat for cat, _ in all_hits)) if all_hits else 0
    if unique_cats > 2:
        score -= 2
        reasons.append(f"conflicting categories ({unique_cats} different)")

    score = max(0, min(10, score))

    if score <= 3:
        level = "low"
    elif score <= 6:
        level = "medium"
    else:
        level = "high"

    return {
        "level": level,
        "score": score,
        "reasons": reasons,
    }