# ── TCS — Threshold & Classification System (étape 8) ───────────────────────
# Entrée : probs, symptom_count, symptoms, incoherence_score
# Sortie : (tcs_level, confidence_level)
#
# Seuils ТЗ :
#   ≥ 0.90 → fort | 0.75–0.89 → besoin_tests | < 0.75 → incertain
#
# Confidence composite (ТЗ п.5) — trois composantes :
#   1. couverture  : part des symptômes couverts par le top diagnostic
#   2. cohérence   : écart entre top prob et 2e prob (plus grand = plus clair)
#   3. qualité     : nombre de symptômes fournis (proxy qualité données)
#
# Règle ТЗ : si données insuffisantes → confidence plafonné à 0.55

from app.data.symptoms import SYMPTOM_DIAGNOSES

# Plafond si données insuffisantes (ТЗ п.5)
_LOW_DATA_CAP: float = 0.55
_LOW_DATA_THRESHOLD: int = 2      # ≤ N symptômes = données insuffisantes

# Pénalité incoherence par unité de score
_INCOHERENCE_PENALTY_PER_UNIT: float = 0.08


def _compute_confidence(
    probs: dict[str, float],
    symptoms: list[str],
    incoherence_score: float,
) -> float:
    """
    Confidence composite 0.0–1.0.

    composante 1 — couverture :
        nb symptômes qui contribuent au top diagnostic / nb total symptômes
    composante 2 — cohérence :
        écart normalisé entre top et 2e probabilité
    composante 3 — qualité données :
        score basé sur le nombre de symptômes (sature à 1.0 à partir de 4)
    """
    if not probs:
        return 0.0

    sorted_probs = sorted(probs.values(), reverse=True)
    top_prob = sorted_probs[0]
    top_diag = max(probs, key=probs.get)

    # Composante 1 — couverture
    diag_symptoms = set(SYMPTOM_DIAGNOSES.get(top_diag, {}).keys())
    symptom_set = set(symptoms)
    if symptom_set:
        couverture = len(symptom_set & diag_symptoms) / len(symptom_set)
    else:
        couverture = 0.0

    # Composante 2 — cohérence (séparation entre top et 2e)
    if len(sorted_probs) >= 2:
        gap = sorted_probs[0] - sorted_probs[1]
        coherence = min(gap / 0.30, 1.0)   # gap de 0.30 = cohérence max
    else:
        coherence = 1.0   # un seul diagnostic = pas d'ambiguïté

    # Composante 3 — qualité données
    n = len(symptoms)
    qualite = min(n / 4.0, 1.0)   # sature à 4 symptômes

    # Score composite pondéré
    score = 0.40 * couverture + 0.35 * coherence + 0.25 * qualite

    # Pénalité incoherence (ТЗ п.6)
    score -= incoherence_score * _INCOHERENCE_PENALTY_PER_UNIT
    score = max(0.0, score)

    # Cap si données insuffisantes (ТЗ п.5)
    if n <= _LOW_DATA_THRESHOLD:
        score = min(score, _LOW_DATA_CAP)

    return round(score, 3)


def _score_to_level(score: float) -> str:
    if score >= 0.65:
        return "élevé"
    elif score >= 0.40:
        return "modéré"
    return "faible"


def run(
    probs: dict[str, float],
    symptom_count: int,
    symptoms: list[str] | None = None,
    incoherence_score: float = 0.0,
) -> tuple[str, str, float]:
    """
    Retourne (tcs_level, confidence_level, confidence_score).

    tcs_level         : décision clinique — fort | besoin_tests | incertain
    confidence_level  : élevé | modéré | faible
    confidence_score  : float 0.0–1.0 (composite)
    """
    if not probs:
        return "incertain", "faible", 0.0

    top_prob = max(probs.values())

    # TCS level
    if top_prob >= 0.90:
        tcs_level = "fort"
    elif top_prob >= 0.75:
        tcs_level = "besoin_tests"
    else:
        tcs_level = "incertain"

    # Cap TCS при недостатньо даних (ТЗ п.5)
    # ≤2 симптоми → не може бути fort, максимум besoin_tests
    if symptom_count <= _LOW_DATA_THRESHOLD and tcs_level == "fort":
        tcs_level = "besoin_tests"

    # Composite confidence
    syms = symptoms or []
    conf_score = _compute_confidence(probs, syms, incoherence_score)
    conf_level = _score_to_level(conf_score)

    return tcs_level, conf_level, conf_score