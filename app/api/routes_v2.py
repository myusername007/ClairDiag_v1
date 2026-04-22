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

router_v2 = APIRouter()
logger = logging.getLogger("clairdiag.v2")

# ── Schemas ───────────────────────────────────────────────────────────────────

class V2AnalyzeRequest(BaseModel):
    symptoms_normalized: List[str]
    red_flags: List[str] = []
    final_action_v1: str = "consult_doctor"

    model_config = {
        "json_schema_extra": {
            "example": {
                "symptoms_normalized": ["douleur_thoracique", "sueur_froide", "nausees"],
                "red_flags": [],
                "final_action_v1": "consult_urgent",
            }
        }
    }


class V2ExportRequest(BaseModel):
    session_id: str
    symptoms_normalized: List[str]
    red_flags: List[str] = []
    final_action_v1: str = "consult_doctor"


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

    try:
        etape1, full_result = _run_full_pipeline(v1_input)
    except Exception as e:
        logger.error(f"v2 pipeline error: {e!r}")
        return JSONResponse(status_code=500, content={"error": "pipeline_error", "detail": str(e)})

    reasoning_trace = build_reasoning_trace(v1_input, etape1, full_result)

    economic_impact = compute_economic_score(
        recommended_tests = full_result.get("recommended_tests", []),
        orientation       = full_result.get("medical_orientation_v2", ""),
        top_hypothesis    = full_result.get("top_hypothesis"),
    )

    test_strategy = {
        "mode":   full_result.get("next_step_logic", ""),
        "reason": reasoning_trace["test_justification"][0] if reasoning_trace["test_justification"] else "",
    }

    log_v2_case(session_id, v1_input, full_result, reasoning_trace, economic_impact)

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
        recommended_tests = full_result.get("recommended_tests", []),
        orientation       = full_result.get("medical_orientation_v2", ""),
        top_hypothesis    = full_result.get("top_hypothesis"),
    )

    export = build_export_case(
        session_id      = request.session_id,
        v1_input        = v1_input,
        full_result     = full_result,
        reasoning_trace = reasoning_trace,
        economic_impact = economic_impact,
    )

    return export