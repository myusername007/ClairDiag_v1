import logging
from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import (
    AnalyzeRequest, AnalyzeResponse, ParseSymptomsRequest,
    RevaluateRequest, RevaluateResponse, TestImpact, Diagnosis,
    ParseConfirmRequest, ParseConfirmResponse,
    ENGINE_VERSION, RULES_VERSION, REGISTRY_VERSION,
    VALIDATION_BASELINE, CORE_STATUS,
)
from app.pipeline.nse import parse_text
import app.pipeline as pipeline_module
from app.pipeline import erl
from app.pipeline import session as session_store
from app.pipeline.tcs import run as tcs_run
from app.pipeline.rme import run as rme_run
from app.pipeline.sgl import run as sgl_run
from app.pipeline.orchestrator import _build_decision
from app.data.symptoms import DEMO_SCENARIOS

router = APIRouter()
logger = logging.getLogger("clairdiag")


@router.get("/health")
def health():
    return {
        "status": "ok",
        "engine_version": ENGINE_VERSION,
        "rules_version": RULES_VERSION,
        "registry_version": REGISTRY_VERSION,
        "validation_baseline": VALIDATION_BASELINE,
        "core_status": CORE_STATUS,
    }


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_symptoms(
    request: AnalyzeRequest,
    debug: bool = Query(False),
    validation_mode: bool = Query(False),
) -> AnalyzeResponse:
    # Query params override body fields
    if debug:
        request.debug = True
    if validation_mode:
        request.validation_mode = True

    symptoms_clean = [s.strip() for s in request.symptoms if s.strip()]
    logger.info(f"Analyse: {symptoms_clean} | onset={request.onset} | duration={request.duration}")
    try:
        result = pipeline_module.run(
            AnalyzeRequest(
                symptoms=symptoms_clean,
                onset=request.onset,
                duration=request.duration,
                debug=request.debug,
                validation_mode=request.validation_mode,
            )
        )
        logger.info(
            f"Résultat: {len(result.diagnoses)} diagnostics | "
            f"emergency={result.emergency_flag} | decision={result.decision}"
        )

        if not result.emergency_flag and result.diagnoses:
            from app.pipeline import nse, scm, bpu, cre, tce
            s1 = nse.run(symptoms_clean)
            s2 = scm.run(s1)
            probs_raw, _ = bpu.run(s2)
            probs_cre = cre.run(probs_raw, s2)
            probs_tce = tce.run(probs_cre, onset=request.onset, duration=request.duration)
            session_id = session_store.create(probs_tce, s2)
            result.session_id = session_id

        return result
    except Exception as e:
        logger.error(f"Erreur pipeline: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")


@router.post("/parse-symptoms")
def parse_symptoms_endpoint(request: ParseSymptomsRequest) -> dict:
    detected = parse_text(request.text)
    return {"detected": detected, "count": len(detected)}


@router.post("/parse-confirm", response_model=ParseConfirmResponse)
def parse_confirm(request: ParseConfirmRequest) -> ParseConfirmResponse:
    from app.pipeline import scm
    from app.data.symptoms import ALIASES, SYMPTOM_DIAGNOSES

    detected_raw = parse_text(request.text)
    detected = scm.run(detected_raw)

    text_lower = request.text.lower()
    known_words = set(SYMPTOM_DIAGNOSES.keys()) | set(ALIASES.keys())
    words = [w.strip(".,!?;:") for w in text_lower.split()]
    unknown = [
        w for w in words
        if len(w) > 3 and w not in known_words
        and not any(w in k for k in known_words)
    ][:5]

    if detected:
        items = "\n".join(f" • {s}" for s in detected)
        msg = f"Symptômes reconnus :\n{items}\n\nConfirmer pour analyser ?"
    else:
        msg = "Aucun symptôme reconnu. Essayez de décrire vos symptômes différemment."

    logger.info(f"ParseConfirm: '{request.text[:50]}' → {detected}")

    return ParseConfirmResponse(
        detected=detected,
        unknown=unknown,
        confirmation_message=msg,
        ready_to_analyze=len(detected) > 0,
    )


