"""
ClairDiag v3 — General Orientation Router
Будує фінальний general_orientation з:
  - common_conditions_config (базова орієнтація)
  - danger_exclusion_rules (що виключати)
  - clinical reasoning (чому саме ця орієнтація)
  - fallback для general_vague
"""

from typing import Dict, Optional, List
from loader import COMMON_CONDITIONS_CONFIG, DANGER_EXCLUSION_RULES


def build_orientation(
    category: str,
    reason: str,
    temporal: str = "unknown",
    intensity: str = "normal",
) -> Optional[Dict]:
    cfg = COMMON_CONDITIONS_CONFIG.get(category)
    if not cfg:
        return None
    return {
        "category": category,
        "recommended_action": cfg["recommended_action"],
        "possible_specialist": cfg["possible_specialist"],
        "urgency": cfg["urgency"],
        "reason": reason,
        "red_flags_to_watch": cfg["red_flags_to_watch"],
        "suggested_basic_tests": cfg["suggested_basic_tests"],
        "patient_explanation": cfg["patient_explanation"],
        "limitations": cfg["limitations"],
    }


def build_danger_exclusion(category: str) -> Dict:
    rules = DANGER_EXCLUSION_RULES.get(category, {})
    return {
        "must_exclude": rules.get("must_exclude", []),
        "red_flags": rules.get("red_flags", []),
    }


def build_clinical_reasoning(
    category: str,
    matched_phrases: List[str],
    temporal: str,
    intensity: str,
    combination_rule_id: Optional[str] = None,
) -> Dict:
    cfg = COMMON_CONDITIONS_CONFIG.get(category, {})
    danger = DANGER_EXCLUSION_RULES.get(category, {})

    why = []
    if matched_phrases:
        why.append(f"symptômes identifiés: {', '.join(matched_phrases[:3])}")
    if temporal != "unknown":
        why.append(f"évolution: {temporal}")
    if intensity == "high":
        why.append("intensité élevée signalée")
    if combination_rule_id:
        why.append(f"règle clinique combinée: {combination_rule_id}")

    next_step = cfg.get("recommended_action", "consultation médecin traitant")

    return {
        "dominant_pattern": category,
        "why_this_orientation": why if why else ["symptômes compatibles avec la catégorie"],
        "danger_to_exclude": danger.get("must_exclude", []),
        "why_not_more_precise": "une consultation et/ou un bilan permettront de préciser",
        "next_best_step": next_step,
    }


def fallback_orientation() -> Dict:
    return build_orientation(
        category="general_vague",
        reason="symptômes non spécifiques — orientation générale",
    )


def general_orientation_router(
    mapped: Dict,
    temporal: str = "unknown",
    intensity: str = "normal",
    combination_rule: Optional[Dict] = None,
) -> Dict:
    """
    Повертає dict з:
      - general_orientation
      - clinical_reasoning
      - danger_exclusion
    """
    # combination rule має пріоритет над simple mapping
    if combination_rule:
        cat = combination_rule["orientation"]["category"]
        reason = combination_rule["orientation"]["reason"]
        rule_id = combination_rule.get("matched_rule")
    elif mapped.get("category"):
        cat = mapped["category"]
        reason = f"symptômes compatibles avec la catégorie {cat}"
        rule_id = None
    else:
        cat = "general_vague"
        reason = "symptômes non spécifiques"
        rule_id = None

    orientation = build_orientation(cat, reason, temporal, intensity)
    if not orientation:
        orientation = fallback_orientation()
        cat = "general_vague"
        rule_id = None

    # Збираємо matched phrases з all_hits для clinical reasoning
    matched_phrases = []
    for hit_cat, _ in mapped.get("all_hits", []):
        if hit_cat == cat and len(matched_phrases) < 3:
            # Знаходимо оригінальний вираз пацієнта для цієї категорії
            matched_phrases.append(hit_cat.replace("_", " "))

    clinical_reasoning = build_clinical_reasoning(
        category=cat,
        matched_phrases=matched_phrases,
        temporal=temporal,
        intensity=intensity,
        combination_rule_id=rule_id,
    )
    danger_exclusion = build_danger_exclusion(cat)

    return {
        "general_orientation": orientation,
        "clinical_reasoning": clinical_reasoning,
        "danger_exclusion": danger_exclusion,
    }