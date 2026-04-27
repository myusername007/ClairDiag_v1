"""
ClairDiag v3 — Core Pipeline

analyze_v3(free_text, patient_context) → dict

Priority order (HARD RULES):
  1. urgent_triggers → urgent output, v2 wins
  2. v2 safety_floor triggered → v2 wins
  3. v2 dangerous orientation (urgent_*) → v2 wins
  4. clinical combinations → specific orientation
  5. common symptom mapping → general orientation
  6. fallback → médecin traitant
"""

import os
import sys
from typing import Dict, Optional

# ── v2 path setup ─────────────────────────────────────────────────────────────
_V2_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "v2_dev")
if _V2_DIR not in sys.path:
    sys.path.insert(0, _V2_DIR)

from common_symptom_mapper import common_symptom_mapper
from medical_normalizer_v3 import normalize_to_medical_tokens
from clinical_combinations_engine import match_combination
from general_orientation_router import general_orientation_router, fallback_orientation
from v3_confidence_engine import compute_v3_confidence
from loader import URGENT_MESSAGE

# ──────────────────────────────────────────────
# V2 INTEGRATION HELPERS (НЕ ЗМІНЮВАТИ v2)
# ──────────────────────────────────────────────

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


def _run_v2(free_text: str, patient_context: Optional[Dict] = None) -> Dict:
    """
    Запускає v2 analyze_free_text pipeline.
    Повертає v2 output dict або порожній dict при помилці.
    """
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


# ──────────────────────────────────────────────
# URGENT OUTPUT
# ──────────────────────────────────────────────

def _urgent_output(trigger: str, v2_output: Dict) -> Dict:
    from .v3_confidence_engine import compute_v3_confidence
    return {
        "v2_output": v2_output,
        "general_orientation": None,
        "clinical_reasoning": None,
        "danger_exclusion": None,
        "confidence_detail": {
            "level": "high",
            "score": 10,
            "reasons": [f"urgent trigger: {trigger}"],
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


# ──────────────────────────────────────────────
# MAIN PIPELINE
# ──────────────────────────────────────────────

def analyze_v3(
    free_text: str,
    patient_context: Optional[Dict] = None,
) -> Dict:
    """
    Головний v3 pipeline.
    v2 завжди викликається, але його output використовується лише при:
      - safety_floor triggered
      - dangerous orientation (urgent_*)
      - urgent trigger у тексті
    """

    # ── Step 1: Common symptom mapping (включає urgent check) ──────────────────
    mapped = common_symptom_mapper(free_text)

    # ── Step 2: Urgent triggers → завершити негайно ────────────────────────────
    if mapped.get("urgent_trigger"):
        v2_output = _run_v2(free_text, patient_context)
        return _urgent_output(mapped["urgent_trigger"], v2_output)

    # ── Step 3: Run v2 ─────────────────────────────────────────────────────────
    v2_output = _run_v2(free_text, patient_context)

    # ── Step 4: v2 safety floor triggered → v2 wins ───────────────────────────
    if _is_safety_floor_triggered(v2_output):
        return {
            "v2_output": v2_output,
            "general_orientation": None,
            "clinical_reasoning": None,
            "danger_exclusion": None,
            "confidence_detail": {
                "level": "high",
                "score": 9,
                "reasons": ["v2 safety floor activated"],
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

    # ── Step 5: v2 dangerous hypothesis → v2 wins ─────────────────────────────
    if _is_dangerous_v2(v2_output):
        return {
            "v2_output": v2_output,
            "general_orientation": None,
            "clinical_reasoning": None,
            "danger_exclusion": None,
            "confidence_detail": {
                "level": "high",
                "score": 9,
                "reasons": ["v2 dangerous orientation detected"],
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

    # ── Step 6: Medical tokens + clinical combinations ─────────────────────────
    norm = normalize_to_medical_tokens(free_text)
    temporal = mapped.get("temporal", "unknown")
    intensity = mapped.get("intensity", "normal")

    combination = match_combination(norm["tokens"], temporal)

    # ── Step 7: Build orientation ──────────────────────────────────────────────
    router_result = general_orientation_router(
        mapped=mapped,
        temporal=temporal,
        intensity=intensity,
        combination_rule=combination,
    )

    # ── Step 8: Confidence ─────────────────────────────────────────────────────
    confidence = compute_v3_confidence(
        category=mapped.get("category"),
        category_matches=mapped.get("category_matches", 0),
        all_hits=mapped.get("all_hits", []),
        combination_matched=combination is not None,
        temporal=temporal,
        patient_context=patient_context,
        urgent_trigger=None,
    )

    return {
        "v2_output": v2_output,
        "general_orientation": router_result["general_orientation"],
        "clinical_reasoning": router_result["clinical_reasoning"],
        "danger_exclusion": router_result["danger_exclusion"],
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