@router.post("/revaluate", response_model=RevaluateResponse)
def revaluate(request: RevaluateRequest) -> RevaluateResponse:
    """
    Post-test reasoning 2.0.
    Перераховує ймовірності + показує що і чому змінилось + decision_before/after.
    """
    session = session_store.get(request.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session introuvable ou expirée (TTL 30 min). Relancez /analyze."
        )

    probs_before = session["probs"]
    symptoms = session["symptoms"]

    # Snapshot before
    diagnoses_before = [
        Diagnosis(name=n, probability=round(p, 2))
        for n, p in sorted(probs_before.items(), key=lambda x: -x[1])[:3]
        if p >= 0.15
    ]

    # decision_before
    tcs_before, conf_before, _ = tcs_run(probs_before, len(symptoms), symptoms=symptoms)
    urgency_before = rme_run(probs_before)
    top3_before = [d.name for d in diagnoses_before]
    misdiag_before = _compute_misdiagnosis_risk_simple(probs_before, len(symptoms))
    decision_before = _build_decision(
        emergency=False,
        urgency_level=urgency_before,
        misdiagnosis_risk=misdiag_before,
        tcs_level=tcs_before,
    )

    # ERL — recalcul
    probs_after, changes_log = erl.run(probs_before, request.exam_results)

    # Structured tests_impact
    tests_impact = _build_tests_impact(probs_before, probs_after, request.exam_results)

    # Levels after
    tcs_after, confidence_level, _ = tcs_run(probs_after, len(symptoms), symptoms=symptoms)
    urgency_after = rme_run(probs_after)
    confidence_final, sgl_warnings = sgl_run(
        diagnoses_names=[n for n, _ in sorted(probs_after.items(), key=lambda x: -x[1])[:3]],
        probs=probs_after,
        symptom_count=len(symptoms),
        confidence_level=confidence_level,
    )

    # Diagnostics after
    diagnoses_after = [
        Diagnosis(name=n, probability=round(p, 2))
        for n, p in sorted(probs_after.items(), key=lambda x: -x[1])[:3]
        if p >= 0.15
    ]

    misdiag_after = _compute_misdiagnosis_risk_simple(probs_after, len(symptoms))
    decision_after = _build_decision(
        emergency=False,
        urgency_level=urgency_after,
        misdiagnosis_risk=misdiag_after,
        tcs_level=tcs_after,
    )

    # Human-readable summaries
    changes_summary = _build_changes_summary(diagnoses_before, diagnoses_after, changes_log)
    reasoning_summary = _build_reasoning_summary(
        tests_impact, decision_before, decision_after
    )

    session_store.delete(request.session_id)

    logger.info(
        f"Revaluate: session={request.session_id[:8]}… "
        f"exams={list(request.exam_results.keys())} "
        f"decision {decision_before} → {decision_after}"
    )

    return RevaluateResponse(
        session_id=request.session_id,
        diagnoses_before=diagnoses_before,
        diagnoses_after=diagnoses_after,
        decision_before=decision_before,
        decision_after=decision_after,
        changes_log=changes_log,
        tests_impact=tests_impact,
        changes_summary=changes_summary,
        reasoning_summary=reasoning_summary,
        tcs_level=tcs_after,
        confidence_level=confidence_final,
        urgency_level=urgency_after,
        sgl_warnings=sgl_warnings,
    )


@router.get("/admin/debug")
def admin_debug(
    symptoms: str = Query(..., description="Симптоми через кому"),
    onset: Optional[str] = Query(None),
    duration: Optional[str] = Query(None),
):
    """
    Admin/debug endpoint — повна трейс-картина pipeline.
    Використовувати тільки для розробки / валідації.
    """
    from app.models.schemas import AnalyzeRequest
    import app.pipeline as pipeline_module

    symptom_list = [s.strip() for s in symptoms.split(",") if s.strip()]
    result = pipeline_module.run(
        AnalyzeRequest(
            symptoms=symptom_list,
            onset=onset,
            duration=duration,
            debug=True,
            validation_mode=True,
        )
    )

    trace = result.debug_trace
    val = result.validation

    return {
        "core": {
            "engine_version": ENGINE_VERSION,
            "rules_version": RULES_VERSION,
            "core_status": CORE_STATUS,
        },
        "input": {
            "symptoms_raw": symptom_list,
            "symptoms_after_parser": trace.symptoms_after_parser if trace else [],
            "symptoms_after_scm": trace.symptoms_after_scm if trace else [],
        },
        "safety": {
            "emergency": trace.emergency if trace else False,
            "red_flags": trace.red_flags_detected if trace else [],
            "emergency_override": trace.emergency_override_triggered if trace else False,
            "emergency_override_patterns": trace.emergency_override_patterns if trace else [],
        },
        "scoring": {
            "bpu": trace.bpu.dict() if trace else {},
            "cre": trace.cre.dict() if trace else {},
            "tce": trace.tce.dict() if trace else {},
        },
        "classification": {
            "tcs": trace.tcs.dict() if trace else {},
            "confidence_gap_top1_top2": trace.confidence_gap_top1_top2 if trace else 0.0,
            "misdiagnosis_risk": trace.misdiagnosis_risk if trace else "",
            "misdiagnosis_risk_score": trace.misdiagnosis_risk_score if trace else 0.0,
        },
        "output": {
            "top3": [{"name": d.name, "probability": d.probability} for d in result.diagnoses],
            "decision": result.decision,
            "urgency": result.urgency_level,
            "tcs_level": result.tcs_level,
            "do_not_miss": result.do_not_miss,
        },
        "tests": {
            "required": result.tests.required,
            "optional": result.tests.optional,
            "test_priority_reasoning": trace.test_priority_reasoning if trace else [],
            "test_details": result.test_details,
        },
        "reasoning": {
            "diagnostic_path": result.diagnostic_path,
            "differential": result.differential,
            "sgl_warnings": trace.sgl_warnings if trace else [],
            "diagnostic_path_summary": trace.diagnostic_path_summary if trace else "",
            "decision_reasoning": trace.decision if trace else "",
        },
        "validation": val.dict() if val else {},
    }


