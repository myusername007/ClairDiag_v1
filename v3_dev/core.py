"""
ClairDiag v3 — Core Pipeline v3.0.2

Priority order (HARD RULES):
  1. urgent_triggers → urgent output, v2 wins
  2. v2 safety_floor triggered → v2 wins
  3. v2 dangerous orientation (urgent_*) → v2 wins
  4. clinical combinations → specific orientation
  5. common symptom mapping → general orientation
  6. fallback → médecin traitant

Зміни v3.0.2:
  - передаємо matched_symptoms і category_priority в confidence engine
  - danger_exclusion → danger_output (таск 1)
  - reasons → orientation_summary (таск 3)
  - matched_symptoms у відповіді (таск 4)
"""

import os
import sys
from typing import Dict, Optional

_V2_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "v2_dev")
if _V2_DIR not in sys.path:
    sys.path.insert(0, _V2_DIR)

from common_symptom_mapper import common_symptom_mapper
from medical_normalizer_v3 import normalize_to_medical_tokens
from clinical_combinations_engine import match_combination
from general_orientation_router import general_orientation_router
from v3_confidence_engine import compute_v3_confidence
from loader import URGENT_MESSAGE, COMMON_SYMPTOM_MAPPING

_DANGEROUS_ORIENTATIONS = {
    "urgent_emergency_workup",
    "urgent_medical_review_with_tests",
}


def _is_safety_floor_triggered(v2_output: Dict) -> bool:
    sf = v2_output.get("safety_floor", {})
    if isinstance(sf, dict):
        return sf.get("triggered", False)
    return False


def _is_dangerous_v2(v2_output: Dict) -> bool:
    return v2_output.get("medical_orientation_v2", "") in _DANGEROUS_ORIENTATIONS


def _get_category_priority(category: str) -> int:
    """Повертає priority категорії з маппінгу."""
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


def _urgent_output(trigger: str, v2_output: Dict) -> Dict:
    return {
        "v2_output": v2_output,
        "general_orientation": None,
        "clinical_reasoning": None,
        "danger_output": None,
        "matched_symptoms": [],
        "confidence_detail": {
            "level": "high",
            "score": 9,
            "orientation_summary": "Signaux d'urgence détectés — évaluation médicale immédiate requise.",
        },
        "routing_decision": {
            "used_v2_core": True,
            "used_general_orientation": False,
            "reason": "urgent_trigger_detected",
        },
        "urgent_message": URGENT_MESSAGE,
        "disclaimer": (
            "ClairDiag v3 — outil d'aide à la décision uniquement. "
            "Ne remplace pas l'avis d'un professionnel de santé."
        ),
    }


def analyze_v3(
    free_text: str,
    patient_context: Optional[Dict] = None,
) -> Dict:

    # Step 1: mapper (включає urgent check)
    mapped = common_symptom_mapper(free_text)

    # Step 2: urgent → завершити
    if mapped.get("urgent_trigger"):
        v2_output = _run_v2(free_text, patient_context)
        return _urgent_output(mapped["urgent_trigger"], v2_output)

    # Step 3: v2
    v2_output = _run_v2(free_text, patient_context)

    # Step 4: safety floor
    if _is_safety_floor_triggered(v2_output):
        return {
            "v2_output": v2_output,
            "general_orientation": None,
            "clinical_reasoning": None,
            "danger_output": None,
            "matched_symptoms": [],
            "confidence_detail": {
                "level": "high",
                "score": 9,
                "orientation_summary": "Signaux de gravité détectés — évaluation médicale urgente requise.",
            },
            "routing_decision": {
                "used_v2_core": True,
                "used_general_orientation": False,
                "reason": "safety_floor_triggered",
            },
            "disclaimer": (
                "ClairDiag v3 — outil d'aide à la décision uniquement. "
                "Ne remplace pas l'avis d'un professionnel de santé."
            ),
        }

    # Step 5: dangerous v2
    if _is_dangerous_v2(v2_output):
        return {
            "v2_output": v2_output,
            "general_orientation": None,
            "clinical_reasoning": None,
            "danger_output": None,
            "matched_symptoms": [],
            "confidence_detail": {
                "level": "high",
                "score": 9,
                "orientation_summary": "Hypothèse grave détectée par le moteur clinique — évaluation médicale requise.",
            },
            "routing_decision": {
                "used_v2_core": True,
                "used_general_orientation": False,
                "reason": "dangerous_v2_orientation",
            },
            "disclaimer": (
                "ClairDiag v3 — outil d'aide à la décision uniquement. "
                "Ne remplace pas l'avis d'un professionnel de santé."
            ),
        }

    # Step 6: tokens + combinations
    norm = normalize_to_medical_tokens(free_text)
    temporal = mapped.get("temporal", "unknown")
    intensity = mapped.get("intensity", "normal")
    combination = match_combination(norm["tokens"], temporal)

    # Step 7: orientation
    router_result = general_orientation_router(
        mapped=mapped,
        temporal=temporal,
        intensity=intensity,
        combination_rule=combination,
    )

    matched_symptoms = router_result.get("matched_symptoms", [])
    category = mapped.get("category")
    category_priority = _get_category_priority(category) if category else 0

    # Step 8: confidence (калібрований)
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
    )

    return {
        "v2_output": v2_output,
        "general_orientation": router_result["general_orientation"],
        "clinical_reasoning": router_result["clinical_reasoning"],
        "danger_output": router_result["danger_output"],
        "matched_symptoms": matched_symptoms,
        "confidence_detail": confidence,
        "routing_decision": {
            "used_v2_core": False,
            "used_general_orientation": True,
            "reason": (
                f"combination_rule:{combination['matched_rule']}"
                if combination
                else "common_symptom_mapping"
            ),
        },
        "disclaimer": (
            "ClairDiag v3 — outil d'aide à la décision uniquement. "
            "Ne remplace pas l'avis d'un professionnel de santé."
        ),
    }