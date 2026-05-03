"""
ClairDiag v3 — General Orientation Router v3.1.0

Зміни v3.1.0:
  - CTRL-17: mollet+gonflement escalation (and_triggers.check_mollet_gonflement)
  - cat=None → завжди fallback general_vague (ніколи не повертаємо None category)
  - urgency override вбудований в orientation dict
"""

from typing import Dict, Optional, List
from loader import (
    COMMON_CONDITIONS_CONFIG,
    DANGER_EXCLUSION_RULES,
    DANGER_REFORMULATION,
    DANGER_EXPOSURE_THRESHOLDS,
)
from and_triggers import check_mollet_gonflement


# ── Danger exposure logic ──────────────────────────────────────────────────────

def should_expose_danger(
    category: str,
    urgency: str,
    duration_days: Optional[int],
    has_group_red_flag: bool,
) -> bool:
    if has_group_red_flag:
        return True
    if urgency in ("medical_consultation", "urgent", "medical_urgent"):
        return True
    threshold = DANGER_EXPOSURE_THRESHOLDS.get(category)
    if threshold is None:
        return True
    if threshold == 0:
        return False
    if duration_days is not None and duration_days > threshold:
        return True
    return False


def _reformulate_dangers(must_exclude: List[str]) -> List[str]:
    result = []
    for item in must_exclude:
        reformulated = DANGER_REFORMULATION.get(item)
        if reformulated:
            result.append(reformulated)
    return result


# ── Orientation builder ────────────────────────────────────────────────────────

def build_orientation(
    category: str,
    reason: str,
    temporal: str = "unknown",
    intensity: str = "normal",
    urgency_override: Optional[str] = None,
    red_flags_override: Optional[List[str]] = None,
) -> Optional[Dict]:
    cfg = COMMON_CONDITIONS_CONFIG.get(category)
    if not cfg:
        return None

    urgency = urgency_override if urgency_override else cfg["urgency"]
    red_flags = red_flags_override if red_flags_override else cfg["red_flags_to_watch"]

    return {
        "category": category,
        "recommended_action": cfg["recommended_action"],
        "possible_specialist": cfg["possible_specialist"],
        "urgency": urgency,
        "reason": reason,
        "red_flags_to_watch": red_flags,
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

    return result


def build_clinical_reasoning(
    category: str,
    matched_symptoms: List[str],
    temporal: str,
    intensity: str,
    combination_rule_id: Optional[str] = None,
    and_trigger_reason: Optional[str] = None,
) -> Dict:
    cfg = COMMON_CONDITIONS_CONFIG.get(category, {})

    why = []
    if matched_symptoms:
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
    if and_trigger_reason:
        why.append(and_trigger_reason)

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


# ── Main router ────────────────────────────────────────────────────────────────

def general_orientation_router(
    mapped: Dict,
    temporal: str = "unknown",
    intensity: str = "normal",
    combination_rule: Optional[Dict] = None,
    free_text: str = "",
) -> Dict:
    """
    Повертає dict з:
      - general_orientation
      - clinical_reasoning
      - danger_output
      - matched_symptoms
      - and_trigger_result (якщо спрацював CTRL-17)
    """
    if combination_rule:
        cat = combination_rule["orientation"]["category"]
        reason = combination_rule["orientation"]["reason"]
        rule_id = combination_rule.get("matched_rule")
    elif mapped.get("category") and mapped["category"] != "general_vague":
        cat = mapped["category"]
        reason = f"symptômes compatibles avec la catégorie {cat}"
        rule_id = None
    else:
        cat = "general_vague"
        reason = "symptômes non spécifiques"
        rule_id = None

    # matched_symptoms
    matched_symptoms = mapped.get("matched_symptoms", [])
    if not matched_symptoms:
        matched_symptoms = [
            phrase for c, _, phrase in mapped.get("all_hits", [])
            if c == cat
        ][:3]

    # CTRL-17: mollet + gonflement escalation
    ctrl17 = check_mollet_gonflement(cat, matched_symptoms, free_text)

    urgency_override = ctrl17["urgency_override"] if ctrl17 else None
    red_flags_override = ctrl17["red_flags_to_watch"] if ctrl17 else None
    and_trigger_reason = ctrl17["reason"] if ctrl17 else None

    orientation = build_orientation(
        cat, reason, temporal, intensity,
        urgency_override=urgency_override,
        red_flags_override=red_flags_override,
    )

    # Fallback якщо category не знайдена в config
    if not orientation:
        orientation = fallback_orientation()
        cat = "general_vague"
        rule_id = None
        ctrl17 = None
        and_trigger_reason = None

    urgency = orientation.get("urgency", "non_urgent")
    duration_days = mapped.get("duration_days")

    clinical_reasoning = build_clinical_reasoning(
        category=cat,
        matched_symptoms=matched_symptoms,
        temporal=temporal,
        intensity=intensity,
        combination_rule_id=rule_id,
        and_trigger_reason=and_trigger_reason,
    )

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
        "and_trigger_result": ctrl17,
    }