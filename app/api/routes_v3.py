"""
ClairDiag v3 — API Router
Endpoints:
  POST /v3/analyze  — v3 general orientation pipeline
  GET  /v3/health   — статус v3
"""

import logging
import os
import sys
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import Optional

# ── v3 path setup ─────────────────────────────────────────────────────────────
_V3_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "v3_dev")
if _V3_DIR not in sys.path:
    sys.path.insert(0, _V3_DIR)

from schemas import V3Request
from core import analyze_v3

router_v3 = APIRouter()
logger = logging.getLogger("clairdiag.v3")

# ── Routes ────────────────────────────────────────────────────────────────────

@router_v3.get("/health")
def v3_health():
    return {
        "status":  "ok",
        "engine":  "ClairDiag v3",
        "version": "3.0.0-dev",
    }


@router_v3.post("/analyze")
def v3_analyze(request: V3Request):
    """
    POST /v3/analyze

    Приймає вільний текст пацієнта французькою.
    Повертає general orientation overlay поверх v2 output.

    HARD RULES:
      - v2 safety floor → v2 wins
      - urgent triggers → v2 wins + urgent message
      - v3 тільки additive overlay, без діагнозу
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
    except Exception as e:
        logger.error(f"v3 pipeline error: {e!r}")
        return JSONResponse(
            status_code=500,
            content={"error": "pipeline_error", "detail": str(e)}
        )

    return result