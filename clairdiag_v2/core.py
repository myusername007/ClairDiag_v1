"""
ClairDiag v3 — Core Pipeline v3.2.0 / v2.0

Зміни v2.0:
  - Layer 8: red_flags_v2 — RedFlagsEngine із red_flags.json (35 flags, additif)
  - Layer 9: specialist_v2 — SpecialistResolver із specialist_mapping.json (additif)
  - Layer 10: analysis_v2 — AnalysisInterpreter, якщо patient_context["lab_results"] (additif)
  Всі нові layers additif: try/except, ніколи не блокують pipeline.

Зміни v1.1.0 / v3.1.0 / v3.2.0: збережені без змін.
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
from pattern_engine_v3 import run_pattern_engine
from economy_calculator import get_economy_config, estimate_economic_value as _calc_economic_value
from feature_extractor import extract_features
from pattern_evaluator import AbstractPatternsConfig, hybrid_pre_triage

_abstract_config = AbstractPatternsConfig()

_DANGEROUS_ORIENTATIONS = {
    "urgent_emergency_workup",
    "urgent_medical_review_with_tests",
}

_DISCLAIMER = (
    "ClairDiag v3 — outil d'aide à la décision uniquement. "
    "Ne remplace pas l'avis d'un professionnel de santé."
)

_URGENCY_ORDER = ["urgent", "urgent_medical_review", "medical_urgent", "medical_consultation", "non_urgent"]


def _urgency_rank(u: str) -> int:
    try:
        return _URGENCY_ORDER.index(u)
    except ValueError:
        return len(_URGENCY_ORDER)


def _max_urgency(a: str, b: str) -> str:
    return a if _urgency_rank(a) <= _urgency_rank(b) else b


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
        "triage": {
            "urgency": "urgent",
            "urgent_message": URGENT_MESSAGE,
            "and_trigger": None,
        },
        "clinical": {
            "category": None,
            "general_orientation": None,
            "clinical_reasoning": None,
            "matched_symptoms": [],
            "and_trigger_result": None,
        },
        "danger": {"danger_output": None},
        "confidence": {
            "level": "high",
            "score": 9,
            "orientation_summary": "Signaux d'urgence détectés — évaluation médicale immédiate requise.",
        },
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
        "danger": {"danger_output": None},
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


# ── v2 additif layers ─────────────────────────────────────────────────────────

_CAT_MAP = {
    "orl_simple": "ORL",
    "dermatologie_simple": "dermatologie",
    "digestif_simple": "digestif",
    "gynecologique_simple": "gynecologique",
    "metabolique_hormonal_suspect": "metabolique_endocrino",
    "sommeil_stress_anxiete_non_urgent": "psychiatrie",
    "sommeil_stress_anxiete": "psychiatrie",
    "musculo_squelettique": "musculo",
    "fatigue_asthenie": "fatigue",
    "urinaire": "urinaire",
    "general_vague": "douleur_generale_vague",
    "general_vague_non_specifique": "douleur_generale_vague",
}

_URG_MAP = {
    "urgent": "urgent",
    "medical_urgent": "urgent",
    "urgent_medical_review": "urgent_medical_review",
    "medical_consultation": "medical_consultation",
    "non_urgent": "non_urgent",
}


def _enrich_red_flags_v2(response: Dict, free_text: str, patient_context: Optional[Dict]) -> Dict:
    """Layer 8 — RedFlagsEngine v2 (35 flags, red_flags.json)."""
    import logging
    log = logging.getLogger(__name__)
    try:
        from loader import get_v2_rules_loader
        from red_flags_engine import RedFlagsEngine
        from body_system_detector import BodySystemDetector

        loader = get_v2_rules_loader()
        if not loader:
            return response

        symptoms_rules = loader.get("symptoms_rules")
        if not symptoms_rules:
            return response

        detector = BodySystemDetector(symptoms_rules)
        detection = detector.detect(free_text, patient_context or {})
        detected_ids = [m["symptom_id"] for m in detection["matched_symptoms"]]

        ctx = patient_context or {}
        patient_data = {
            "symptoms": detected_ids,
            "demographics": {
                "age": ctx.get("age"),
                "sex": ctx.get("sex"),
                "pregnancy_status": ctx.get("pregnancy_status"),
                "pregnancy_trimester": ctx.get("pregnancy_trimester"),
            },
            "risk_factors": ctx.get("risk_factors", []),
            "context_flags": ctx.get("context_flags", []),
            "temporal": {"onset_speed": ctx.get("onset_speed")},
        }

        rf_rules = loader.get_rules("red_flags", "red_flags")
        rf_result = RedFlagsEngine(rf_rules).evaluate(patient_data)

        response["red_flags_v2"] = {
            "triggered": rf_result["triggered"],
            "override_triggered": rf_result.get("override_triggered", False),
            "flags": rf_result["triggered_flags"],
            "highest_urgency": rf_result["highest_urgency"],
            "body_systems_flagged": rf_result["body_systems_flagged"],
            "detected_symptoms": detected_ids,
            "body_system": detection["dominant_system"],
            "body_zone": detection["body_zone"],
        }

        if not rf_result["triggered"]:
            return response

        # Override absolu (suicide)
        if rf_result.get("override_triggered"):
            response["triage"]["urgency"] = "urgent"
            response["triage"]["urgent_message"] = (
                "Si vous pensez à vous faire du mal: appelez le 3114 immédiatement "
                "(gratuit, anonyme, 24h/24)."
            )
            return response

        # Escalade urgency (jamais downgrade)
        current = response.get("triage", {}).get("urgency", "non_urgent")
        new_urgency = _max_urgency(rf_result["highest_urgency"], current)
        if new_urgency != current:
            response["triage"]["urgency"] = new_urgency
            response["triage"]["urgency_escalated_by"] = "red_flags_v2"

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"red_flags_v2 error (non-blocking): {e!r}")

    return response


def _enrich_specialist_v2(response: Dict, patient_context: Optional[Dict]) -> Dict:
    """Layer 9 — SpecialistResolver v2 (40 routing rules, specialist_mapping.json)."""
    try:
        from loader import get_v2_rules_loader
        from specialist_resolver import SpecialistResolver

        loader = get_v2_rules_loader()
        if not loader:
            return response

        sm = loader.get("specialist_mapping")
        if not sm:
            return response

        category = (
            response.get("clinical", {}).get("category")
            or response.get("care_pathway", {}).get("matched_category")
            or "douleur_generale_vague"
        )
        urgency = response.get("triage", {}).get("urgency", "medical_consultation")
        body_zone = response.get("red_flags_v2", {}).get("body_zone")

        mapped_cat = _CAT_MAP.get(category, category)
        mapped_urg = _URG_MAP.get(urgency, "medical_consultation")

        ctx = patient_context or {}
        specialist = SpecialistResolver(sm).resolve(
            pathway_category=mapped_cat,
            urgency=mapped_urg,
            body_zone=body_zone,
            demographics={"sex": ctx.get("sex"), "age": ctx.get("age")},
        )

        response["specialist_v2"] = {
            "primary": specialist["primary"],
            "alternatives": specialist.get("alternatives", []),
            "fallback": specialist.get("fallback", []),
            "matched_rule": specialist.get("matched_rule"),
            "rationale": specialist.get("rationale"),
            "is_mt_legitimate": specialist.get("is_mt_legitimate", False),
            "specialist_info": specialist.get("specialist_info", {}),
        }

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"specialist_v2 error (non-blocking): {e!r}")

    return response


def _enrich_analysis_v2(response: Dict, patient_context: Optional[Dict]) -> Dict:
    """Layer 10 — AnalysisInterpreter v2 (analysis_rules.json). Активується якщо lab_results є."""
    try:
        ctx = patient_context or {}
        lab_results = ctx.get("lab_results", [])
        if not lab_results:
            return response

        from loader import get_v2_rules_loader
        from analysis_interpreter import AnalysisInterpreter, LabResult

        loader = get_v2_rules_loader()
        if not loader:
            return response

        ar = loader.get("analysis_rules")
        if not ar:
            return response

        interpreter = AnalysisInterpreter(ar)
        lab_objs = [
            LabResult(
                analysis_id=lr["analysis_id"],
                fields=lr.get("fields", {}),
                source=lr.get("source", "patient_uploaded"),
            )
            for lr in lab_results
        ]
        result = interpreter.apply(lab_objs)

        response["analysis_v2"] = {
            "modifiers_applied": [m.modifier_id for m in result.applied_modifiers],
            "urgency_override": result.urgency_override,
            "specialist_override": result.specialist_override,
            "additional_exams": result.additional_exams,
            "audit_trail": result.audit_trail,
        }

        # Urgency escalation depuis modifiers
        if result.urgency_override:
            current = response.get("triage", {}).get("urgency", "non_urgent")
            new_urg = _max_urgency(result.urgency_override, current)
            if new_urg != current:
                response["triage"]["urgency"] = new_urg
                response["triage"]["urgency_source"] = "analysis_modifier_v2"

        # Specialist override depuis modifiers
        if result.specialist_override and "specialist_v2" in response:
            response["specialist_v2"]["primary"] = result.specialist_override
            response["specialist_v2"]["override_by_analysis"] = True

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"analysis_v2 error (non-blocking): {e!r}")

    return response


# ── Main pipeline ──────────────────────────────────────────────────────────────

def analyze_v3(
    free_text: str,
    patient_context: Optional[Dict] = None,
) -> Dict:

    # Step 1: mapper
    mapped = common_symptom_mapper(free_text)
    norm_text = normalize_text(free_text)

    # Step 1b: feature extraction
    norm_tokens = normalize_to_medical_tokens(free_text)
    features = extract_features(
        free_text=free_text,
        norm_text=norm_text,
        mapped=mapped,
        norm_tokens=norm_tokens,
        patient_context=patient_context,
    )

    # Step 1c: hybrid pre-triage
    def _token_layer(feats: dict) -> dict:
        result = run_pattern_engine(norm_text, patient_context)
        if result:
            return {
                "matched_patterns": [result.get("pattern_id", "PE-unknown")],
                "triage_level": result.get("urgency"),
                "message": result.get("message"),
                "pattern_name": result.get("pattern_name"),
            }
        return {"matched_patterns": [], "triage_level": None}

    hybrid_result = hybrid_pre_triage(_abstract_config, features, _token_layer)

    if hybrid_result["triage_level"] in ("urgent", "medical_urgent"):
        v2_output = _run_v2(free_text, patient_context)
        hints = hybrid_result.get("patient_explanation_hints", [])
        pattern_ids = ",".join(hybrid_result["matched_patterns"]) or "hybrid_pretriage"
        out = _urgent_output(pattern_ids, v2_output)
        out["triage"]["urgent_message"] = hints[0] if hints else URGENT_MESSAGE
        out["triage"]["pattern_triggered"] = True
        out["triage"]["pattern_id"] = pattern_ids
        out["triage"]["primary_layer_used"] = hybrid_result["primary_layer_used"]
        out["triage"]["fallback_would_have_matched"] = hybrid_result.get("fallback_would_have_matched", [])
        if hybrid_result.get("override_all"):
            out["triage"]["override_all"] = True
        return out

    elif hybrid_result["triage_level"] == "urgent_medical_review":
        v2_output = _run_v2(free_text, patient_context)
        hints = hybrid_result.get("patient_explanation_hints", [])
        pattern_ids = ",".join(hybrid_result["matched_patterns"])
        return {
            "triage": {
                "urgency": "urgent_medical_review",
                "urgent_message": hints[0] if hints else None,
                "and_trigger": None,
                "pattern_triggered": True,
                "pattern_id": pattern_ids,
                "primary_layer_used": hybrid_result["primary_layer_used"],
                "fallback_would_have_matched": hybrid_result.get("fallback_would_have_matched", []),
            },
            "clinical": {
                "category": None,
                "general_orientation": None,
                "clinical_reasoning": None,
                "matched_symptoms": mapped.get("matched_symptoms", []),
                "and_trigger_result": None,
            },
            "danger": {"danger_output": None},
            "confidence": {
                "level": "high",
                "score": 8,
                "orientation_summary": hints[0] if hints else "",
            },
            "engine": {
                "v2_output": v2_output,
                "routing_decision": _build_routing_layer("hybrid_pretriage_urgent_medical_review", True),
                "hybrid_pretriage": hybrid_result,
            },
            "disclaimer": _DISCLAIMER,
        }

    # Step 2: urgent
    if mapped.get("urgent_trigger"):
        v2_output = _run_v2(free_text, patient_context)
        return _urgent_output(mapped["urgent_trigger"], v2_output)

    # Step 3: CTRL-16
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

    # Step 6: dangerous v2
    if _is_dangerous_v2(v2_output):
        return _safety_output("dangerous_v2_orientation", v2_output)

    # Step 7: tokens + combinations
    norm = norm_tokens
    temporal = mapped.get("temporal", "unknown")
    intensity = mapped.get("intensity", "normal")
    combination = match_combination(norm["tokens"], temporal)

    # Step 8: orientation
    router_result = general_orientation_router(
        mapped=mapped,
        temporal=temporal,
        intensity=intensity,
        combination_rule=combination,
        free_text=norm_text,
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

    # Step 10: urgency
    orientation = router_result.get("general_orientation", {})
    final_urgency = orientation.get("urgency", "non_urgent") if orientation else "non_urgent"

    final_response = {
        "triage": {
            "urgency": final_urgency,
            "urgent_message": None,
            "and_trigger": router_result.get("and_trigger_result"),
        },
        "clinical": {
            "category": category,
            "general_orientation": router_result["general_orientation"],
            "clinical_reasoning": router_result["clinical_reasoning"],
            "matched_symptoms": matched_symptoms,
            "and_trigger_result": router_result.get("and_trigger_result"),
        },
        "danger": {
            "danger_output": router_result["danger_output"],
        },
        "confidence": confidence,
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

    # Layer 6: economic value
    try:
        econ_cfg = get_economy_config()
        if econ_cfg:
            economic_value = _calc_economic_value(econ_cfg, final_response)
            if economic_value:
                final_response["economic_value"] = economic_value
    except Exception:
        pass

    # Layer 7a: local directory
    try:
        from local_directory_engine import LocalDirectoryConfig, enrich_with_pilot_mode
        _dir_config = LocalDirectoryConfig()
        local = enrich_with_pilot_mode(_dir_config, final_response, patient_context or {}, region="PACA")
        final_response["local_orientation"] = local
    except Exception:
        pass

    # Layer 7b: care pathway v1
    try:
        from care_pathway_engine import enrich as _enrich_care_pathway
        final_response = _enrich_care_pathway(
            final_response,
            free_text=free_text,
            patient_context=patient_context,
        )
    except Exception:
        pass

    # Layer 8: red flags v2 (35 flags, JSON-driven)
    try:
        final_response = _enrich_red_flags_v2(final_response, free_text, patient_context)
    except Exception:
        pass

    # Layer 9: specialist v2 (40 routing rules, JSON-driven)
    try:
        final_response = _enrich_specialist_v2(final_response, patient_context)
    except Exception:
        pass

    # Layer 10: analysis v2 (lab_results → modifiers, JSON-driven)
    try:
        final_response = _enrich_analysis_v2(final_response, patient_context)
    except Exception:
        pass

    return final_response