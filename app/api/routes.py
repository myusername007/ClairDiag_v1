import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import (
    AnalyzeRequest, AnalyzeResponse, ParseSymptomsRequest,
    RevaluateRequest, RevaluateResponse, TestImpact, Diagnosis,
    ParseConfirmRequest, ParseConfirmResponse,
    ENGINE_VERSION, RULES_VERSION, REGISTRY_VERSION,
    VALIDATION_BASELINE, CORE_STATUS, SymptomContext,
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
from app.pipeline.nlp_normalizer import extract_symptoms
from app.pipeline.context_parser import parse_context, apply_context_boosts
from app.pipeline.request_logger import log_request

# ── DEMO_CASE — fallback якщо pipeline впав ───────────────────────────────────
_DEMO_CASE = {
    "diagnoses": [{"name": "Gastrite", "probability": 0.78, "key_symptoms": ["douleur abdominale", "nausées"]}],
    "tests": {"required": ["NFS", "CRP"], "optional": []},
    "economics": {"standard_cost": 120, "optimized_cost": 65, "savings": 55, "currency": "EUR", "pricing_basis": "demo"},
    "explanation": "Analyse en mode démo. Consultez un médecin pour un diagnostic réel.",
    "confidence_level": "modéré",
    "urgency_level": "faible",
    "emergency_flag": False,
    "emergency_reason": "",
    "tcs_level": "TCS_3",
    "decision": "MEDICAL_REVIEW",
    "sgl_warnings": ["Mode démo activé — résultat indicatif uniquement."],
    "test_explanations": {},
    "test_probabilities": {},
    "test_costs": {},
    "consultation_cost": 30,
    "debug_trace": None,
    "validation": None,
    "differential": [],
    "test_details": [],
    "diagnostic_path": {},
    "misdiagnosis_risk": "modéré",
    "misdiagnosis_risk_score": 0.3,
    "worsening_signs": [],
    "do_not_miss": [],
    "analysis_limits": [],
    "session_id": None,
    "interpreted_symptoms": [],
    "note": "mode démo activé",
}

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

    # ── NLP Normalization: збагачуємо симптоми перед pipeline ────────────────
    # Якщо юзер надіслав один рядок тексту — нормалізуємо його
    raw_text = " ".join(symptoms_clean)
    normalized = extract_symptoms(raw_text)

    # Якщо нормалайзер знайшов щось — замінюємо/доповнюємо
    if normalized:
        # Об'єднуємо оригінальні + нормалізовані (без дублів)
        merged = list(dict.fromkeys(symptoms_clean + normalized))
        interpreted_symptoms = normalized
    else:
        merged = symptoms_clean
        interpreted_symptoms = []

    # low_confidence_input: нічого не знайшли взагалі
    if not merged:
        logger.warning(f"low_confidence_input: '{raw_text[:80]}'")
        return {
            "error": "low_confidence_input",
            "suggestion": "utiliser des termes médicaux ou choisir dans la liste",
            "interpreted_symptoms": [],
        }

    logger.info(
        f"Analyse: {merged} | onset={request.onset} | duration={request.duration} "
        f"| interpreted={interpreted_symptoms}"
    )
    try:
        result = pipeline_module.run(
            AnalyzeRequest(
                symptoms=merged,
                onset=request.onset,
                duration=request.duration,
                debug=request.debug,
                validation_mode=request.validation_mode,
                voice_confidence=request.voice_confidence,
            )
        )
        logger.info(
            f"Résultat: {len(result.diagnoses)} diagnostics | "
            f"emergency={result.emergency_flag} | decision={result.decision}"
        )

        # UX Confirmation — додаємо interpreted_symptoms у відповідь
        result.interpreted_symptoms = interpreted_symptoms

        # ── Context Parser (патч п.4–5) ──────────────────────────────────────
        ctx = parse_context(raw_text)
        result.context = SymptomContext(
            trigger=          ctx.get("trigger"),
            pattern=          ctx.get("pattern"),
            cause=            ctx.get("cause"),
            frequency=        ctx.get("frequency"),
            chronology=       ctx.get("chronology"),
            aggravation_time= ctx.get("aggravation_time"),
            after_food=       ctx.get("after_food", False),
            post_medication=  ctx.get("post_medication", False),
            night_worsening=  ctx.get("night_worsening", False),
        )

        # context_influence в clinical_reasoning
        if result.clinical_reasoning and ctx.get("trigger"):
            parts = []
            if ctx.get("after_food"):
                parts.append("after_meal → boost Gastrite/Dyspepsie")
            if ctx.get("post_medication"):
                parts.append("post-antibiotiques → boost Dysbiose/SII")
            if ctx.get("night_worsening"):
                parts.append("aggravation nocturne → contexte Insuffisance cardiaque")
            if parts:
                result.clinical_reasoning.context_influence = "; ".join(parts)

        # п.10 — context_logic_consistent: перевіряємо context vs top1
        _DIGESTIVE = {"Gastrite", "RGO", "SII", "Dyspepsie"}
        if result.consistency_check and ctx.get("after_food"):
            top1_name = result.diagnoses[0].name if result.diagnoses else ""
            ctx_logic = top1_name in _DIGESTIVE
            result.consistency_check.context_logic_consistent = ctx_logic

        # п.13 — context_quality: якщо є context fields — підвищуємо
        if result.trust_score:
            ctx_fields = sum(1 for k in ("trigger","cause","frequency","chronology")
                             if ctx.get(k))
            result.trust_score.context_quality = round(min(ctx_fields / 3.0, 1.0), 2)

        # п.15 — audit: заповнюємо context_detected + symptom_trace
        if result.audit:
            ctx_display = {k: str(v) for k, v in ctx.items()
                          if k != "flags" and v and v is not False}
            result.audit.context_detected = ctx_display
            if result.symptom_trace:
                result.audit.symptom_trace = result.symptom_trace.traces

        # ── EXPLAINABILITY LAYER: inject context into new blocks ────────────
        from app.pipeline.orchestrator import (
            _build_clinical_reasoning_v2,
            _build_probability_reasoning,
            _build_do_not_miss_engine,
            _build_explainability_score,
        )

        # FIX 1: do_not_miss_engine будується завжди — навіть якщо diagnoses порожні
        # C.diff детектується на рівні raw_text незалежно від pipeline
        _syms_for_explain_base = list(result.audit.normalized_symptoms) if result.audit else merged
        result.do_not_miss_engine = _build_do_not_miss_engine(
            symptoms_compressed=_syms_for_explain_base,
            context=ctx,
            diagnoses=result.diagnoses,
            urgency_level=result.urgency_level,
            raw_text=raw_text,
        )

        if result.diagnoses:
            _probs_for_explain = {d.name: d.probability for d in result.diagnoses}
            _syms_for_explain = _syms_for_explain_base

            result.clinical_reasoning_v2 = _build_clinical_reasoning_v2(
                diagnoses=result.diagnoses,
                symptoms_compressed=_syms_for_explain,
                probs=_probs_for_explain,
                context=ctx,
            )
            result.probability_reasoning = _build_probability_reasoning(
                diagnoses=result.diagnoses,
                symptoms_compressed=_syms_for_explain,
                probs=_probs_for_explain,
                context=ctx,
            )
            # п.4: якщо do_not_miss_engine має mandatory_tests — додаємо в required
            if result.do_not_miss_engine and result.do_not_miss_engine.mandatory_tests:
                existing = set(result.tests.required)
                for mt in result.do_not_miss_engine.mandatory_tests:
                    if mt not in existing:
                        result.tests.required.append(mt)
                        existing.add(mt)
                        # update test_reasoning
                        if result.test_reasoning:
                            result.test_reasoning.links[mt] = (
                                result.test_reasoning.links.get(mt)
                                or f"Obligatoire — règle do-not-miss clinique"
                            )

            # п.6: differential cleaning — SII в contexte aigu post-abx
            if ctx.get("post_medication") and result.diagnoses:
                result.diagnoses = [
                    d for d in result.diagnoses
                    if not (d.name == "SII" and ctx.get("post_medication"))
                ] or result.diagnoses  # garde au moins 1

            result.explainability = _build_explainability_score(
                clinical_v2=result.clinical_reasoning_v2,
                probability_reasoning=result.probability_reasoning,
                test_reasoning=result.test_reasoning or __import__(
                    'app.models.schemas', fromlist=['TestReasoning']
                ).TestReasoning(),
                do_not_miss=result.do_not_miss_engine,
                context=ctx,
            )

            # п.8 validation gate: is_valid_output = False si pas de reasoning
            has_reasoning = bool(
                result.clinical_reasoning_v2 and result.clinical_reasoning_v2.main_logic
            )
            has_test_logic = bool(result.test_reasoning and result.test_reasoning.links)
            has_do_not_miss = result.do_not_miss_engine is not None
            has_context_link = bool(
                result.clinical_reasoning_v2
                and any("contexte" in l.lower() or "context" in l.lower()
                        for l in result.clinical_reasoning_v2.main_logic)
            ) or not any(ctx.get(k) for k in ("after_food", "post_medication", "night_worsening"))

            # FIX 2: single symptom → insufficient data → is_valid_output = False
            single_symptom_high_conf = (
                len(_syms_for_explain) <= 1
                and result.diagnoses
                and result.diagnoses[0].probability >= 0.60
            )

            if not (has_reasoning and has_test_logic and has_do_not_miss and has_context_link):
                result.is_valid_output = False
            elif single_symptom_high_conf:
                result.is_valid_output = False
                if result.edge_case_analysis:
                    result.edge_case_analysis.manual_review_recommended = True
                    result.edge_case_analysis.fallback_reason = (
                        "Symptôme unique — données insuffisantes pour résultat valide"
                    )

        # п.18 — structured logging
        try:
            log_request(
                input_text=raw_text,
                normalized=interpreted_symptoms,
                parsed=list(merged),
                confidence=result.confidence_level,
                decision=result.decision,
                session_id=result.session_id,
            )
        except Exception:
            pass

        if not result.emergency_flag and result.diagnoses:
            from app.pipeline import nse, scm, bpu, cre, tce
            s1 = nse.run(merged)
            s2 = scm.run(s1)
            probs_raw, _ = bpu.run(s2)
            probs_cre = cre.run(probs_raw, s2)
            probs_tce = tce.run(probs_cre, onset=request.onset, duration=request.duration)
            session_id = session_store.create(probs_tce, s2)
            result.session_id = session_id

        return result
    except Exception as e:
        logger.error(f"Erreur pipeline: {e}", exc_info=True)
        # ── DEMO fallback — не падаємо, повертаємо demo-результат ────────────
        demo = dict(_DEMO_CASE)
        demo["interpreted_symptoms"] = interpreted_symptoms
        return demo


@router.post("/parse-symptoms")
def parse_symptoms_endpoint(request: ParseSymptomsRequest) -> dict:
    # NLP normalization перед parse_text
    normalized = extract_symptoms(request.text)
    detected_raw = parse_text(request.text)
    # Об'єднуємо: parse_text + normalizer (без дублів)
    detected = list(dict.fromkeys(detected_raw + [s for s in normalized if s not in detected_raw]))
    return {"detected": detected, "count": len(detected), "interpreted_symptoms": normalized}


@router.post("/parse-confirm", response_model=ParseConfirmResponse)
def parse_confirm(request: ParseConfirmRequest) -> ParseConfirmResponse:
    from app.pipeline import scm
    from app.data.symptoms import ALIASES, SYMPTOM_DIAGNOSES

    detected_raw = parse_text(request.text)
    # NLP normalization — доповнюємо
    normalized = extract_symptoms(request.text)
    detected_raw_merged = list(dict.fromkeys(detected_raw + [s for s in normalized if s not in detected_raw]))
    detected = scm.run(detected_raw_merged)

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

    ctx = parse_context(request.text)

    return ParseConfirmResponse(
        detected=detected,
        unknown=unknown,
        confirmation_message=msg,
        ready_to_analyze=len(detected) > 0,
        context=SymptomContext(
            trigger=          ctx.get("trigger"),
            pattern=          ctx.get("pattern"),
            cause=            ctx.get("cause"),
            frequency=        ctx.get("frequency"),
            chronology=       ctx.get("chronology"),
            aggravation_time= ctx.get("aggravation_time"),
            after_food=       ctx.get("after_food", False),
            post_medication=  ctx.get("post_medication", False),
            night_worsening=  ctx.get("night_worsening", False),
        ),
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

    # Levels after
    tcs_after, confidence_level, _ = tcs_run(probs_after, len(symptoms), symptoms=symptoms)
    urgency_after = rme_run(probs_after)
    confidence_final, sgl_warnings = sgl_run(
        diagnoses_names=[n for n, _ in sorted(probs_after.items(), key=lambda x: -x[1])[:3]],
        probs=probs_after,
        symptom_count=len(symptoms),
        confidence_level=confidence_level,
    )

    # Diagnostics after — обраховуємо ДО tests_impact
    diagnoses_after = [
        Diagnosis(name=n, probability=round(p, 2))
        for n, p in sorted(probs_after.items(), key=lambda x: -x[1])[:3]
        if p >= 0.15
    ]

    # Structured tests_impact — тільки діагнози з diagnoses_after
    tests_impact = _build_tests_impact(probs_before, probs_after, request.exam_results, diagnoses_after)

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
        tests_impact, decision_before, decision_after, diagnoses_after
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
    diagnoses_after: list | None = None,
) -> list[TestImpact]:
    """
    ТЗ: Top1 → Top2 → Top3.
    Використовує intended_delta з TEST_CATALOG (без обмеження стелею 0.9).
    """
    from app.pipeline.erl import _find_test, _BOOST_MULTIPLIER, _PENALTY_MULTIPLIER
    from app.data.tests import TEST_CATALOG

    _POSITIVE_VALUES = {
        "high", "positive", "present", "élevé", "positif",
        "infiltrat", "anormal", "pathologique", "elevated",
        "augmenté", "augmentée", "présent", "présente",
    }

    after_names = [d.name for d in (diagnoses_after or [])]
    after_set = set(after_names)

    def diag_priority(d):
        try: return after_names.index(d)
        except ValueError: return 9

    impacts = []
    for test_name, raw_value in exam_results.items():
        catalog_key = _find_test(test_name)
        if not catalog_key:
            continue
        dv = TEST_CATALOG[catalog_key].get("diagnostic_value", {})
        value = raw_value.strip().lower()
        is_positive = value in _POSITIVE_VALUES
        direction = "boost" if is_positive else "suppress"
        multiplier = _BOOST_MULTIPLIER if is_positive else _PENALTY_MULTIPLIER

        for diag, diag_val in sorted(dv.items(), key=lambda x: (diag_priority(x[0]), -x[1])):
            if diag not in after_set:
                continue
            if diag not in probs_before:
                continue
            intended_delta = round(diag_val * multiplier, 3)
            if intended_delta < 0.001:
                continue
            impacts.append(TestImpact(
                test=test_name,
                result=raw_value,
                target_diagnosis=diag,
                delta=intended_delta,
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
    """
    ТЗ: порівнювати before vs after, писати тільки реальні зміни.
    inchangé / renforcé / affaibli per diagnosis.
    """
    if not after:
        return "Aucun changement significatif détecté."

    before_map = {d.name: d.probability for d in before}
    after_map  = {d.name: d.probability for d in after}

    parts = []
    for d in after[:3]:
        p_after  = d.probability
        p_before = before_map.get(d.name)
        if p_before is None:
            parts.append(f"{d.name} apparu ({p_after:.0%})")
        else:
            delta = round(p_after - p_before, 2)
            if abs(delta) < 0.02:
                parts.append(f"{d.name} inchangé")
            elif delta > 0:
                parts.append(f"{d.name} renforcé (+{int(delta*100)}%)")
            else:
                parts.append(f"{d.name} affaibli ({int(delta*100)}%)")

    return ". ".join(parts) + "." if parts else "Aucun changement significatif."


def _build_reasoning_summary(
    tests_impact: list[TestImpact],
    decision_before: str,
    decision_after: str,
    diagnoses_after: list[Diagnosis] | None = None,
) -> str:
    """
    ТЗ: використовувати ТІЛЬКИ діагнози з diagnoses_after.
    Не згадувати відсутні діагнози.
    """
    if not tests_impact:
        return "Aucun examen n'a modifié significativement l'analyse."

    after_names = {d.name for d in (diagnoses_after or [])}

    # Фільтруємо тільки impacts для діагнозів що є в after
    relevant = [t for t in tests_impact if not after_names or t.target_diagnosis in after_names]
    if not relevant:
        relevant = tests_impact  # fallback

    boosts     = [t for t in relevant if t.direction == "boost"]
    suppresses = [t for t in relevant if t.direction == "suppress"]

    parts = []
    if boosts:
        # Групуємо по target_diagnosis — знаходимо діагноз з найбільшим сумарним delta
        from collections import defaultdict
        diag_boost: dict = defaultdict(list)
        for t in boosts:
            diag_boost[t.target_diagnosis].append(t)
        top_diag = max(diag_boost, key=lambda d: sum(t.delta for t in diag_boost[d]))
        top_tests = diag_boost[top_diag]
        test_names = " et ".join(t.test for t in top_tests[:2])
        parts.append(f"{test_names} renforcent le profil de {top_diag}")
    if suppresses:
        top = max(suppresses, key=lambda x: abs(x.delta))
        parts.append(f"{top.test} {top.result} réduit {top.target_diagnosis}")

    summary = ". ".join(parts) + "."
    if decision_before != decision_after:
        summary += f" Décision modifiée : {decision_before} → {decision_after}."
    return summary