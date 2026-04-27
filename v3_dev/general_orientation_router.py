"""
ClairDiag v3 — General Orientation Router v3.0.2

Зміни v3.0.2:
  - Таск 1: danger_to_exclude → _internal за замовчуванням
             показується тільки при умовах §8.2
             reformulation patient-friendly через danger_reformulation_v1.json
  - Таск 3: clinical_reasoning без технічних reasons
  - Таск 4: matched_symptoms передається і відображається
"""

from typing import Dict, Optional, List
from loader import (
    COMMON_CONDITIONS_CONFIG,
    DANGER_EXCLUSION_RULES,
    DANGER_REFORMULATION,
    DANGER_EXPOSURE_THRESHOLDS,
)


# ──────────────────────────────────────────────
# DANGER EXPOSURE LOGIC (Таск 1)
# ──────────────────────────────────────────────

def should_expose_danger(
    category: str,
    urgency: str,
    duration_days: Optional[int],
    has_group_red_flag: bool,
) -> bool:
    """
    §8.2: expose danger_to_exclude тільки при:
      (a) red flag групи присутній
      (b) тривалість > порогу категорії
      (c) urgency вже medical_consultation або urgent
    """
    # (a)
    if has_group_red_flag:
        return True
    # (c)
    if urgency in ("medical_consultation", "urgent"):
        return True
    # (b)
    threshold = DANGER_EXPOSURE_THRESHOLDS.get(category)
    if threshold is None:
        return True  # None = завжди показувати
    if threshold == 0:
        return False  # 0 = тільки red flag (вже перевірено вище)
    if duration_days is not None and duration_days > threshold:
        return True
    return False


def _reformulate_dangers(must_exclude: List[str]) -> List[str]:
    """Конвертує технічні назви патологій у симптоми-сентинели для пацієнта."""
    result = []
    for item in must_exclude:
        reformulated = DANGER_REFORMULATION.get(item)
        if reformulated:
            result.append(reformulated)
        # якщо нема reformulation — НЕ показуємо технічну назву пацієнту
    return result


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


def build_danger_output(
    category: str,
    urgency: str,
    duration_days: Optional[int],
    has_group_red_flag: bool = False,
) -> Dict:
    """
    Повертає:
      - elements_to_watch: публічний список для пацієнта (reformulated)
      - _internal: технічні дані для лікаря/audit (завжди присутні)
    """
    rules = DANGER_EXCLUSION_RULES.get(category, {})
    must_exclude = rules.get("must_exclude", [])
    red_flags = rules.get("red_flags", [])

    expose = should_expose_danger(category, urgency, duration_days, has_group_red_flag)

    result = {
        "_internal": {
            "must_exclude": must_exclude,
            "red_flags": red_flags,
            "exposed_to_patient": expose,
        }
    }

    if expose and must_exclude:
        reformulated = _reformulate_dangers(must_exclude)
        if reformulated:
            result["elements_to_watch"] = reformulated
    # red_flags_to_watch вже є в general_orientation — не дублюємо

    return result


def build_clinical_reasoning(
    category: str,
    matched_symptoms: List[str],
    temporal: str,
    intensity: str,
    combination_rule_id: Optional[str] = None,
) -> Dict:
    """
    Таск 3: без технічних reasons, тільки людський текст.
    Таск 4: використовує реальні matched_symptoms.
    """
    cfg = COMMON_CONDITIONS_CONFIG.get(category, {})

    why = []
    if matched_symptoms:
        # реальні фрази пацієнта
        why.append(
            f"{', '.join(matched_symptoms[:3])}, compatible avec une plainte "
            f"{category.replace('_', ' ')} sans signe de gravité immédiate"
        )
    if temporal != "unknown":
        temporal_labels = {
            "acute": "symptômes d'apparition récente",
            "subacute": "évolution sur quelques jours",
            "chronic": "symptômes persistants depuis plusieurs semaines",
        }
        why.append(temporal_labels.get(temporal, f"évolution: {temporal}"))
    if intensity == "high":
        why.append("intensité élevée signalée — surveillance recommandée")
    if combination_rule_id:
        why.append(f"association de symptômes typique (règle {combination_rule_id})")

    next_step = cfg.get("recommended_action", "consultation médecin traitant")

    return {
        "dominant_pattern": category,
        "why_this_orientation": why if why else [
            f"symptômes compatibles avec la catégorie {category.replace('_', ' ')}"
        ],
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
      - danger_output (замість danger_exclusion)
      - matched_symptoms
    """
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

    urgency = orientation.get("urgency", "non_urgent")
    duration_days = mapped.get("duration_days")

    # Таск 4: реальні matched_symptoms
    matched_symptoms = mapped.get("matched_symptoms", [])
    # Якщо matched_symptoms порожній — fallback до all_hits
    if not matched_symptoms:
        matched_symptoms = [
            phrase for c, _, phrase in mapped.get("all_hits", [])
            if c == cat
        ][:3]

    clinical_reasoning = build_clinical_reasoning(
        category=cat,
        matched_symptoms=matched_symptoms,
        temporal=temporal,
        intensity=intensity,
        combination_rule_id=rule_id,
    )

    # Таск 1: danger з логікою exposure
    danger_output = build_danger_output(
        category=cat,
        urgency=urgency,
        duration_days=duration_days,
    )

    return {
        "general_orientation": orientation,
        "clinical_reasoning": clinical_reasoning,
        "danger_output": danger_output,
        "matched_symptoms": matched_symptoms,
    }