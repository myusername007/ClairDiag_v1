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
    tag: str                        # перший тег (backward compat)
    tags: Optional[list[str]] = None  # multi-select: всі вибрані теги


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

    # Розгортаємо multi-select: якщо tags[] є — створюємо окремий запис на кожен тег
    answers_dicts = []
    for a in request.answers:
        if a.tags and len(a.tags) > 1:
            for t in a.tags:
                answers_dicts.append({"qid": a.qid, "tag": t})
        else:
            answers_dicts.append({"qid": a.qid, "tag": a.tag})

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

# ═══════════════════════════════════════════════════════════════════════════════
# ClairDiag v2.0 — Rules-driven engine endpoints
# ═══════════════════════════════════════════════════════════════════════════════

import sys as _sys
from pathlib import Path as _Path
from typing import List as _List, Dict as _Dict, Any as _Any

_V2_DIR = str(_Path(__file__).parent)
if _V2_DIR not in _sys.path:
    _sys.path.insert(0, _V2_DIR)

try:
    from orchestrator_v2 import OrchestratorV2 as _OrchestratorV2
    _v2_rules_dir = _Path(__file__).parent / "data"
    _v2_orch = _OrchestratorV2(rules_dir=_v2_rules_dir)
    _v2_init_result = _v2_orch.initialize()
    _v2_ready = _v2_init_result.get("success", False)
    if not _v2_ready:
        logger.warning(f"v2 engine init warnings: {_v2_init_result.get('errors')}")
    else:
        logger.info(f"v2 engine ready. modules: {_v2_init_result.get('modules')}")
except Exception as _exc:
    _v2_orch = None
    _v2_ready = False
    logger.warning(f"v2 engine not loaded: {_exc}")


# ── v2.0 Pydantic schemas ────────────────────────────────────────────────────────

class V2LabResult(BaseModel):
    analysis_id: str
    fields: _Dict[str, float]
    source: Optional[str] = "patient_uploaded"


class V2ExamFinding(BaseModel):
    exam_type: str
    finding_text: str
    source: Optional[str] = "patient_uploaded"


class V2PatientContext(BaseModel):
    age: Optional[int] = None
    sex: Optional[str] = None
    pregnancy_status: Optional[str] = None
    pregnancy_trimester: Optional[int] = None
    risk_factors: Optional[_List[str]] = None
    chronic_conditions: Optional[_List[str]] = None
    current_medications: Optional[_List[str]] = None
    onset_speed: Optional[str] = None
    duration_days: Optional[int] = None
    context_flags: Optional[_List[str]] = None
    code_postal: Optional[str] = None


class V2Request(BaseModel):
    free_text: str
    patient_context: Optional[V2PatientContext] = None
    lab_results: Optional[_List[V2LabResult]] = None
    exam_findings: Optional[_List[V2ExamFinding]] = None


class V2FeedbackPayload(BaseModel):
    session_id: Optional[str] = None
    type: str  # patient_outcome | physician_feedback | user_rating
    payload: _Dict[str, _Any]


# ── v2.0 endpoints ───────────────────────────────────────────────────────────────

@router_v3.get("/v2.0/health")
def v2_0_health():
    if not _v2_ready:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "engine": "ClairDiag v2.0", "ready": False}
        )
    return {
        "status": "ok",
        "engine": "ClairDiag v2.0",
        "version": "2.0.0",
        "modules": _v2_init_result.get("modules", {}),
        "rule_versions": {
            k: v.get("version") for k, v in _v2_init_result.get("versions", {}).items()
        },
    }


@router_v3.post("/v2.0/analyze")
def v2_analyze(request: V2Request):
    """
    POST /v2.0/analyze
    Rules-driven medical orientation engine.
    Accepts lab_results and exam_findings in addition to free_text.
    Returns full v2 response with audit trail.
    """
    if not request.free_text or not request.free_text.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "empty_input", "detail": "free_text is required"}
        )

    if not _v2_ready or _v2_orch is None:
        return JSONResponse(
            status_code=503,
            content={"error": "v2_0_engine_unavailable", "detail": "v2 rules engine not initialized"}
        )

    patient_ctx = None
    if request.patient_context:
        pc = request.patient_context
        patient_ctx = {
            k: v for k, v in {
                "age": pc.age,
                "sex": pc.sex,
                "pregnancy_status": pc.pregnancy_status,
                "pregnancy_trimester": pc.pregnancy_trimester,
                "risk_factors": pc.risk_factors or [],
                "chronic_conditions": pc.chronic_conditions or [],
                "current_medications": pc.current_medications or [],
                "onset_speed": pc.onset_speed,
                "duration_days": pc.duration_days,
                "context_flags": pc.context_flags or [],
                "code_postal": pc.code_postal,
            }.items() if v is not None
        }

    lab_results = None
    if request.lab_results:
        lab_results = [
            {"analysis_id": lr.analysis_id, "fields": lr.fields, "source": lr.source}
            for lr in request.lab_results
        ]

    exam_findings = None
    if request.exam_findings:
        exam_findings = [
            {"exam_type": ef.exam_type, "finding_text": ef.finding_text, "source": ef.source}
            for ef in request.exam_findings
        ]

    try:
        result = _v2_orch.analyze(
            text=request.free_text,
            patient_context=patient_ctx,
            lab_results=lab_results,
            exam_findings=exam_findings,
        )
    except Exception as e:
        logger.error(f"v2.0 pipeline error: {e!r}")
        return JSONResponse(
            status_code=500,
            content={"error": "v2_0_pipeline_error", "detail": str(e)}
        )

    return result


@router_v3.post("/v2.0/feedback")
def v2_feedback(request: V2FeedbackPayload):
    """
    POST /v2.0/feedback
    Submit feedback event (S9). Never mutates rule files.
    """
    if not _v2_ready or _v2_orch is None:
        return JSONResponse(status_code=503, content={"error": "v2_0_engine_unavailable"})

    result = _v2_orch.submit_feedback({
        "session_id": request.session_id,
        "type": request.type,
        "payload": request.payload,
    })
    return result