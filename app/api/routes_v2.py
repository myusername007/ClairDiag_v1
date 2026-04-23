"""
ClairDiag v2 — API Router
Endpoints:
  POST /v2/analyze  — повний v2 pipeline
  POST /v2/export   — export кейсу для лікаря
  GET  /v2/health   — статус v2
"""

import logging
import os
import sys
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

# ── v2 pipeline imports ───────────────────────────────────────────────────────
_V2_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "v2_dev")
if _V2_DIR not in sys.path:
    sys.path.insert(0, _V2_DIR)

from medical_probability_engine import run_probability_engine
from test_recommendation_engine import run_recommendation_engine
from reasoning_trace_builder import build_reasoning_trace
from economic_score_v2 import compute_economic_score
from case_logger_v2 import new_session_id, log_v2_case, build_export_case
from context_flags import detect_context_flags
from simple_to_medical_mapper import map_input

router_v2 = APIRouter()
logger = logging.getLogger("clairdiag.v2")

# ── Schemas ───────────────────────────────────────────────────────────────────

class V2AnalyzeRequest(BaseModel):
    symptoms_normalized: List[str]
    red_flags: List[str] = []
    final_action_v1: str = "consult_doctor"
    context_text: Optional[str] = ""  # raw patient context for flag detection (overlay only)

    model_config = {
        "json_schema_extra": {
            "example": {
                "symptoms_normalized": ["douleur_thoracique", "sueur_froide", "nausees"],
                "red_flags": [],
                "final_action_v1": "consult_urgent",
                "context_text": "Patient sous AOD, chute recente",
            }
        }
    }


class V2ExportRequest(BaseModel):
    session_id: str
    symptoms_normalized: List[str]
    red_flags: List[str] = []
    final_action_v1: str = "consult_doctor"
    context_text: Optional[str] = ""  # raw patient context for flag detection


# ── Helpers ───────────────────────────────────────────────────────────────────

def _v2_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "v2_dev")


def _run_full_pipeline(v1_input: dict) -> tuple[dict, dict, dict]:
    """Запускає повний v2 pipeline. Повертає (etape1, full_result, v1_input)."""
    base = _v2_dir()
    etape1 = run_probability_engine(
        v1_output       = v1_input,
        conditions_path = os.path.join(base, "conditions_master.json"),
        weights_path    = os.path.join(base, "condition_weights.json"),
    )
    full_result = run_recommendation_engine(
        etape1_output     = etape1,
        v1_output         = v1_input,
        conditions_path   = os.path.join(base, "conditions_master.json"),
        tests_path        = os.path.join(base, "tests_master.json"),
        differential_path = os.path.join(base, "differential_rules.json"),
    )
    return etape1, full_result


# ── Routes ────────────────────────────────────────────────────────────────────

@router_v2.get("/health")
def v2_health():
    return {
        "status":  "ok",
        "engine":  "ClairDiag v2",
        "version": "2.0.0-dev",
    }


