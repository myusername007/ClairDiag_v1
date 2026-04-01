# ── Pipeline orchestrator — CORE v2 ─────────────────────────────────────────
# Exécute les 10 étapes dans l'ordre strict défini par le ТЗ.
# Ne contient aucune logique métier — uniquement l'orchestration.
#
# Ordre obligatoire (NE PAS MODIFIER) :
#   1. NSE — parser
#   2. SCM — compression
#   3. RFE — red flags  ← priorité absolue, avant scoring
#   4. BPU — scoring probabiliste
#   5. RME — risk module
#   6. TCE — temporal logic
#   7. CRE — règles médicales
#   8. TCS — thresholds
#   9. LME — sélection des tests
#  10. SGL — safety layer

import logging

from app.pipeline import nse, scm, rfe, bpu, rme, tce, cre, tcs, lme, sgl
from app.data.symptoms import DIAG_ARTICLE, URGENT_DIAGNOSES
from app.data.tests import TEST_EXPLANATIONS, CONSULTATION_COST
from app.models.schemas import (
    AnalyzeRequest, AnalyzeResponse, Diagnosis, Tests, Cost, Comparison,
    DebugTrace, DebugBPU, DebugCRE, DebugTCE, DebugTCS,
)

logger = logging.getLogger("clairdiag.pipeline")

_MAX_PROB: float = 0.90
PROBABILITY_THRESHOLD: float = 0.15


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_diagnosis_list(probs: dict[str, float], symptom_set: set[str]) -> list[Diagnosis]:
    """
    Construit la liste triée des diagnostics depuis les probabilités BPU/TCE/CRE.
    Garantit des probabilités distinctes (évite les ex-aequo à l'affichage).
    Limite à 3 diagnostics.
    """
    from app.data.symptoms import SYMPTOM_DIAGNOSES

    # Symptômes clés par diagnostic
    key_symptoms_map: dict[str, list[str]] = {name: [] for name in probs}
    for sym in symptom_set:
        for diag in SYMPTOM_DIAGNOSES.get(sym, {}):
            if diag in key_symptoms_map and sym not in key_symptoms_map[diag]:
                key_symptoms_map[diag].append(sym)

    diagnoses = sorted(
        [
            Diagnosis(
                name=name,
                probability=round(prob, 2),
                key_symptoms=key_symptoms_map.get(name, []),
            )
            for name, prob in probs.items()
            if prob >= PROBABILITY_THRESHOLD
        ],
        key=lambda d: d.probability,
        reverse=True,
    )[:3]

    # Dédoublonnage des probabilités identiques
    deduped: list[Diagnosis] = []
    for d in diagnoses:
        if deduped and (deduped[-1].probability - d.probability) < 0.04:
            prob = round(deduped[-1].probability - 0.04, 2)
        else:
            prob = d.probability
        deduped.append(
            Diagnosis(name=d.name, probability=max(prob, 0.10), key_symptoms=d.key_symptoms)
        )
    return deduped


def _build_explanation(symptoms: list[str], diagnoses: list[Diagnosis], required_tests: list[str]) -> str:
    """Génère l'explication en langue simple."""
    if not diagnoses:
        return (
            "Les symptômes fournis ne permettent pas d'établir un diagnostic. "
            "Veuillez consulter un médecin."
        )

    top = diagnoses[0]
    pct = int(top.probability * 100)
    art = DIAG_ARTICLE.get(top.name, "une")

    if pct >= 65:
        start = f"Les symptômes correspondent le plus probablement à {art} {top.name}."
    elif pct >= 40:
        start = f"Le diagnostic le plus probable est {art} {top.name}."
    else:
        start = (
            f"{art.capitalize()} {top.name} est possible, "
            "mais les symptômes restent insuffisants pour confirmer."
        )

    alt = ""
    if len(diagnoses) > 1:
        art2 = DIAG_ARTICLE.get(diagnoses[1].name, "une")
        alt = f" {art2.capitalize()} {diagnoses[1].name} ne peut pas être totalement exclue."

    tests_hint = ""
    first_two = [t for t in required_tests[:2] if t in TEST_EXPLANATIONS]
    if first_two:
        joined = " et ".join(
            f"{t} ({TEST_EXPLANATIONS[t]})" for t in first_two
        )
        tests_hint = f" Pour une première évaluation : {joined}."

    return start + alt + tests_hint


