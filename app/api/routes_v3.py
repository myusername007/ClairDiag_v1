"""
ClairDiag v3 — API Router v3.2.0
Endpoints:
  POST /v3/analyze          — v3 general orientation pipeline
  POST /v3/analyze/followup — adaptive follow-up questions (Module 01)
  GET  /v3/health           — статус v3
"""

import logging
import os
import sys
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

_V3_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "v3_dev")
if _V3_DIR not in sys.path:
    sys.path.insert(0, _V3_DIR)

from schemas import V3Request
from core import analyze_v3
from followup_engine import FollowupEngine

router_v3 = APIRouter()
logger = logging.getLogger("clairdiag.v3")

# Singleton engine (in-memory sessions)
_followup_engine = FollowupEngine()


# ── Followup request schemas ───────────────────────────────────────────────────

class FollowupAnswer(BaseModel):
    qid: str
    tag: str


class FollowupRequest(BaseModel):
    session_id: str
    round: int
    answers: list[FollowupAnswer]


# ── Helpers ────────────────────────────────────────────────────────────────────

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


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router_v3.get("/health")
def v3_health():
    return {
        "status":  "ok",
        "engine":  "ClairDiag v3",
        "version": "3.2.0",
    }


@router_v3.post("/analyze")
def v3_analyze(request: V3Request):
    """
    POST /v3/analyze
    Повертає multi-layer output + backward-compatible поля.
    Якщо confidence низький або категорія vague → поле followup_needed=True
    з session_id і питаннями для наступного кроку.
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

    # ── Followup trigger (non-blocking) ───────────────────────────────────────
    try:
        followup_result = _followup_engine.initiate_followup(
            v3_response=result,
            patient_context=patient_context_dict or {},
        )
        if followup_result.get("followup_needed"):
            # Повертаємо v3_response + followup questions
            result["followup_needed"] = True
            result["session_id"] = followup_result["session_id"]
            result["followup_questions"] = followup_result["questions"]
            result["followup_round"] = followup_result["round"]
            result["followup_max_rounds"] = followup_result["max_rounds"]
        else:
            result["followup_needed"] = False
    except Exception as e:
        # Followup est additif — jamais bloquer le pipeline principal
        logger.warning(f"followup engine error (non-blocking): {e!r}")
        result["followup_needed"] = False

    return result


@router_v3.post("/analyze/followup")
def v3_followup(request: FollowupRequest):
    """
    POST /v3/analyze/followup
    Reçoit les réponses patient au follow-up, retourne:
    - Round suivant (si round 2 nécessaire)
    - Réponse finale modifiée (si toutes les questions posées ou urgent déclenché)

    Body: {
      "session_id": "uuid",
      "round": 1,
      "answers": [{"qid": "DERM-Q1", "tag": "duration_acute"}, ...]
    }
    """
    if not request.session_id:
        return JSONResponse(
            status_code=400,
            content={"error": "session_id_required"},
        )

    if not request.answers:
        return JSONResponse(
            status_code=400,
            content={"error": "answers_required", "detail": "Provide at least one answer"},
        )

    answers_dicts = [{"qid": a.qid, "tag": a.tag} for a in request.answers]

    try:
        result = _followup_engine.submit_answers(
            session_id=request.session_id,
            round_number=request.round,
            answers=answers_dicts,
        )
    except Exception as e:
        logger.error(f"followup submit error: {e!r}")
        return JSONResponse(
            status_code=500,
            content={"error": "followup_error", "detail": str(e)},
        )

    if "error" in result:
        return JSONResponse(status_code=404, content=result)

    # Si round suivant → inclure questions
    if result.get("followup_needed"):
        return result

    # Résultat final — ajouter flag
    result["followup_completed"] = True
    return result