@router.get("/scenarios")
def get_scenarios() -> dict:
    return {
        "scenarios": [
            {"name": name, "symptoms": symptoms}
            for name, symptoms in DEMO_SCENARIOS.items()
        ]
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _compute_misdiagnosis_risk_simple(probs: dict, symptom_count: int) -> str:
    """Simplified version for revaluate (no full diagnoses list needed)."""
    sorted_p = sorted(probs.values(), reverse=True)
    gap = (sorted_p[0] - sorted_p[1]) if len(sorted_p) >= 2 else 1.0
    score = 0.0
    if gap < 0.10:
        score += 0.35
    elif gap < 0.20:
        score += 0.20
    if symptom_count <= 2:
        score += 0.25
    if score >= 0.50:
        return "élevé"
    elif score >= 0.25:
        return "modéré"
    return "faible"


def _build_tests_impact(
    probs_before: dict,
    probs_after: dict,
    exam_results: dict,
) -> list[TestImpact]:
    """Structured per-test impact."""
    from app.pipeline.erl import _find_test
    from app.data.tests import TEST_CATALOG

    impacts = []
    for test_name, raw_value in exam_results.items():
        catalog_key = _find_test(test_name)
        if not catalog_key:
            continue
        dv = TEST_CATALOG[catalog_key].get("diagnostic_value", {})
        value = raw_value.strip().lower()
        is_positive = value in {
            "high", "positive", "present", "élevé", "positif",
            "infiltrat", "anormal", "pathologique", "elevated",
            "augmenté", "augmentée", "présent", "présente",
        }
        direction = "boost" if is_positive else "suppress"

        # Top impacted diagnosis = highest dv in common
        for diag, diag_val in sorted(dv.items(), key=lambda x: -x[1]):
            if diag not in probs_before:
                continue
            delta = round(probs_after.get(diag, 0) - probs_before.get(diag, 0), 3)
            if abs(delta) < 0.001:
                continue
            impacts.append(TestImpact(
                test=test_name,
                result=raw_value,
                target_diagnosis=diag,
                delta=delta,
                direction=direction,
                reason=(
                    f"Valeur diagnostique {diag_val:.0%} — "
                    f"résultat {'positif' if is_positive else 'négatif'} "
                    f"{'renforce' if is_positive else 'affaiblit'} {diag}"
                ),
            ))

    return impacts


def _build_changes_summary(
    before: list[Diagnosis],
    after: list[Diagnosis],
    changes_log: list[str],
) -> str:
    if not before or not after:
        return "Aucun changement significatif détecté."

    top_before = before[0].name if before else "?"
    top_after = after[0].name if after else "?"

    if top_before != top_after:
        return (
            f"Le diagnostic principal a changé : {top_before} → {top_after}. "
            f"{len(changes_log)} modification(s) appliquée(s)."
        )
    else:
        prob_before = before[0].probability
        prob_after = after[0].probability
        delta = round(prob_after - prob_before, 2)
        direction = "renforcé" if delta > 0 else "affaibli"
        return (
            f"Le diagnostic principal ({top_after}) a été {direction} "
            f"({'+' if delta > 0 else ''}{int(delta * 100)}%). "
            f"{len(changes_log)} modification(s) appliquée(s)."
        )


def _build_reasoning_summary(
    tests_impact: list[TestImpact],
    decision_before: str,
    decision_after: str,
) -> str:
    if not tests_impact:
        return "Aucun examen n'a modifié significativement l'analyse."

    boosts = [t for t in tests_impact if t.direction == "boost"]
    suppresses = [t for t in tests_impact if t.direction == "suppress"]
    parts = []
    if boosts:
        top = max(boosts, key=lambda x: abs(x.delta))
        parts.append(f"{top.test} positif renforce {top.target_diagnosis}")
    if suppresses:
        top = max(suppresses, key=lambda x: abs(x.delta))
        parts.append(f"{top.test} négatif réduit {top.target_diagnosis}")

    summary = ". ".join(parts) + "."
    if decision_before != decision_after:
        summary += f" Décision modifiée : {decision_before} → {decision_after}."
    return summary


# Fix Optional import
from typing import Optional