@router_v2.post("/analyze")
def v2_analyze(request: V2AnalyzeRequest):
    session_id = new_session_id()
    v1_input = {
        "symptoms_normalized": request.symptoms_normalized,
        "red_flags":           request.red_flags,
        "final_action_v1":     request.final_action_v1,
    }

    # ── context_flags (overlay — no engine impact) ────────────────────────────
    context_result = detect_context_flags(request.context_text)

    try:
        etape1, full_result = _run_full_pipeline(v1_input)
    except Exception as e:
        logger.error(f"v2 pipeline error: {e!r}")
        return JSONResponse(status_code=500, content={"error": "pipeline_error", "detail": str(e)})

    reasoning_trace = build_reasoning_trace(v1_input, etape1, full_result)

    economic_impact = compute_economic_score(
        recommended_tests  = full_result.get("recommended_tests", []),
        orientation        = full_result.get("medical_orientation_v2", ""),
        top_hypothesis     = full_result.get("top_hypothesis"),
        clinical_confidence= full_result.get("confidence_level", "faible"),
        clinical_group     = full_result.get("clinical_group", "general"),
    )

    test_strategy = {
        "mode":   full_result.get("next_step_logic", ""),
        "reason": reasoning_trace["test_justification"][0] if reasoning_trace["test_justification"] else "",
    }

    log_v2_case(session_id, v1_input, full_result, reasoning_trace, economic_impact,
                context_flags=context_result["context_flags"])

    # ── danger_zone ───────────────────────────────────────────────────────────
    _base = _v2_dir()
    try:
        import json as _json
        with open(os.path.join(_base, "conditions_master.json")) as _f:
            _conds = _json.load(_f)["conditions"]
    except Exception:
        _conds = {}

    _danger_levels = {"critical", "high"}
    _all_danger = list({
        *full_result.get("exclude_priority", []),
        *([full_result.get("top_hypothesis")] if full_result.get("top_hypothesis") else []),
        *full_result.get("secondary_hypotheses", []),
    })
    danger_zone = [
        {
            "condition": c,
            "danger_level": _conds.get(c, {}).get("danger_level", "unknown"),
            "label_fr":     _conds.get(c, {}).get("label_fr", c),
        }
        for c in _all_danger
        if _conds.get(c, {}).get("danger_level", "") in _danger_levels
    ]

    # ── confidence_detail ─────────────────────────────────────────────────────
    _conf = full_result.get("confidence_level", "faible")
    _sf   = full_result.get("safety_floor", {})
    _sf_on = _sf.get("triggered", False) if isinstance(_sf, dict) else False
    _conf_reasons = []
    if _sf_on:
        _conf_reasons.append("safety floor activé — confidence plancher appliqué")
    if full_result.get("v2_status") == "tied_scores":
        _conf_reasons.append("scores identiques — ranking non discriminant")
    if len(full_result.get("secondary_hypotheses", [])) >= 2:
        _conf_reasons.append("plusieurs hypothèses alternatives présentes")
    if not _conf_reasons:
        _conf_reasons.append("score discriminant — hypothèse principale claire")

    _CONF_SCORE = {"faible": 1, "modéré": 2, "élevé": 3}
    confidence_detail = {
        "level":       _conf,
        "score":       _CONF_SCORE.get(_conf, 1),
        "scale":       "1=faible / 2=modéré / 3=élevé",
        "reasons":     _conf_reasons,
        "ceiling":     _conds.get(full_result.get("top_hypothesis", ""), {}).get("default_confidence_ceiling", "modéré"),
        "safety_floor_applied": _sf_on,
    }

    # ── input_quality ─────────────────────────────────────────────────────────
    _syms = v1_input.get("symptoms_normalized", [])
    _rfs  = v1_input.get("red_flags", [])
    _n    = len(_syms)
    if _n == 0:
        _iq = "insufficient"
    elif _n <= 2:
        _iq = "low"
    elif _n <= 4:
        _iq = "medium"
    else:
        _iq = "high"

    input_quality = {
        "symptom_count":    _n,
        "red_flags_count":  len(_rfs),
        "quality":          _iq,
        "v2_status":        full_result.get("v2_status"),
        "discriminability": "high" if _conf == "élevé" else "medium" if _conf == "modéré" else "low",
    }

    return {
        "session_id":      session_id,
        "v2_status":       full_result.get("v2_status"),

        # Діагностика
        "top_hypothesis":       full_result.get("top_hypothesis"),
        "secondary_hypotheses": full_result.get("secondary_hypotheses", []),
        "exclude_priority":     full_result.get("exclude_priority", []),
        "confidence_level":     full_result.get("confidence_level"),
        "clinical_group":       full_result.get("clinical_group"),

        # Орієнтація
        "medical_orientation_v2": full_result.get("medical_orientation_v2"),
        "safety_floor":           full_result.get("safety_floor", {}),

        # Тести
        "recommended_tests": full_result.get("recommended_tests", []),
        "test_strategy":     test_strategy,

        # Trace + Economics
        "reasoning_trace":  reasoning_trace,
        "economic_impact":  economic_impact,

        # Нові поля
        "danger_zone":       danger_zone,
        "confidence_detail": confidence_detail,
        "input_quality":     input_quality,

        # Context flags (overlay)
        "context_flags":  context_result["context_flags"],
        "context_alerts": context_result["context_alerts"],

        # Scope
        "scope_status": "in_scope",

        # Meta
        "disclaimer": (
            "ClairDiag v2 — outil d'aide à la décision uniquement. "
            "Ne remplace pas l'avis d'un professionnel de santé."
        ),
    }


@router_v2.post("/export")
def v2_export(request: V2ExportRequest):
    v1_input = {
        "symptoms_normalized": request.symptoms_normalized,
        "red_flags":           request.red_flags,
        "final_action_v1":     request.final_action_v1,
    }

    try:
        etape1, full_result = _run_full_pipeline(v1_input)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "pipeline_error", "detail": str(e)})

    reasoning_trace = build_reasoning_trace(v1_input, etape1, full_result)
    economic_impact = compute_economic_score(
        recommended_tests  = full_result.get("recommended_tests", []),
        orientation        = full_result.get("medical_orientation_v2", ""),
        top_hypothesis     = full_result.get("top_hypothesis"),
        clinical_confidence= full_result.get("confidence_level", "faible"),
        clinical_group     = full_result.get("clinical_group", "general"),
    )

    export = build_export_case(
        session_id      = request.session_id,
        v1_input        = v1_input,
        full_result     = full_result,
        reasoning_trace = reasoning_trace,
        economic_impact = economic_impact,
    )

    # Overlay: context flags
    _ctx = detect_context_flags(request.context_text)
    export["context_flags"]  = _ctx["context_flags"]
    export["context_alerts"] = _ctx["context_alerts"]
    export["scope_status"]   = "in_scope"

    return export

