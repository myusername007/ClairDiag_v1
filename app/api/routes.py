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

# ── FINAL FIX PACK imports ────────────────────────────────────────────────────
import re as _re

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

    # ── NLP Segmentation (БЛОК 1: ніколи не "Aucun résultat") ───────────────
    raw_text = " ".join(symptoms_clean)
    # Pour check_red_flags — utilise le texte brut original si disponible
    # (les chips parsées peuvent manquer des mots clés comme "jambe gonflée")
    _rf_text = request.raw_text or raw_text

    # ── TEXT-BASED RED FLAG — avant NLP, avant tout ──────────────────────────
    from app.pipeline.rfe import check_red_flags as _check_text_rf
    _text_rf = _check_text_rf(_rf_text)
    if _text_rf["triggered"]:
        from app.pipeline.orchestrator import _empty_response
        _rf_resp = _empty_response(_text_rf["reason"], urgency_level="élevé")
        _rf_resp.emergency_flag = True
        _rf_resp.emergency_reason = _text_rf["reason"]
        _rf_resp.decision = "EMERGENCY"
        return _rf_resp
    # ────────────────────────────────────────────────────────────────────────

    def _segment_text(text: str) -> list[str]:
        """Split input by natural separators into sub-phrases."""
        parts = _re.split(r"[,\.\n]|\bet\b|\bou\b", text, flags=_re.IGNORECASE)
        return [p.strip() for p in parts if p.strip() and len(p.strip()) > 2]

    # Нормалізуємо кожен сегмент окремо + весь текст цілком
    segments = _segment_text(raw_text)
    normalized: list[str] = []

    # 1. Спочатку весь текст
    whole = extract_symptoms(raw_text)
    normalized.extend(whole)

    def _normalize_segment(segment: str) -> list[str]:
        """
        Semantic fallback — спрацьовує тільки якщо extract_symptoms нічого не знайшов.
        Повертає ТІЛЬКИ ключі що є в SYMPTOM_DIAGNOSES (або через ALIASES).
        """
        s = segment.lower()
        mapped: list[str] = []
        # Digestif
        if any(x in s for x in ("mal ventre", "mal au ventre", "ventre", "côté droit", "côté gauche",
                                  "cote droit", "cote gauche", "abdomen", "abdomin")):
            mapped.append("douleur abdominale")
        if any(x in s for x in ("après manger", "apres manger", "après repas", "apres repas",
                                  "après avoir mangé", "petit repas", "chaque repas", "verre d'eau",
                                  "en mangeant")):
            mapped.append("après repas")
        if any(x in s for x in ("nuit", "nocturne", "allongé", "allongée")):
            mapped.append("symptomes nocturnes")
        if any(x in s for x in ("constip",)):
            mapped.append("constipation")
        if any(x in s for x in ("diarrhee", "diarrhée", "selles liquides")):
            mapped.append("diarrhée")
        if any(x in s for x in ("antibiotique", "antibio", "amoxicillin", "penicillin")):
            mapped.append("diarrhée")  # post-abx → diarrhée digestif signal
        if any(x in s for x in ("gargouil", "gargouillement", "bruits")):
            mapped.append("bruits intestinaux")
        if any(x in s for x in ("ballonnement", "gonflé", "gonflée", "ventre gonflé")):
            mapped.append("ballonnements")
        if any(x in s for x in ("nausee", "nausée", "envie de vomir", "mal au coeur")):
            mapped.append("nausées")
        if any(x in s for x in ("vomis", "vomissement", "j'ai vomi")):
            mapped.append("nausées")
        # Général — malaise retiré (trop vague)
        if any(x in s for x in ("fatigué", "fatigue", "épuisé", "epuise", "sans énergie",
                                  "pas d'énergie")):
            mapped.append("fatigue")
        # Respiratoire
        if any(x in s for x in ("respir", "souffle", "essouf", "manque d'air")):
            mapped.append("essoufflement")
        if any(x in s for x in ("touss", "je tousse")):
            mapped.append("toux")
        if any(x in s for x in ("fievre", "fièvre", "température", "temperature", "j'ai chaud")):
            mapped.append("fièvre")
        # Cardiaque
        if any(x in s for x in ("coeur", "cœur", "palpitat", "battement")):
            mapped.append("palpitations")
        if any(x in s for x in ("poitrine", "thorax", "thoracique")):
            mapped.append("douleur thoracique")
        # Tête
        if any(x in s for x in ("tête", "tete", "mal à la tête", "mal de tête", "crâne")):
            mapped.append("céphalées")
        if any(x in s for x in ("vertige", "tourne", "tête qui tourne")):
            mapped.append("vertiges")
        # Gorge
        if any(x in s for x in ("gorge", "avaler", "déglutition")):
            mapped.append("mal de gorge")
        return mapped

    # 2. Потім кожен сегмент — extract_symptoms, потім semantic fallback
    unrecognized_segments: list[str] = []
    for seg in segments:
        seg_result = extract_symptoms(seg)
        if seg_result:
            for s in seg_result:
                if s not in normalized:
                    normalized.append(s)
        else:
            # extract_symptoms нічого не знайшов → semantic fallback
            sem = _normalize_segment(seg)
            if sem:
                for s in sem:
                    if s not in normalized:
                        normalized.append(s)
            else:
                unrecognized_segments.append(seg)

    # Suggestions: прості варіанти для нерозпізнаних сегментів
    _SUGGESTIONS_MAP = {
        "nuit": "douleur nocturne",
        "noc": "douleur nocturne",
        "mang": "douleur après repas",
        "repas": "douleur après repas",
        "effort": "douleur à l'effort",
        "respir": "difficulté à respirer",
        "souf": "essoufflement",
        "cœur": "palpitations",
        "ventre": "douleur abdominale",
        "tête": "céphalée",
        "gorge": "mal de gorge",
        "dos": "douleur dorsale",
    }
    suggestions: list[str] = []
    for seg in unrecognized_segments:
        seg_lower = seg.lower()
        for trigger, suggestion in _SUGGESTIONS_MAP.items():
            if trigger in seg_lower and suggestion not in suggestions:
                suggestions.append(f"Voulez-vous dire : {suggestion} ?")
                break

    # ── Merge: оригінальні + нормалізовані ──────────────────────────────────
    if normalized:
        merged = list(dict.fromkeys(symptoms_clean + normalized))
        interpreted_symptoms = normalized
    else:
        merged = symptoms_clean
        interpreted_symptoms = []

    # ── CRITICAL FIX: фільтр nse.run() вбиває все що не в SYMPTOM_DIAGNOSES ──
    # Рішення: пропускаємо merged через parse_text (текстовий пошук, не точний ключ)
    # і залишаємо тільки те що pipeline прийме. Якщо нічого — fallback на raw_text.
    from app.pipeline.nse import parse_text as _parse_text
    from app.data.symptoms import ALIASES as _ALIASES, SYMPTOM_DIAGNOSES as _SD

    # Збираємо всі канонічні симптоми з merged через parse_text на об'єднаному тексті
    _combined_text = " ".join(merged)
    _pipeline_ready = _parse_text(_combined_text)

    # Якщо parse_text теж нічого не дав — спробуємо кожен токен через ALIASES
    if not _pipeline_ready:
        for tok in merged:
            tok_lower = tok.lower().strip()
            canon = _ALIASES.get(tok_lower, tok_lower)
            if canon in _SD:
                _pipeline_ready.append(canon)

    # Якщо ВСЕ одно порожньо — мінімальний guarantee щоб pipeline не падав
    if not _pipeline_ready and merged:
        # Шукаємо будь-який ключ з _SD що є підрядком в combined_text
        combined_lower = _combined_text.lower()
        for key in _SD:
            if key in combined_lower:
                _pipeline_ready.append(key)
                if len(_pipeline_ready) >= 3:
                    break

    # Логуємо для дебагу
    logger.info(f"NLP pipeline: raw={merged} → parse_text={_pipeline_ready}")

    # Замінюємо merged на те що pipeline реально прийме
    if _pipeline_ready:
        merged = list(dict.fromkeys(_pipeline_ready))

    # ── GUARANTEED FALLBACK: якщо після всіх шарів merged порожній ──────────
    # Запускаємо _normalize_segment на raw_text цілком як останній шанс
    if not merged and raw_text:
        _sem_full = _normalize_segment(raw_text)
        if _sem_full:
            # Резолвимо через ALIASES
            _resolved = []
            for s in _sem_full:
                canon = _ALIASES.get(s.lower(), s)
                if canon in _SD:
                    _resolved.append(canon)
                elif s in _SD:
                    _resolved.append(s)
            merged = list(dict.fromkeys(_resolved))
            logger.info(f"GUARANTEED FALLBACK: raw_text sem → {merged}")

    # ── LAST RESORT: хоч щось відправити щоб не "Aucun résultat" ────────────
    if not merged and raw_text:
        _last = _parse_text(raw_text)
        if _last:
            merged = _last
        else:
            # Абсолютний мінімум — digestif generic якщо є хоч слово про живіт/їжу
            _raw_lower = raw_text.lower()
            if any(x in _raw_lower for x in ("ventre", "repas", "manger", "digest",
                                               "constip", "diarrhée", "diarrhee")):
                merged = ["douleur abdominale"]
            elif any(x in _raw_lower for x in ("toux", "respir", "fièvre", "fievre")):
                merged = ["toux"]
            elif any(x in _raw_lower for x in ("coeur", "cœur", "poitrine")):
                merged = ["douleur thoracique"]
            else:
                merged = []
            logger.warning(f"LAST RESORT fallback: merged={merged}")

    # ── NLP Fallback (partial success) ──────────────────────────────────────
    # Vague-only guard
    _VAGUE_ONLY = frozenset({"malaise", "fatigue", "symptomes nocturnes"})
    if merged and all(s in _VAGUE_ONLY for s in merged):
        merged = []

    from app.models.schemas import NlpFallback
    _nlp_fallback = NlpFallback(
        understood=interpreted_symptoms or symptoms_clean,
        not_understood=unrecognized_segments,
        suggestions=suggestions[:3],
        partial_success=bool(interpreted_symptoms or symptoms_clean),
    )

    # low_confidence_input: нічого не знайшли взагалі — але все одно пробуємо
    if not merged:
        logger.warning(f"low_confidence_input: '{raw_text[:80]}'")
        from app.pipeline.orchestrator import _empty_response
        from app.models.schemas import DataQualityMessage
        resp = _empty_response(
            "Les informations fournies sont insuffisantes pour établir un diagnostic. "
            "Veuillez décrire vos symptômes plus précisément ou choisissez dans la liste.",
        )
        resp.nlp_fallback = _nlp_fallback
        resp.is_valid_output = False
        resp.decision = "LOW_RISK_MONITOR"
        resp.data_quality = DataQualityMessage(
            status="insufficient_data",
            message=(
                "Nous ne pouvons pas établir d'orientation fiable. "
                "Pour améliorer l'analyse, précisez : la localisation de la douleur, "
                "la durée, et les symptômes associés."
            ),
        )
        # Fix A: guide the user with concrete clarification questions
        resp.clarification_questions = {
            "show": True,
            "context": "Pour orienter le diagnostic, répondez à ces questions :",
            "questions": [
                "Où avez-vous mal exactement (poitrine, ventre, gorge, tête…) ?",
                "Depuis combien de temps (heures, jours) ?",
                "Intensité de la douleur/gêne de 0 à 10 ?",
                "Autres symptômes : fièvre, nausées, essoufflement, toux ?",
                "Contexte particulier : après un repas, effort physique, prise de médicament ?",
            ],
        }
        return resp

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

        # UX Confirmation — interpreted_symptoms: normalized + direct matches (merged)
        # Fix: direct keyword matches (toux, fièvre…) go to symptoms_clean, not normalized
        # → include merged so all recognized symptoms appear in "Symptômes interprétés"
        result.interpreted_symptoms = list(dict.fromkeys(
            (interpreted_symptoms or []) + [s for s in merged if s not in (interpreted_symptoms or [])]
        ))
        # БЛОК 1: NLP Fallback
        result.nlp_fallback = _nlp_fallback

        # ── Context Parser (патч п.4–5) ──────────────────────────────────────
        # Якщо фронт передав raw_text — використовуємо його для кращого context detection
        _ctx_source = getattr(request, "raw_text", None) or raw_text
        ctx = parse_context(_ctx_source)

        # ── Clinical fix: apply context boosts/penalties to diagnoses ────────
        if result.diagnoses and ctx.get("flags"):
            from app.pipeline.context_parser import apply_context_boosts
            from app.models.schemas import Diagnosis as _Diag

            # Беремо ВСІ probs — завжди запускаємо bpu для отримання повного списку
            if result.debug_trace and result.debug_trace.bpu.final_probs:
                _all_probs = dict(result.debug_trace.bpu.final_probs)
            else:
                # Перераховуємо probs через pipeline для отримання повного списку
                from app.pipeline import nse, scm, bpu, cre, tce
                _s1 = nse.run(list(merged))
                _s2 = scm.run(_s1)
                _all_probs, _ = bpu.run(_s2)
                _all_probs = cre.run(_all_probs, _s2)
                _all_probs = tce.run(
                    _all_probs,
                    onset=request.onset,
                    duration=request.duration,
                )

            _probs_ctx = apply_context_boosts(_all_probs, ctx)

            # Будуємо новий список з усіх probs >= threshold (same as orchestrator)
            _THRESHOLD = 0.15
            from app.models.schemas import Diagnosis as _Diag
            all_diags = [
                _Diag(name=name, probability=round(prob, 2), key_symptoms=[])
                for name, prob in _probs_ctx.items()
                if prob >= _THRESHOLD
            ]
            # Зберігаємо key_symptoms з оригінальних diagnoses
            _orig_keys = {d.name: d.key_symptoms for d in result.diagnoses}
            for d in all_diags:
                if d.name in _orig_keys:
                    d.key_symptoms = _orig_keys[d.name]
            # Пересортировуємо топ-3
            # Фільтруємо хронічні з penalty + minimum symptoms + сортуємо топ-3
            _CHRONIC_PENALIZED = {"SII", "Dyspepsie"}
            pre_filtered = [
                d for d in all_diags
                if not (d.name in _CHRONIC_PENALIZED and d.probability < 0.25)
            ]
            # Apply minimum symptoms guard BEFORE top-3 to avoid losing valid candidates
            from app.pipeline.orchestrator import filter_diagnoses as _filter_dx
            filtered = _filter_dx(pre_filtered, list(merged))
            sorted_diags = sorted(filtered, key=lambda d: d.probability, reverse=True)
            deduped = []
            for d in sorted_diags:
                if deduped and d.probability >= deduped[-1].probability:
                    d.probability = round(deduped[-1].probability - 0.04, 2)
                deduped.append(d)
                if len(deduped) == 3:
                    break
            # ── CARDIO GUARD v2.5 (context boost) ───────────────────────
            _CTX_CARDIO_CORE = frozenset({
                "essoufflement", "douleur thoracique", "palpitations",
                "syncope", "douleur thoracique intense", "dyspnée progressive",
            })
            _CTX_CARDIO_DIAGS = {"Insuffisance cardiaque", "Angor",
                                  "Infarctus du myocarde", "Embolie pulmonaire",
                                  "Trouble du rythme"}
            if not (set(merged) & _CTX_CARDIO_CORE):
                for _d in deduped:
                    if _d.name in _CTX_CARDIO_DIAGS and _d.probability > 0.35:
                        _d.probability = 0.35
            result.diagnoses = deduped

            # Rebuild decision_logic to reflect actual top-1 after context reranking
            if result.diagnoses:
                try:
                    from app.pipeline.orchestrator import _build_decision_logic as _bdl
                    _conf = (result.trust_score.overall if result.trust_score and hasattr(result.trust_score, "overall") else 0.36)
                    result.decision_logic = _bdl(
                        diagnoses=result.diagnoses,
                        confidence_score=_conf,
                        misdiagnosis_risk_score=result.misdiagnosis_risk_score or 0.0,
                        decision=result.decision,
                        urgency_level=result.urgency_level,
                        symptoms_compressed=list(merged),
                    )
                except Exception as _e:
                    logger.warning(f"decision_logic rebuild skipped: {_e}")

            # Sync diagnostic_path.main_hypothesis + differential.principal with actual ranked #1
            if result.diagnoses and result.diagnostic_path:
                _actual_top = result.diagnoses[0].name
                _path_top = result.diagnostic_path.get("main_hypothesis", "")
                if _path_top != _actual_top:
                    if _path_top:
                        result.diagnostic_path["_hypothesis_override_note"] = (
                            f"Override sécurité : {_path_top} → {_actual_top}"
                        )
                    result.diagnostic_path["main_hypothesis"] = _actual_top
            # differential.principal must equal diagnostic_path.main_hypothesis — same variable
            if result.diagnoses and isinstance(result.differential, dict) and result.differential.get("principal"):
                result.differential["principal"] = result.diagnoses[0].name
                result.differential["principal_probability"] = result.diagnoses[0].probability

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
            _build_economic_reasoning_v2,
            _build_severity_assessment,
            _build_triage_level,
            _build_diagnostic_status,
            _build_follow_up,
            _build_action_plan,
            _build_user_reassurance,
            _build_user_explanation,
            _build_kpi_metrics,
            _build_public_health,
            _build_differential_gap,
            _build_roi_projection,
            _build_system_impact,
            _build_confidence_explanation,
            _build_system_value,
            _map_severity_to_urgency,
            _build_final_decision,
            _build_ux_message,
            _sanitize_text_for_severity,
            _build_clinical_explanation_v3,
            _build_primary_action,
            _build_user_reassurance_v2,
            _build_why_consultation,
            _build_data_quality,
            _build_baseline_pathway,
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

            # ── ECONOMIC ENGINE V2: rebuild with FINAL tests + FINAL diagnoses ──
            result.economic_reasoning_v2 = _build_economic_reasoning_v2(
                tests_required=list(result.tests.required),
                tests_optional=list(result.tests.optional),
                diagnoses=result.diagnoses,
            )

            # ── БЛОК 2: BASELINE PATHWAY — реальна економія (не декоративна) ──
            result.baseline_pathway = _build_baseline_pathway(
                diagnoses=result.diagnoses,
                economic_v2=result.economic_reasoning_v2,
            )

            # sync economics — une seule source de vérité pour les économies
            # economic_reasoning_v2.pathway est la valeur finale (FINAL tests inclus)
            if result.economic_reasoning_v2 and result.economic_reasoning_v2.pathway:
                _pw = result.economic_reasoning_v2.pathway
                result.economics = {
                    **result.economics,
                    "standard_cost":  round(_pw.standard_cost, 2),
                    "optimized_cost": round(_pw.optimized_cost, 2),
                    "savings": round(_pw.savings, 2)
                        if not result.economic_reasoning_v2.savings_blocked else 0.0,
                    "savings_blocked": result.economic_reasoning_v2.savings_blocked,
                }

            # ── UX LAYER (п.1–10): severity-first flow ──────────────────────
            _syms_compressed = list(result.audit.normalized_symptoms) if result.audit else list(merged)

            # П.1: Severity engine
            result.severity_assessment = _build_severity_assessment(
                symptoms_compressed=_syms_compressed,
                context=ctx,
                raw_text=_ctx_source or "",
            )
            _sev = result.severity_assessment.level

            # RÈGLE DE SÉCURITÉ CRITIQUE: diagnostics à risque vital → severity=severe obligatoire
            _CARDIAC_EMERGENCY_DIAGS = {"Infarctus du myocarde", "Embolie pulmonaire"}
            _top3_diag_names = {d.name for d in result.diagnoses[:3]} if result.diagnoses else set()
            _is_cardiac_emergency = bool(_top3_diag_names & _CARDIAC_EMERGENCY_DIAGS)
            if _is_cardiac_emergency:
                result.severity_assessment.level = "severe"
                result.severity_assessment.drivers = ["Diagnostic à risque vital — urgence immédiate"]
                _sev = "severe"

            # П.2: Triage = severity only (П.10: anti-panic)
            result.triage = _build_triage_level(
                severity_level=_sev,
                emergency_flag=result.emergency_flag,
            )

            # П.3: Confidence ladder
            _conf_score = result.trust_score.model_confidence if result.trust_score else 0.49
            _misdiag = result.misdiagnosis_risk_score or 0.0
            result.diagnostic_status = _build_diagnostic_status(
                confidence_score=_conf_score,
                severity_level=_sev,
                misdiagnosis_risk_score=_misdiag,
            )

            # П.4: Follow-up engine
            result.follow_up = _build_follow_up(
                diagnoses=result.diagnoses,
                severity_level=_sev,
                urgency_level=result.urgency_level,
            )

            # П.5: Action plan (severity-aware)
            result.action_plan = _build_action_plan(
                diagnoses=result.diagnoses,
                severity_level=_sev,
                worsening_signs=result.worsening_signs,
                urgency_level=result.urgency_level,
            )

            # П.6: Reassurance layer (anti-panic: empty if severe)
            result.user_reassurance = _build_user_reassurance(
                diagnoses=result.diagnoses,
                severity_level=_sev,
            )

            # П.7: User explanation
            result.user_explanation = _build_user_explanation(
                diagnoses=result.diagnoses,
                symptoms_compressed=_syms_compressed,
                context=ctx,
            )

            # П.8: KPI metrics
            result.kpi_metrics = _build_kpi_metrics(
                economic_v2=result.economic_reasoning_v2,
            )

            # П.9: Public health mode
            result.public_health = _build_public_health(
                severity_level=_sev,
                economic_v2=result.economic_reasoning_v2,
                decision=result.decision,
            )

            # ── 3 NEW BLOCKS: differential gap, ROI, system impact ────────
            result.differential_gap = _build_differential_gap(
                diagnoses=result.diagnoses,
            )
            # П.1 integration: if low_separation → force referral_required
            if result.differential_gap.force_referral and result.diagnostic_status:
                result.diagnostic_status.status = "referral_required"

            result.roi_projection = _build_roi_projection(
                economic_v2=result.economic_reasoning_v2,
            )
            result.system_impact = _build_system_impact(
                severity_level=_sev,
                economic_v2=result.economic_reasoning_v2,
            )

            # UX: Confidence explanation (why not 100%)
            result.confidence_explanation = _build_confidence_explanation(
                confidence_score=_conf_score,
                severity_level=_sev,
                diagnoses=result.diagnoses,
                symptoms_count=len(_syms_compressed),
            )

            # UX: System value (even when savings == 0€)
            result.system_value = _build_system_value(
                economic_v2=result.economic_reasoning_v2,
                diagnoses=result.diagnoses,
                severity_level=_sev,
            )

            # ══════════════════════════════════════════════════════════════════
            # БЛОК 1: FINAL OVERRIDE — urgency = max(severity, rme)
            # severity дає мінімальний рівень, rme може підвищити до élevé
            # якщо URGENT diagnoses в differential (клінічно правильно)
            # ══════════════════════════════════════════════════════════════════
            _sev_urgency = _map_severity_to_urgency(_sev)
            _urgency_order = {"faible": 0, "modéré": 1, "élevé": 2}
            # Беремо максимум — severity не може понизити urgency від rme
            if _urgency_order.get(result.urgency_level, 0) > _urgency_order.get(_sev_urgency, 0):
                pass  # rme urgency вища — залишаємо
            else:
                result.urgency_level = _sev_urgency

            # БЛОК 3: FINAL DECISION Phase 1 — severity→action, gap→tests
            _diag_status_str = result.diagnostic_status.status if result.diagnostic_status else "orientation_probable"
            _threshold = result.diagnostic_status.threshold_required if result.diagnostic_status else 0.85
            _gap_val = result.differential_gap.value if result.differential_gap else 1.0
            _force_ref = result.differential_gap.force_referral if result.differential_gap else False
            _has_tests = bool(result.tests and result.tests.required)
            result.decision = _build_final_decision(
                severity=_sev,
                diagnostic_status_str=_diag_status_str,
                confidence_score=_conf_score,
                threshold=_threshold,
                gap_value=_gap_val,
                has_required_tests=_has_tests,
            )

            # БЛОК 4: UX Message Engine (decision-aware)
            result.ux_message = _build_ux_message(
                severity=_sev,
                gap_value=_gap_val,
                force_referral=_force_ref,
                decision=result.decision,
                urgency_level=result.urgency_level,
            )

            # БЛОК 5: SANITIZER — удаление запрещённых состояний для moderate/mild
            if _sev != "severe":
                # Sanitize explanation text
                result.explanation = _sanitize_text_for_severity(result.explanation, _sev)
                # Sanitize worsening_signs
                result.worsening_signs = [
                    _sanitize_text_for_severity(s, _sev) for s in result.worsening_signs
                ]
                # Sanitize diagnostic_path next_step
                if result.diagnostic_path and "next_best_step" in result.diagnostic_path:
                    result.diagnostic_path["next_best_step"] = _sanitize_text_for_severity(
                        result.diagnostic_path["next_best_step"], _sev
                    )

            # HARD RULE ASSERT: urgency >= severity (може бути вищим через rme)
            assert _urgency_order.get(result.urgency_level, 0) >= _urgency_order.get(_sev_urgency, 0), \
                f"URGENCY UNDERFLOW: {result.urgency_level} < {_sev_urgency}"
            # ══════════════════════════════════════════════════════════════════

            # ── EXPLAINABILITY V3 + UX CLEAN (new blocks) ────────────────────
            result.clinical_explanation_v3 = _build_clinical_explanation_v3(
                diagnoses=result.diagnoses,
                symptoms_compressed=_syms_compressed,
                context=ctx,
            )

            result.primary_action = _build_primary_action(
                decision=result.decision,
                severity=_sev,
                diagnoses=result.diagnoses,
                gap_value=_gap_val,
            )

            if _is_cardiac_emergency:
                from app.models.schemas import TriageLevel, PrimaryActionBlock
                result.triage = TriageLevel(
                    level="severe",
                    label_fr="Urgence vitale",
                    icon="🔴",
                    color="red",
                    description="Appelez le 15 (SAMU) immédiatement — ne conduisez pas vous-même.",
                )
                result.primary_action = PrimaryActionBlock(
                    action="Appelez le 15 (SAMU) immédiatement",
                    severity_label="Suspicion de syndrome coronarien aigu — urgence vitale possible",
                    reason="Ne restez pas seul. Ne conduisez pas vous-même. En attendant les secours : asseyez-vous, ne bougez plus, desserrez vos vêtements.",
                )
                result.decision = "EMERGENCY"
                result.urgency_level = "élevé"
                result.user_reassurance = None
                result.user_reassurance_v2 = None

            if not _is_cardiac_emergency:
                result.user_reassurance_v2 = _build_user_reassurance_v2(
                    diagnoses=result.diagnoses,
                    severity=_sev,
                    symptoms_compressed=_syms_compressed,
                    confidence_score=_conf_score,
                )

            result.why_consultation = _build_why_consultation(
                decision=result.decision,
                severity=_sev,
                gap_value=_gap_val,
            )

            result.data_quality = _build_data_quality(
                symptoms_count=len(_syms_compressed),
                confidence_score=_conf_score,
                diagnoses=result.diagnoses,
            )

            # Clarification questions — digestif profile + C.diff possible
            _DIGESTIF_PROFILE = {"Dysbiose", "Infection intestinale", "SII", "Gastrite", "RGO", "Dyspepsie", "Colite"}
            _diag_names = {d.name for d in result.diagnoses}
            _is_digestif = bool(_diag_names & _DIGESTIF_PROFILE)
            _has_cdiff = "Clostridioides difficile" in _diag_names
            if _is_digestif and _has_cdiff and _conf_score < 0.60:
                result.clarification_questions = {
                    "show": True,
                    "context": "Profil digestif post-antibiotiques — clarification nécessaire",
                    "questions": [
                        "Nombre de selles par jour ?",
                        "Présence de sang ou mucus dans les selles ?",
                        "Fièvre présente (> 38°C) ?",
                        "Signes de déshydratation (soif intense, vertiges) ?",
                    ],
                }

            # Fix B: C.diff clear single decision line (override ux_message)
            _cdiff_red_flags_present = False
            if result.do_not_miss_engine:
                _dnm = result.do_not_miss_engine
                _cdiff_red_flags_present = (
                    _dnm.cdiff_risk
                    and bool(_dnm.mandatory_tests)  # mandatory_tests only set when red flags present
                )
            if _is_digestif and _has_cdiff:
                from app.models.schemas import UxMessage, ActionPlan
                if _cdiff_red_flags_present:
                    result.ux_message = UxMessage(
                        headline="Consultation médicale recommandée",
                        detail="Signes d'alerte détectés — test C. difficile et examen clinique requis.",
                        gap_warning="",
                    )
                    result.action_plan = ActionPlan(
                        immediate=["Consultez votre médecin aujourd'hui ou rendez-vous aux urgences"],
                        within_24h=["Réalisez un test de toxines C. difficile (coproculture)"],
                        watch_for=["Aggravation des douleurs abdominales", "Chute tensionnelle ou confusion"],
                        self_care=["Hydratation abondante", "Évitez antidiarrhéiques sans avis médical"],
                    )
                else:
                    result.ux_message = UxMessage(
                        headline="Surveillance à domicile 48–72h",
                        detail="Pas de signe d'alerte immédiat. Consultez si : ≥ 3 selles/jour, fièvre, sang dans les selles ou déshydratation.",
                        gap_warning="",
                    )
                    result.action_plan = ActionPlan(
                        immediate=["Repos et hydratation", "Notez le nombre de selles et leur aspect"],
                        within_24h=["Consultez si : ≥ 3 selles/jour, fièvre > 38°C, sang dans les selles ou déshydratation"],
                        watch_for=["≥ 3 selles liquides par jour", "Sang ou mucus dans les selles", "Fièvre > 38°C", "Déshydratation (soif intense, vertiges)"],
                        self_care=["Probiotiques (Saccharomyces boulardii)", "Alimentation légère", "Hydratation abondante"],
                    )

            # Fix D: preliminary_evaluation flag when confidence < 50%
            if _conf_score < 0.50 and result.diagnoses:
                result.preliminary_evaluation = True
                # ── LOW CONFIDENCE TEST FILTER v3.1 ─────────────────────────
                # confidence < 0.50:
                #   sans pattern clinique → pas de tests, MEDICAL_REVIEW
                #   avec pattern clinique (oedème/rétention) → tests permis, ton doux
                _CLINICAL_PATTERN = {
                    "gonflement jambes", "prise de poids rapide",
                    "œdème périphérique", "rétention hydrique", "œdèmes",
                }
                _has_clinical_pattern = bool(set(merged) & _CLINICAL_PATTERN)
                _HEAVY_TESTS = {"BNP", "ECG", "Troponine", "D-dimères",
                                 "Échocardiographie", "Scanner thoracique",
                                 "Radiographie pulmonaire", "Holter ECG"}
                if not _has_clinical_pattern:
                    # Pas de pattern → pas de heavy tests
                    if result.tests:
                        _light = [t for t in result.tests.required if t not in _HEAVY_TESTS]
                        _demoted = [t for t in result.tests.required if t in _HEAVY_TESTS]
                        result.tests = result.tests.__class__(
                            required=_light,
                            optional=list(result.tests.optional) + _demoted,
                        )
                    if not (result.tests and result.tests.required):
                        result.decision = "MEDICAL_REVIEW"
                # Pattern présent → tests permis mais ton doux obligatoire
                if _has_clinical_pattern and result.ux_message:
                    if hasattr(result.ux_message, 'detail') and result.ux_message.detail:
                        _d = result.ux_message.detail
                        _d = _d.replace("analyses nécessaires", "peut être envisagé si persistance")
                        _d = _d.replace("analyses essentielles", "peut être envisagé si persistance")
                        _d = _d.replace("diagnostic probable", "orientation possible")
                        result.ux_message.detail = _d

            # Fix D: when_to_consult_immediately — profile-specific red flag list
            _top_diag_names = [d.name for d in result.diagnoses[:3]]
            _CARDIAC_ACUTE_DIAGS = {"Infarctus du myocarde", "Embolie pulmonaire", "Angor", "Trouble du rythme"}
            _CARDIAC_CHRONIC_DIAGS = {"Insuffisance cardiaque"}
            _RESP_DIAGS = {"Pneumonie", "Bronchite", "Grippe", "Asthme"}
            _top_set = set(_top_diag_names)
            _is_cardiac_acute = bool(_top_set & _CARDIAC_ACUTE_DIAGS)
            _is_cardiac_chronic = bool(_top_set & _CARDIAC_CHRONIC_DIAGS) and not _is_cardiac_acute
            _is_resp_profile = bool(_top_set & _RESP_DIAGS)
            _is_cardiac_profile = _is_cardiac_acute
            if result.urgency_level in ("élevé", "modéré"):
                if _is_digestif and not _is_cardiac_acute:
                    result.when_to_consult_immediately = [
                        "≥ 3 selles liquides par jour",
                        "Sang ou mucus dans les selles",
                        "Fièvre > 38°C",
                        "Signes de déshydratation (soif intense, vertiges, bouche sèche)",
                        "Douleurs abdominales intenses",
                    ]
                elif _is_resp_profile and not _is_cardiac_acute:
                    result.when_to_consult_immediately = [
                        "Essoufflement ou difficulté à respirer",
                        "Fièvre > 39°C persistante ou > 5 jours",
                        "Douleur thoracique",
                        "Confusion ou somnolence inhabituelle",
                        "Lèvres ou ongles bleutés (cyanose)",
                    ]
                elif _is_cardiac_chronic:
                    result.when_to_consult_immediately = [
                        "Essoufflement brutal au repos ou la nuit",
                        "Prise de poids rapide (> 2 kg en 2–3 jours)",
                        "Œdèmes des jambes qui s aggravent",
                        "Fatigue intense avec incapacité à faire les activités habituelles",
                    ]
                elif _is_cardiac_acute:
                    result.when_to_consult_immediately = [
                        "Douleur thoracique intense ou irradiant dans le bras",
                        "Essoufflement brutal au repos",
                        "Palpitations avec malaise ou syncope",
                        "Confusion ou perte de connaissance",
                    ]

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
            # symptoms_clean = оригінальний ввід юзера (до NLP merge)
            # Якщо юзер ввів 1 симптом і впевненість висока — недостатньо даних
            single_symptom_high_conf = (
                len(symptoms_clean) <= 1
                and result.diagnoses
                and result.diagnoses[0].probability >= 0.55
            )

            if not (has_reasoning and has_test_logic and has_do_not_miss and has_context_link):
                result.is_valid_output = False
            if single_symptom_high_conf:
                result.is_valid_output = False
                if result.edge_case_analysis:
                    result.edge_case_analysis.manual_review_recommended = True
                    result.edge_case_analysis.fallback_reason = (
                        "Symptôme unique — données insuffisantes pour résultat valide"
                    )

        # п.8 gate: diagnoses порожній при непорожньому вводі → invalid
        if not result.diagnoses and symptoms_clean:
            result.is_valid_output = False
            result.decision = "LOW_RISK_MONITOR"
            from app.models.schemas import DataQualityMessage
            result.data_quality = DataQualityMessage(
                status="insufficient_data",
                message=(
                    "Nous ne pouvons pas établir d'orientation fiable. "
                    "Pour améliorer l'analyse, précisez : la localisation de la douleur, "
                    "la durée, et les symptômes associés."
                ),
            )

        # résoudre contradiction top1 — un seul diagnostic principal
        if result.diagnoses:
            from app.pipeline.orchestrator import resolve_primary_diagnosis
            # safety_diagnosis: si do_not_miss_engine signale urgence → priorité
            _safety = None
            if (result.do_not_miss_engine and result.do_not_miss_engine.ecg_required
                    and result.urgency_level == "élevé"):
                _dnm = result.do_not_miss_engine
                _top_dangerous = next(
                    (n for n in ["Infarctus du myocarde", "Embolie pulmonaire", "Angor"]
                     if any(n in f for f in (_dnm.flags or []))),
                    None,
                )
                if _top_dangerous:
                    _safety = {"name": _top_dangerous, "urgency": "EMERGENCY"}
            result.primary_diagnosis = resolve_primary_diagnosis(result.diagnoses, _safety)

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

        # ── HARD SINGLE PATH RULE v3.0 ───────────────────────────────────────────
        # faible urgency → ТІЛЬКИ surveillance, видалити tests
        # є tests → видалити surveillance повністю
        if result.urgency_level == "faible":
            result.decision = "LOW_RISK_MONITOR"
            result.tests = result.tests.__class__(
                required=[],
                optional=list(result.tests.optional) + list(result.tests.required),
            ) if result.tests else result.tests
            if result.action_plan and result.action_plan.immediate:
                result.action_plan.immediate = [
                    m for m in result.action_plan.immediate
                    if "analyses" not in m.lower() and "examens" not in m.lower()
                    and "rendez-vous" not in m.lower()
                ] or ["Surveillez vos symptômes à domicile pendant 48–72h"]
        elif result.tests and result.tests.required:
            if result.action_plan and result.action_plan.immediate:
                result.action_plan.immediate = [
                    m for m in result.action_plan.immediate
                    if "surveillance" not in m.lower()
                    and "48h" not in m.lower()
                    and "72h" not in m.lower()
                ] or ["Consultez votre médecin et réalisez les analyses prescrites"]


        # ── UX MESSAGE REBUILD v2.5 ─────────────────────────────────────────
        try:
            from app.pipeline.orchestrator import _build_ux_message as _bum
            if result.decision in ("TESTS_REQUIRED", "MEDICAL_REVIEW", "TESTS_FIRST"):
                result.ux_message = _bum(
                    severity=_sev,
                    gap_value=_gap_val,
                    force_referral=_force_ref,
                    decision=result.decision,
                    urgency_level=result.urgency_level,
                )
            elif result.decision == "LOW_RISK_MONITOR":
                result.ux_message = _bum(
                    severity="mild",
                    gap_value=_gap_val,
                    force_referral=False,
                    decision="LOW_RISK_MONITOR",
                    urgency_level="faible",
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


# ══════════════════════════════════════════════════════════════════════════════
# MODULE: "J'ai déjà des analyses" — import + interpret test results
# ══════════════════════════════════════════════════════════════════════════════

from app.models.schemas import (
    ImportTestsRequest, ImportTestsResponse, ParsedTestResult,
    AnalyzeWithTestsRequest, AnalyzeWithTestsResponse, TestInfluence,
)


@router.post("/import-tests", response_model=ImportTestsResponse)
def import_tests(request: ImportTestsRequest) -> ImportTestsResponse:
    """
    Parse test results from text, PDF, or image.
    Returns structured data for user confirmation before analysis.
    """
    from app.pipeline.test_parser import parse_test_text, parse_test_pdf, parse_test_image
    import base64

    parsed: list[dict] = []
    method = "text"

    # 1. Text input (primary)
    if request.text:
        parsed = parse_test_text(request.text)
        method = "text"

    # 2. File input (PDF or image)
    elif request.file_base64 and request.file_type:
        try:
            file_bytes = base64.b64decode(request.file_base64)
        except Exception:
            return ImportTestsResponse(
                confirmation_message="Erreur : fichier invalide. Veuillez réessayer.",
            )

        if request.file_type == "pdf":
            parsed = parse_test_pdf(file_bytes)
            method = "pdf"
        elif request.file_type in ("image", "jpg", "jpeg", "png", "heic"):
            parsed = parse_test_image(file_bytes)
            method = "image"

    if not parsed:
        return ImportTestsResponse(
            confirmation_message="Aucun résultat d'analyse reconnu. "
                "Essayez de coller le texte directement ou vérifiez le format du fichier.",
            parse_method=method,
        )

    # Convert to Pydantic models
    results = [
        ParsedTestResult(
            raw_name=p.get("raw_name", ""),
            canonical_name=p.get("canonical_name"),
            value=p.get("value"),
            raw_value=p.get("raw_value", ""),
            unit=p.get("unit", ""),
            status=p.get("status", "inconnu"),
            recognized=p.get("recognized", False),
        )
        for p in parsed
    ]

    recognized = sum(1 for r in results if r.recognized)
    unrecognized = len(results) - recognized

    msg = f"{recognized} analyse(s) reconnue(s)"
    if unrecognized:
        msg += f", {unrecognized} non reconnue(s)"
    msg += ". Vérifiez et confirmez avant l'analyse."

    logger.info(f"ImportTests [{method}]: {recognized} recognized, {unrecognized} unrecognized")

    return ImportTestsResponse(
        results=results,
        recognized_count=recognized,
        unrecognized_count=unrecognized,
        confirmation_message=msg,
        ready_to_analyze=recognized > 0,
        parse_method=method,
    )


@router.post("/analyze-with-tests", response_model=AnalyzeWithTestsResponse)
def analyze_with_tests(request: AnalyzeWithTestsRequest) -> AnalyzeWithTestsResponse:
    """
    Analyze confirmed test results.
    If session_id provided: revaluate existing analysis with test results.
    If symptoms provided: run full analysis first, then apply test results.
    """
    from app.pipeline.test_parser import to_erl_format

    # Convert confirmed results to ERL format
    erl_data = to_erl_format([r.dict() for r in request.confirmed_results])

    if not erl_data:
        return AnalyzeWithTestsResponse(
            changes_summary="Aucun résultat exploitable pour l'analyse.",
        )

    # ── PATH A: revaluate existing session ──────────────────────────────────
    if request.session_id:
        session = session_store.get(request.session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail="Session introuvable ou expirée (TTL 30 min). Relancez l'analyse des symptômes d'abord."
            )
        return _run_test_analysis(session, erl_data, request)

    # ── PATH B: fresh analysis with symptoms + tests ────────────────────────
    if request.symptoms:
        from app.pipeline.nlp_normalizer import extract_symptoms
        raw_text = " ".join(request.symptoms)
        normalized = extract_symptoms(raw_text)
        merged = list(dict.fromkeys(list(request.symptoms) + normalized))

        result = pipeline_module.run(
            AnalyzeRequest(
                symptoms=merged,
                onset=request.onset,
                duration=request.duration,
            )
        )

        if not result.diagnoses:
            return AnalyzeWithTestsResponse(
                changes_summary="Aucun diagnostic identifié à partir des symptômes fournis.",
            )

        # Create session from fresh analysis
        from app.pipeline import nse, scm, bpu, cre, tce
        s1 = nse.run(merged)
        s2 = scm.run(s1)
        probs_raw, _ = bpu.run(s2)
        probs_cre = cre.run(probs_raw, s2)
        probs_tce = tce.run(probs_cre, onset=request.onset, duration=request.duration)
        session_id = session_store.create(probs_tce, s2)
        session = session_store.get(session_id)

        return _run_test_analysis(session, erl_data, request)

    # ── PATH C: tests only (no symptoms, no session) ────────────────────────
    # Build a minimal response from test results alone
    influences = _build_test_influences_standalone(request.confirmed_results)
    return AnalyzeWithTestsResponse(
        test_influences=influences,
        changes_summary="Résultats d'analyses interprétés sans contexte symptomatique. "
            "Pour une analyse complète, décrivez vos symptômes.",
    )


def _run_test_analysis(
    session: dict,
    erl_data: dict[str, str],
    request: AnalyzeWithTestsRequest,
) -> AnalyzeWithTestsResponse:
    """Run ERL revaluation and build rich response."""
    probs_before = session["probs"]
    symptoms = session["symptoms"]

    # Snapshot before
    diagnoses_before = [
        Diagnosis(name=n, probability=round(p, 2))
        for n, p in sorted(probs_before.items(), key=lambda x: -x[1])[:3]
        if p >= 0.15
    ]

    # Decision before
    tcs_before, conf_before, _ = tcs_run(probs_before, len(symptoms), symptoms=symptoms)
    urgency_before = rme_run(probs_before)
    misdiag_before = _compute_misdiagnosis_risk_simple(probs_before, len(symptoms))
    decision_before = _build_decision(
        emergency=False,
        urgency_level=urgency_before,
        misdiagnosis_risk=misdiag_before,
        tcs_level=tcs_before,
    )

    # ERL revaluation
    probs_after, changes_log = erl.run(probs_before, erl_data)

    # Levels after
    tcs_after, confidence_level, _ = tcs_run(probs_after, len(symptoms), symptoms=symptoms)
    urgency_after = rme_run(probs_after)
    confidence_final, sgl_warnings = sgl_run(
        diagnoses_names=[n for n, _ in sorted(probs_after.items(), key=lambda x: -x[1])[:3]],
        probs=probs_after,
        symptom_count=len(symptoms),
        confidence_level=confidence_level,
    )

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

    # Tests impact
    tests_impact = _build_tests_impact(probs_before, probs_after, erl_data, diagnoses_after)

    # Build test influences for UX
    influences = _build_test_influences(
        tests_impact=tests_impact,
        confirmed_results=request.confirmed_results,
        diagnoses_before=diagnoses_before,
        diagnoses_after=diagnoses_after,
    )

    # Key test = highest impact
    key_test = ""
    if tests_impact:
        key = max(tests_impact, key=lambda t: abs(t.delta))
        key_test = f"{key.test} ({key.result})"

    # Confirmed / excluded
    before_names = {d.name for d in diagnoses_before}
    after_names = {d.name for d in diagnoses_after}
    confirmed = []
    excluded = []
    for d in diagnoses_after:
        if d.name in before_names:
            old_p = next((db.probability for db in diagnoses_before if db.name == d.name), 0)
            if d.probability > old_p + 0.05:
                confirmed.append(d.name)
    for d in diagnoses_before:
        if d.name not in after_names:
            excluded.append(d.name)

    changes_summary = _build_changes_summary(diagnoses_before, diagnoses_after, changes_log)
    reasoning_summary = _build_reasoning_summary(
        tests_impact, decision_before, decision_after, diagnoses_after
    )

    # ── Phase 2 FINAL DECISION (after tests) ──────────────────────────────
    from app.pipeline.orchestrator import _build_final_decision_phase2
    # Confidence score after tests
    _conf_after = 0.5
    if diagnoses_after:
        top_prob = diagnoses_after[0].probability
        _conf_after = min(top_prob + 0.1, 0.95) if len(tests_impact) > 0 else top_prob
    # Gap after tests
    _gap_after = 1.0
    if len(diagnoses_after) >= 2:
        _gap_after = round(diagnoses_after[0].probability - diagnoses_after[1].probability, 3)
    _final_threshold = 0.75  # lower than phase 1 — tests provide additional evidence
    final_dec, action_label = _build_final_decision_phase2(
        severity="moderate",  # tests don't change severity (ТЗ п.9)
        confidence_score=_conf_after,
        final_threshold=_final_threshold,
        gap_value=_gap_after,
    )

    # ── Economics recalc (п.10) ──────────────────────────────────────────
    tests_performed = len(erl_data)
    tests_originally_required = len(session.get("symptoms", [])) + 2  # rough estimate
    tests_avoided = max(0, tests_originally_required - tests_performed)
    savings = round(tests_avoided * 25.0, 2)  # avg €25/test

    logger.info(
        f"AnalyzeWithTests: {len(erl_data)} tests → "
        f"decision {decision_before}→{final_dec}, "
        f"confirmed={confirmed}, excluded={excluded}"
    )

    return AnalyzeWithTestsResponse(
        phase="phase_2",
        test_influences=influences,
        diagnoses_before=diagnoses_before,
        diagnoses_after=diagnoses_after,
        decision_before=decision_before,
        decision_after=decision_after,
        final_decision=final_dec,
        confidence_before=conf_before,
        confidence_after=confidence_final,
        key_test=key_test,
        confirmed_diagnoses=confirmed,
        excluded_diagnoses=excluded,
        changes_summary=changes_summary,
        reasoning_summary=reasoning_summary,
        action_label=action_label,
        savings_after_tests=savings,
        tests_avoided_after=tests_avoided,
        tests_impact=tests_impact,
        changes_log=changes_log,
        urgency_level=urgency_after,
        sgl_warnings=sgl_warnings,
    )


def _build_test_influences(
    tests_impact: list[TestImpact],
    confirmed_results: list,
    diagnoses_before: list[Diagnosis],
    diagnoses_after: list[Diagnosis],
) -> list[TestInfluence]:
    """Build UX-friendly test influence list."""
    influences = []
    after_names = {d.name for d in diagnoses_after}

    for ti in tests_impact:
        if ti.direction == "boost":
            effect = "renforce"
            icon = "✔"
        else:
            effect = "affaiblit"
            icon = "✖"

        # Check if diagnosis was excluded
        if ti.target_diagnosis not in after_names:
            effect = "exclut"

        # Check if strongly confirmed
        if ti.direction == "boost" and ti.delta > 0.15:
            effect = "confirme"

        influences.append(TestInfluence(
            test=ti.test,
            result=ti.result,
            effect=effect,
            target=ti.target_diagnosis,
            detail=ti.reason,
        ))

    return influences


def _build_test_influences_standalone(
    confirmed_results: list,
) -> list[TestInfluence]:
    """Build basic influences when no symptom context available."""
    influences = []
    for r in confirmed_results:
        r_dict = r.dict() if hasattr(r, 'dict') else r
        canonical = r_dict.get("canonical_name", "")
        status = r_dict.get("status", "inconnu")
        if not canonical or status == "inconnu":
            continue

        if status in ("élevé", "positif"):
            effect = "renforce"
            detail = f"{canonical} {status} — valeur anormale détectée"
        elif status in ("bas",):
            effect = "affaiblit"
            detail = f"{canonical} bas — valeur en dessous de la norme"
        else:
            effect = "normal"
            detail = f"{canonical} dans les normes"

        influences.append(TestInfluence(
            test=canonical,
            result=r_dict.get("raw_value", status),
            effect=effect,
            target="(analyse sans symptômes)",
            detail=detail,
        ))

    return influences


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