def _empty_response(reason: str) -> AnalyzeResponse:
    empty_comparison = Comparison(
        standard_tests=[], standard_cost=0,
        optimized_tests=[], optimized_cost=0,
        savings=0, savings_multiplier="—",
    )
    return AnalyzeResponse(
        diagnoses=[],
        tests=Tests(required=[], optional=[]),
        cost=Cost(required=0, optional=0, savings=0),
        explanation=reason,
        comparison=empty_comparison,
        urgency_level="faible",
        tcs_level="incertain",
        consultation_cost=CONSULTATION_COST,
    )


# ── Pipeline principal ────────────────────────────────────────────────────────

def run(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Exécute le pipeline CORE v2 complet dans l'ordre strict.
    """
    _debug = request.debug
    trace = DebugTrace() if _debug else None

    # ── Étape 1 : NSE ─────────────────────────────────────────────────────────
    symptoms_canonical = nse.run(request.symptoms)
    logger.debug(f"NSE → {symptoms_canonical}")
    if _debug: trace.symptoms_after_parser = list(symptoms_canonical)

    # ── Étape 2 : SCM ─────────────────────────────────────────────────────────
    symptoms_compressed = scm.run(symptoms_canonical)
    logger.debug(f"SCM → {symptoms_compressed}")
    if _debug: trace.symptoms_after_scm = list(symptoms_compressed)

    # ── Étape 3 : RFE ─────────────────────────────────────────────────────────
    rfe_result = rfe.run(symptoms_compressed)
    if _debug:
        trace.red_flags_detected = [rfe_result.reason] if rfe_result.emergency else []
        trace.emergency = rfe_result.emergency
    if rfe_result.emergency:
        logger.warning(f"RFE EMERGENCY → {rfe_result.reason}")
        resp = _empty_response(
            f"URGENCE MÉDICALE : {rfe_result.reason} "
            "Arrêtez cette application et appelez le 15 (SAMU) ou le 112."
        )
        resp.emergency_flag = True
        resp.emergency_reason = rfe_result.reason
        resp.urgency_level = "élevé"
        resp.tcs_level = "incertain"
        if _debug: resp.debug_trace = trace
        return resp

    # ── Étape 4 : BPU ─────────────────────────────────────────────────────────
    probs, incoherence_score = bpu.run(symptoms_compressed)
    logger.debug(f"BPU → probs={len(probs)}, incoherence={incoherence_score:.3f}")
    logger.debug(f"BPU → {probs}")

    if _debug:
        # Reconstruire les détails BPU pour la trace
        from app.data.symptoms import SYMPTOM_DIAGNOSES, COMBO_BONUSES, SYMPTOM_EXCLUSIONS
        ss = set(symptoms_compressed)
        _combos = [
            f"{'+'.join(sorted(combo))} → {diag} +{bonus}"
            for combo, bonuses in COMBO_BONUSES
            for diag, bonus in bonuses.items()
            if combo.issubset(ss) and diag in probs
        ]
        _penalties = [
            f"{sym} → {diag} -{penalty}"
            for sym in ss
            for diag, penalty in SYMPTOM_EXCLUSIONS.get(sym, {}).items()
            if diag in probs
        ]
        trace.bpu = DebugBPU(
            combo_bonuses_applied=_combos,
            penalties_applied=_penalties,
            incoherence_score=round(incoherence_score, 3),
            final_probs={k: round(v, 3) for k, v in sorted(probs.items(), key=lambda x: -x[1])},
        )

    if not probs:
        resp = _empty_response(
            "Les symptômes indiqués ne permettent pas d'identifier un diagnostic. "
            "Veuillez consulter un médecin."
        )
        if _debug: resp.debug_trace = trace
        return resp

    # ── Étape 5 : RME ─────────────────────────────────────────────────────────
    urgency_level = rme.run(probs)
    logger.debug(f"RME → urgency={urgency_level}")

    # ── Étape 6 : TCE ─────────────────────────────────────────────────────────
    probs_before_tce = dict(probs)
    probs = tce.run(probs, onset=request.onset, duration=request.duration)
    logger.debug(f"TCE → {probs}")
    if _debug:
        _tce_boosts, _tce_pens = [], []
        for d, v_after in probs.items():
            v_before = probs_before_tce.get(d, 0)
            diff = round(v_after - v_before, 3)
            if diff > 0:   _tce_boosts.append(f"{d} +{diff}")
            elif diff < 0: _tce_pens.append(f"{d} {diff}")
        trace.tce = DebugTCE(
            onset=request.onset,
            duration=request.duration,
            boosts_applied=_tce_boosts,
            penalties_applied=_tce_pens,
            probs_before={k: round(v, 3) for k, v in sorted(probs_before_tce.items(), key=lambda x: -x[1])},
            probs_after={k: round(v, 3) for k, v in sorted(probs.items(), key=lambda x: -x[1])},
        )

    # ── Étape 7 : CRE ─────────────────────────────────────────────────────────
    probs_before_cre = dict(probs)
    probs = cre.run(probs, symptoms_compressed)
    logger.debug(f"CRE → {probs}")
    if _debug:
        from app.pipeline.cre import _RULES
        ss = set(symptoms_compressed)
        _rules_applied = [
            f"{'+'.join(sorted(req))}{'(excl:'+','.join(sorted(excl))+')' if excl else ''} → {diag} {delta:+.2f}"
            for req, excl, diag, delta in _RULES
            if diag in probs_before_cre
            and req.issubset(ss)
            and not excl.intersection(ss)
        ]
        trace.cre = DebugCRE(
            rules_applied=_rules_applied,
            probs_before={k: round(v, 3) for k, v in sorted(probs_before_cre.items(), key=lambda x: -x[1])},
            probs_after={k: round(v, 3) for k, v in sorted(probs.items(), key=lambda x: -x[1])},
        )

    # ── Étape 8 : TCS ─────────────────────────────────────────────────────────
    probs_before_tcs = dict(probs)
    tcs_level, confidence_level, confidence_score = tcs.run(
        probs, len(symptoms_compressed),
        symptoms=symptoms_compressed,
        incoherence_score=incoherence_score,
    )
    logger.debug(f"TCS → tcs={tcs_level}, confidence={confidence_level}, score={confidence_score}")
    if _debug:
        from app.pipeline.tcs import _compute_confidence, _LOW_DATA_THRESHOLD
        from app.data.symptoms import SYMPTOM_DIAGNOSES as _SD
        _syms = symptoms_compressed
        _sp = sorted(probs_before_tcs.values(), reverse=True)
        _top_diag = max(probs_before_tcs, key=probs_before_tcs.get) if probs_before_tcs else ""
        _diag_syms = set(_SD.get(_top_diag, {}).keys())
        _ss = set(_syms)
        _cov = len(_ss & _diag_syms) / len(_ss) if _ss else 0.0
        _gap = (_sp[0] - _sp[1]) if len(_sp) >= 2 else 1.0
        _coh = min(_gap / 0.30, 1.0)
        _qual = min(len(_syms) / 4.0, 1.0)
        _raw = 0.40 * _cov + 0.35 * _coh + 0.25 * _qual
        _pen = incoherence_score * 0.08
        trace.tcs = DebugTCS(
            coverage=round(_cov, 3),
            coherence=round(_coh, 3),
            quality=round(_qual, 3),
            raw_score=round(_raw, 3),
            incoherence_penalty=round(_pen, 3),
            final_score=round(confidence_score, 3),
            low_data_cap_applied=(len(_syms) <= _LOW_DATA_THRESHOLD),
            confidence_level=confidence_level,
            tcs_level=tcs_level,
        )

    # Construction de la liste diagnostics finale
    symptom_set = set(symptoms_compressed)
    diagnoses = _build_diagnosis_list(probs, symptom_set)
    diagnoses_names = [d.name for d in diagnoses]

    # ── Étape 9 : LME ─────────────────────────────────────────────────────────
    tests, cost, comparison, test_explanations, test_probabilities, test_costs = lme.run(
        diagnoses_names=diagnoses_names,
        symptom_set=symptom_set,
        probs=probs,
    )
    logger.debug(f"LME → required={tests.required}, optional={tests.optional}")

    # ── Étape 10 : SGL ────────────────────────────────────────────────────────
    confidence_final, sgl_warnings = sgl.run(
        diagnoses_names=diagnoses_names,
        probs=probs,
        symptom_count=len(symptoms_compressed),
        confidence_level=confidence_level,
        incoherence_score=incoherence_score,
    )
    logger.debug(f"SGL → confidence={confidence_final}, warnings={sgl_warnings}")
    if _debug:
        trace.selected_tests = list(tests.required) + list(tests.optional)
        trace.sgl_warnings = list(sgl_warnings)
        trace.confidence_final = confidence_final

    explanation = _build_explanation(symptoms_compressed, diagnoses, tests.required)

    return AnalyzeResponse(
        diagnoses=diagnoses,
        tests=tests,
        cost=cost,
        explanation=explanation,
        comparison=comparison,
        confidence_level=confidence_final,
        urgency_level=urgency_level,
        emergency_flag=False,
        emergency_reason="",
        tcs_level=tcs_level,
        sgl_warnings=sgl_warnings,
        test_explanations=test_explanations,
        test_probabilities=test_probabilities,
        test_costs=test_costs,
        consultation_cost=CONSULTATION_COST,
        debug_trace=trace,
    )