# ── Free Text Schema ──────────────────────────────────────────────────────────

class V2FreeTextRequest(BaseModel):
    free_text: Optional[str] = ""
    audio_base64: Optional[str] = None
    context_text: Optional[str] = ""
    red_flags: List[str] = []
    final_action_v1: str = "consult_doctor"


# ── Free Text Endpoint ────────────────────────────────────────────────────────

@router_v2.post("/analyze_free_text")
def v2_analyze_free_text(request: V2FreeTextRequest):
    """
    POST /v2/analyze_free_text
    Accepts French free-text (or audio stub) → maps → runs v2 engine.
    """
    # Step 1: map free text → normalized symptoms
    mapping = map_input(
        free_text    = request.free_text,
        audio_base64 = request.audio_base64,
    )

    symptoms_normalized = mapping["symptoms_normalized"]
    mapping_confidence  = mapping["mapping_confidence"]

    # Step 2: safety — low confidence → flag but still run
    v2_status_override = None
    if mapping_confidence == "low":
        v2_status_override = "low_input_quality"

    if not symptoms_normalized:
        return {
            "v2_status":          "low_input_quality",
            "top_hypothesis":     None,
            "symptoms_normalized": [],
            "input_quality": {
                "mapping_confidence": mapping_confidence,
                "free_text_used":     mapping["free_text_used"],
                "unmapped_fragments": mapping["unmapped_fragments"],
            },
            "context_flags":  [],
            "context_alerts": [],
            "scope_status":   "in_scope",
            "disclaimer": (
                "ClairDiag v2 — outil d'aide à la décision uniquement. "
                "Ne remplace pas l'avis d'un professionnel de santé."
            ),
        }

    # Step 3: run full v2 pipeline
    session_id = new_session_id()
    v1_input = {
        "symptoms_normalized": symptoms_normalized,
        "red_flags":           request.red_flags,
        "final_action_v1":     request.final_action_v1,
    }

    context_result = detect_context_flags(request.context_text)

    try:
        etape1, full_result = _run_full_pipeline(v1_input)
    except Exception as e:
        logger.error(f"v2 free_text pipeline error: {e!r}")
        return JSONResponse(status_code=500, content={"error": "pipeline_error", "detail": str(e)})

    reasoning_trace = build_reasoning_trace(v1_input, etape1, full_result)
    economic_impact = compute_economic_score(
        recommended_tests   = full_result.get("recommended_tests", []),
        orientation         = full_result.get("medical_orientation_v2", ""),
        top_hypothesis      = full_result.get("top_hypothesis"),
        clinical_confidence = full_result.get("confidence_level", "faible"),
        clinical_group      = full_result.get("clinical_group", "general"),
    )

    log_v2_case(session_id, v1_input, full_result, reasoning_trace, economic_impact,
                context_flags=context_result["context_flags"])

    return {
        "session_id":   session_id,
        "v2_status":    v2_status_override or full_result.get("v2_status"),
        "top_hypothesis":       full_result.get("top_hypothesis"),
        "secondary_hypotheses": full_result.get("secondary_hypotheses", []),
        "exclude_priority":     full_result.get("exclude_priority", []),
        "confidence_level":     full_result.get("confidence_level"),
        "medical_orientation_v2": full_result.get("medical_orientation_v2"),
        "recommended_tests":    full_result.get("recommended_tests", []),
        "reasoning_trace":      reasoning_trace,
        "economic_impact":      economic_impact,
        "context_flags":        context_result["context_flags"],
        "context_alerts":       context_result["context_alerts"],
        "scope_status":         "in_scope",
        "input_quality": {
            "mapping_confidence": mapping_confidence,
            "free_text_used":     mapping["free_text_used"],
            "unmapped_fragments": mapping["unmapped_fragments"],
            "audio_transcribed":  mapping["audio_transcribed"],
        },
        "disclaimer": (
            "ClairDiag v2 — outil d'aide à la décision uniquement. "
            "Ne remplace pas l'avis d'un professionnel de santé."
        ),
    }