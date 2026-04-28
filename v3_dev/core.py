"""
ClairDiag v3 — Core Pipeline v3.1.0

Зміни v3.1.0:
  - CTRL-16: AND-trigger урінарний (medical_urgent) перед confidence
  - CTRL-17: mollet+gonflement через general_orientation_router
  - multi-layer output: структурований JSON з окремими шарами
  - category priority engine: при рівних votes → priority вирішує
  - cat=None → завжди general_vague (ніколи не None)
  - free_text передається в router для AND-trigger токен-пошуку
"""

import os
import sys
from typing import Dict, Optional

_V2_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "v2_dev")
if _V2_DIR not in sys.path:
    sys.path.insert(0, _V2_DIR)

from common_symptom_mapper import common_symptom_mapper, normalize_text
from medical_normalizer_v3 import normalize_to_medical_tokens
from clinical_combinations_engine import match_combination
from general_orientation_router import general_orientation_router
from v3_confidence_engine import compute_v3_confidence
from loader import URGENT_MESSAGE, COMMON_SYMPTOM_MAPPING

_DANGEROUS_ORIENTATIONS = {
    "urgent_emergency_workup",
    "urgent_medical_review_with_tests",
}

_DISCLAIMER = (
    "ClairDiag v3 — outil d'aide à la décision uniquement. "
    "Ne remplace pas l'avis d'un professionnel de santé."
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_safety_floor_triggered(v2_output: Dict) -> bool:
    sf = v2_output.get("safety_floor", {})
    if isinstance(sf, dict):
        return sf.get("triggered", False)
    return False


def _is_dangerous_v2(v2_output: Dict) -> bool:
    return v2_output.get("medical_orientation_v2", "") in _DANGEROUS_ORIENTATIONS


def _get_category_priority(category: str) -> int:
    for mapping in COMMON_SYMPTOM_MAPPING:
        if mapping["category"] == category:
            return mapping["priority"]
    return 0


def _run_v2(free_text: str, patient_context: Optional[Dict] = None) -> Dict:
    try:
        from simple_to_medical_mapper import map_input
        from medical_probability_engine import run_probability_engine
        from test_recommendation_engine import run_recommendation_engine

        mapping = map_input(free_text=free_text, audio_base64=None)
        symptoms = mapping.get("symptoms_normalized", [])

        if not symptoms:
            return {
                "v2_status": "low_input_quality",
                "top_hypothesis": None,
                "symptoms_normalized": [],
                "medical_orientation_v2": "insufficient_data",
                "safety_floor": {"triggered": False},
            }

        base = _V2_DIR
        v1_input = {
            "symptoms_normalized": symptoms,
            "red_flags": [],
            "final_action_v1": "consult_doctor",
        }

        etape1 = run_probability_engine(
            v1_output=v1_input,
            conditions_path=os.path.join(base, "conditions_master.json"),
            weights_path=os.path.join(base, "condition_weights.json"),
        )
        full_result = run_recommendation_engine(
            etape1_output=etape1,
            v1_output=v1_input,
            conditions_path=os.path.join(base, "conditions_master.json"),
            tests_path=os.path.join(base, "tests_master.json"),
            differential_path=os.path.join(base, "differential_rules.json"),
        )
        return full_result

    except Exception as e:
        return {
            "v2_status": "pipeline_error",
            "top_hypothesis": None,
            "medical_orientation_v2": "insufficient_data",
            "safety_floor": {"triggered": False},
            "_v2_error": str(e),
        }


# ── Multi-layer output builders ───────────────────────────────────────────────

def _build_routing_layer(reason: str, used_v2: bool, combination=None) -> Dict:
    return {
        "used_v2_core": used_v2,
        "used_general_orientation": not used_v2,
        "reason": reason,
    }


def _urgent_output(trigger: str, v2_output: Dict) -> Dict:
    return {
        # Layer 1: triage
        "triage": {
            "urgency": "urgent",
            "urgent_message": URGENT_MESSAGE,
            "and_trigger": None,
        },
        # Layer 2: clinical (порожній при urgent)
        "clinical": {
            "category": None,
            "general_orientation": None,
            "clinical_reasoning": None,
            "matched_symptoms": [],
            "and_trigger_result": None,
        },
        # Layer 3: danger
        "danger": {
            "danger_output": None,
        },
        # Layer 4: confidence
        "confidence": {
            "level": "high",
            "score": 9,
            "orientation_summary": "Signaux d'urgence détectés — évaluation médicale immédiate requise.",
        },
        # Layer 5: engine internals
        "engine": {
            "v2_output": v2_output,
            "routing_decision": _build_routing_layer("urgent_trigger_detected", True),
        },
        "disclaimer": _DISCLAIMER,
    }


def _safety_output(reason: str, v2_output: Dict) -> Dict:
    return {
        "triage": {
            "urgency": "urgent",
            "urgent_message": None,
            "and_trigger": None,
        },
        "clinical": {
            "category": None,
            "general_orientation": None,
            "clinical_reasoning": None,
            "matched_symptoms": [],
            "and_trigger_result": None,
        },
        "danger": {
            "danger_output": None,
        },
        "confidence": {
            "level": "high",
            "score": 9,
            "orientation_summary": "Signaux de gravité détectés — évaluation médicale urgente requise.",
        },
        "engine": {
            "v2_output": v2_output,
            "routing_decision": _build_routing_layer(reason, True),
        },
        "disclaimer": _DISCLAIMER,
    }


# ── Main pipeline ──────────────────────────────────────────────────────────────

def analyze_v3(
    free_text: str,
    patient_context: Optional[Dict] = None,
) -> Dict:

    # Step 1: mapper (urgent check + AND-triggers + symptom matching)
    mapped = common_symptom_mapper(free_text)

    # Step 2: urgent → завершити
    if mapped.get("urgent_trigger"):
        v2_output = _run_v2(free_text, patient_context)
        return _urgent_output(mapped["urgent_trigger"], v2_output)

    # Step 3: CTRL-16 AND-trigger → medical_urgent
    ctrl16 = mapped.get("and_trigger")
    if ctrl16 and ctrl16.get("urgency") == "medical_urgent":
        v2_output = _run_v2(free_text, patient_context)
        return {
            "triage": {
                "urgency": "medical_urgent",
                "urgent_message": ctrl16["message"],
                "and_trigger": ctrl16,
            },
            "clinical": {
                "category": ctrl16.get("category"),
                "general_orientation": None,
                "clinical_reasoning": None,
                "matched_symptoms": mapped.get("matched_symptoms", []),
                "and_trigger_result": ctrl16,
            },
            "danger": {"danger_output": None},
            "confidence": {
                "level": "high",
                "score": 8,
                "orientation_summary": ctrl16["message"],
            },
            "engine": {
                "v2_output": v2_output,
                "routing_decision": _build_routing_layer("and_trigger_ctrl16", False),
            },
            "disclaimer": _DISCLAIMER,
        }

    # Step 4: v2
    v2_output = _run_v2(free_text, patient_context)

    # Step 5: safety floor
    if _is_safety_floor_triggered(v2_output):
        return _safety_output("safety_floor_triggered", v2_output)

    # Step 6: dangerous v2 orientation
    if _is_dangerous_v2(v2_output):
        return _safety_output("dangerous_v2_orientation", v2_output)

    # Step 7: tokens + combinations
    norm = normalize_to_medical_tokens(free_text)
    temporal = mapped.get("temporal", "unknown")
    intensity = mapped.get("intensity", "normal")
    combination = match_combination(norm["tokens"], temporal)

    # Step 8: orientation (включає CTRL-17)
    router_result = general_orientation_router(
        mapped=mapped,
        temporal=temporal,
        intensity=intensity,
        combination_rule=combination,
        free_text=normalize_text(free_text),  # нормалізований текст для AND-triggers
    )

    matched_symptoms = router_result.get("matched_symptoms", [])
    category = mapped.get("category") or "general_vague"
    category_priority = _get_category_priority(category)

    # Step 9: confidence
    confidence = compute_v3_confidence(
        category=category,
        category_matches=mapped.get("category_matches", 0),
        all_hits=mapped.get("all_hits", []),
        combination_matched=combination is not None,
        temporal=temporal,
        patient_context=patient_context,
        urgent_trigger=None,
        matched_symptoms=matched_symptoms,
        category_priority=category_priority,
        and_trigger=router_result.get("and_trigger_result"),
    )

    # Step 10: urgency з CTRL-17 override
    orientation = router_result.get("general_orientation", {})
    final_urgency = orientation.get("urgency", "non_urgent") if orientation else "non_urgent"

    return {
        # Layer 1: triage
        "triage": {
            "urgency": final_urgency,
            "urgent_message": None,
            "and_trigger": router_result.get("and_trigger_result"),
        },
        # Layer 2: clinical
        "clinical": {
            "category": category,
            "general_orientation": router_result["general_orientation"],
            "clinical_reasoning": router_result["clinical_reasoning"],
            "matched_symptoms": matched_symptoms,
            "and_trigger_result": router_result.get("and_trigger_result"),
        },
        # Layer 3: danger
        "danger": {
            "danger_output": router_result["danger_output"],
        },
        # Layer 4: confidence
        "confidence": confidence,
        # Layer 5: engine internals
        "engine": {
            "v2_output": v2_output,
            "routing_decision": {
                "used_v2_core": False,
                "used_general_orientation": True,
                "reason": (
                    f"combination_rule:{combination['matched_rule']}"
                    if combination
                    else "common_symptom_mapping"
                ),
            },
        },
        "disclaimer": _DISCLAIMER,
    }