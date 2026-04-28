"""
ClairDiag v3 — API Router v3.1.0
Endpoints:
  POST /v3/analyze  — v3 general orientation pipeline
  GET  /v3/health   — статус v3
"""

import logging
import os
import sys
from fastapi import APIRouter
from fastapi.responses import JSONResponse

_V3_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "v3_dev")
if _V3_DIR not in sys.path:
    sys.path.insert(0, _V3_DIR)

from schemas import V3Request
from core import analyze_v3

router_v3 = APIRouter()
logger = logging.getLogger("clairdiag.v3")


def _flatten(result: dict) -> dict:
    """
    Додає backward-compatible поля на верхній рівень
    поруч з новою multi-layer структурою.
    Фронтенд і зовнішні клієнти можуть читати обидва формати.
    """
    clinical = result.get("clinical", {})
    triage = result.get("triage", {})
    confidence = result.get("confidence", {})
    engine = result.get("engine", {})

    result["general_orientation"] = clinical.get("general_orientation")
    result["clinical_reasoning"] = clinical.get("clinical_reasoning")
    result["matched_symptoms"] = clinical.get("matched_symptoms", [])
    result["danger_output"] = result.get("danger", {}).get("danger_output")
    result["confidence_detail"] = confidence
    result["v2_output"] = engine.get("v2_output")
    result["routing_decision"] = engine.get("routing_decision")
    result["urgency"] = triage.get("urgency")
    result["urgent_message"] = triage.get("urgent_message")

    return result


@router_v3.get("/health")
def v3_health():
    return {
        "status":  "ok",
        "engine":  "ClairDiag v3",
        "version": "3.1.0",
    }


@router_v3.post("/analyze")
def v3_analyze(request: V3Request):
    """
    POST /v3/analyze
    Повертає multi-layer output + backward-compatible поля.
    """
    if not request.free_text or not request.free_text.strip():
        return JSONResponse(
            status_code=400,
            content={
                "error": "empty_input",
                "detail": "free_text is required",
                "v3_status": "no_input",
            }
        )

    patient_context_dict = None
    if request.patient_context:
        patient_context_dict = request.patient_context.model_dump()

    try:
        result = analyze_v3(
            free_text=request.free_text,
            patient_context=patient_context_dict,
        )
        result = _flatten(result)
    except Exception as e:
        logger.error(f"v3 pipeline error: {e!r}")
        return JSONResponse(
            status_code=500,
            content={"error": "pipeline_error", "detail": str(e)}
        )

    return result