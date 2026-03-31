# ── BPU — Bayesian Probability Unit (étape 4) ───────────────────────────────
# Entrée : liste de symptômes canoniques (sortie SCM, après RFE)
# Sortie : (probs dict, incoherence_score float)
#
# Logique — 3 couches :
#   1. Score de base avec facteur de spécificité
#   2. Bonus de combinaisons (COMBO_BONUSES)
#   3. Pénalités pour symptômes incompatibles (SYMPTOM_EXCLUSIONS)
#
# incoherence_score : somme des pénalités appliquées — utilisé par TCS + SGL
# pour baisser confidence quand les symptômes se contredisent.

from app.data.symptoms import (
    SYMPTOM_DIAGNOSES,
    COMBO_BONUSES,
    SYMPTOM_EXCLUSIONS,
)

_MAX_PROB: float = 0.90
_MIN_DENOM: float = 2.0
PROBABILITY_THRESHOLD: float = 0.15

_MAX_DIAG_COUNT: int = max(len(w) for w in SYMPTOM_DIAGNOSES.values())


def _specificity(n: int) -> float:
    return 1.0 + 0.5 * max(0.0, 1.0 - n / _MAX_DIAG_COUNT)


DIAGNOSIS_MAX_SCORES: dict[str, float] = {}
for _sym, _weights in SYMPTOM_DIAGNOSES.items():
    _f = _specificity(len(_weights))
    for _diag, _w in _weights.items():
        DIAGNOSIS_MAX_SCORES[_diag] = DIAGNOSIS_MAX_SCORES.get(_diag, 0) + _w * _f


def run(symptoms: list[str]) -> tuple[dict[str, float], float]:
    """
    Retourne (probs, incoherence_score).
    incoherence_score = somme totale des pénalités (0.0 = aucune contradiction).
    """
    symptom_set = {s.lower().strip() for s in symptoms}
    incoherence_score: float = 0.0

    raw: dict[str, float] = {}
    for sym in symptom_set:
        weights = SYMPTOM_DIAGNOSES.get(sym, {})
        factor = _specificity(len(weights)) if weights else 1.0
        for diag, weight in weights.items():
            raw[diag] = raw.get(diag, 0) + weight * factor

    if not raw:
        return {}, 0.0

    probs: dict[str, float] = {
        name: min(score / max(DIAGNOSIS_MAX_SCORES.get(name, _MIN_DENOM), _MIN_DENOM), 1.0)
        for name, score in raw.items()
    }

    for combo, bonuses in COMBO_BONUSES:
        if combo.issubset(symptom_set):
            for diag, bonus in bonuses.items():
                if diag in probs:
                    probs[diag] = min(1.0, probs[diag] + bonus)

    for sym in symptom_set:
        for diag, penalty in SYMPTOM_EXCLUSIONS.get(sym, {}).items():
            if diag in probs:
                probs[diag] = max(0.0, probs[diag] - penalty)
                incoherence_score += penalty

    probs = {name: min(prob, _MAX_PROB) for name, prob in probs.items()}
    probs = {name: prob for name, prob in probs.items() if prob >= PROBABILITY_THRESHOLD}

    return probs, incoherence_score