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
)

logger = logging.getLogger("clairdiag.pipeline")

_MAX_PROB: float = 0.75
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

    # ── Étape 1 : NSE ─────────────────────────────────────────────────────────
    symptoms_canonical = nse.run(request.symptoms)
    logger.debug(f"NSE → {symptoms_canonical}")

    # ── Étape 2 : SCM ─────────────────────────────────────────────────────────
    symptoms_compressed = scm.run(symptoms_canonical)
    logger.debug(f"SCM → {symptoms_compressed}")

    # ── Étape 3 : RFE ─────────────────────────────────────────────────────────
    rfe_result = rfe.run(symptoms_compressed)
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
        return resp

    # ── Étape 4 : BPU ─────────────────────────────────────────────────────────
    probs, incoherence_score = bpu.run(symptoms_compressed)
    logger.debug(f"BPU → probs={len(probs)}, incoherence={incoherence_score:.3f}")
    logger.debug(f"BPU → {probs}")

    if not probs:
        return _empty_response(
            "Les symptômes indiqués ne permettent pas d'identifier un diagnostic. "
            "Veuillez consulter un médecin."
        )

    # ── Étape 5 : RME ─────────────────────────────────────────────────────────
    urgency_level = rme.run(probs)
    logger.debug(f"RME → urgency={urgency_level}")

    # ── Étape 6 : TCE ─────────────────────────────────────────────────────────
    probs = tce.run(probs, onset=request.onset, duration=request.duration)
    logger.debug(f"TCE → {probs}")

    # ── Étape 7 : CRE ─────────────────────────────────────────────────────────
    probs = cre.run(probs, symptoms_compressed)
    logger.debug(f"CRE → {probs}")

    # ── Étape 8 : TCS ─────────────────────────────────────────────────────────
    tcs_level, confidence_level, confidence_score = tcs.run(
        probs, len(symptoms_compressed),
        symptoms=symptoms_compressed,
        incoherence_score=incoherence_score,
    )
    logger.debug(f"TCS → tcs={tcs_level}, confidence={confidence_level}, score={confidence_score}")

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
    )