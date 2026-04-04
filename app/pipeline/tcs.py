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
    # SYMPTOM_DIAGNOSES est {symptôme: {diag: weight}} — on inverse la recherche
    diag_symptoms = {sym for sym, diags in SYMPTOM_DIAGNOSES.items() if top_diag in diags}
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
    if n <= 1:
        score = min(score, 0.35)   # 1 symptôme → max faible
    elif n <= _LOW_DATA_THRESHOLD:
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
    top_diag = max(probs, key=probs.get)

    # ── TCS decision logic ──────────────────────────────────────────────────
    # Groupes de diagnostics par comportement TCS :
    #
    # ALWAYS_NEEDS_TESTS : jamais fort (confirmation biologique obligatoire)
    # NEEDS_TESTS_IF_STRONG : besoin_tests si symptom_count >= 2, incertain sinon
    # LIGHT : incertain sauf profil fort (>= 3 symptômes ET top_prob >= 0.75)
    # Pneumonie : fort autorisé si >= 5 symptômes
    # Autres (Angor, Hypertension...) : logique prob pure

    _ALWAYS_NEEDS_TESTS: set[str] = {
        "Insuffisance cardiaque", "Embolie pulmonaire", "Trouble du rythme",
        "RGO", "SII",
    }
    _NEEDS_TESTS_IF_STRONG: set[str] = {
        "Asthme", "Bronchite", "Pneumonie",
    }
    _LIGHT_DIAGNOSES: set[str] = {
        "Gastrite", "Rhinopharyngite", "Allergie",
    }
    # Infectieux : besoin_tests si fièvre présente, incertain si profil très léger
    _INFECTIEUX: set[str] = {"Grippe", "Angine"}

    _syms_set = set(symptoms or [])
    has_fievre = "fièvre" in _syms_set

    # Étape 1 : score brut basé sur top_prob
    if top_prob >= 0.90:
        tcs_level = "fort"
    elif top_prob >= 0.75:
        tcs_level = "besoin_tests"
    else:
        tcs_level = "incertain"

    # Étape 2 : overrides par groupe de diagnostic

    # Jamais fort; et si 1 seul symptôme → incertain même pour ces diagnostics
    if tcs_level == "fort" and top_diag in _ALWAYS_NEEDS_TESTS:
        tcs_level = "besoin_tests"
    if top_diag in _ALWAYS_NEEDS_TESTS and symptom_count < 2:
        tcs_level = "incertain"

    # Pneumonie : fort seulement si profil très complet (>= 5 symptômes)
    if top_diag == "Pneumonie":
        if symptom_count >= 5 and top_prob >= 0.75:
            tcs_level = "fort"
        elif symptom_count >= 3 and top_prob >= 0.60:
            tcs_level = "besoin_tests"
        elif symptom_count >= 2 and top_prob >= 0.75:
            tcs_level = "besoin_tests"
        else:
            tcs_level = "incertain"

    # Asthme / Bronchite : besoin_tests si >= 2 symptômes, incertain sinon
    # (jamais fort — confirmation spirométrie/Rx nécessaire)
    if top_diag in _NEEDS_TESTS_IF_STRONG - {"Pneumonie"}:
        if tcs_level == "fort":
            tcs_level = "besoin_tests"
        if symptom_count < 2:
            tcs_level = "incertain"

    # Diagnostics légers : incertain si <= 3 symptômes (Gastrite, Rhinopharyngite, Allergie)
    if top_diag in _LIGHT_DIAGNOSES and symptom_count <= 3:
        tcs_level = "incertain"

    # Infectieux (Grippe, Angine) :
    # - fièvre présente ET symptom_count >= 2 → besoin_tests (bilan infectieux justifié)
    # - sinon → incertain
    if top_diag in _INFECTIEUX:
        if tcs_level == "fort":
            tcs_level = "besoin_tests"
        if has_fievre and symptom_count >= 2:
            tcs_level = "besoin_tests"
        elif not has_fievre or symptom_count < 2:
            tcs_level = "incertain"

    # Threshold Guard final — fort seulement si profil vraiment solide
    if tcs_level == "fort":
        if symptom_count <= _LOW_DATA_THRESHOLD:
            tcs_level = "besoin_tests"
        elif incoherence_score > 0.15:
            tcs_level = "besoin_tests"
        else:
            _syms = symptoms or []
            _diag_syms = {sym for sym, diags in SYMPTOM_DIAGNOSES.items() if top_diag in diags}
            _covered = len(set(_syms) & _diag_syms)
            if _covered < 2:
                tcs_level = "besoin_tests"

    # Composite confidence
    syms = symptoms or []
    conf_score = _compute_confidence(probs, syms, incoherence_score)
    conf_level = _score_to_level(conf_score)

    return tcs_level, conf_level, conf_score