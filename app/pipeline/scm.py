# ── SCM — Symptom Compression Module (étape 2) ──────────────────────────────
# Entrée : liste de symptômes canoniques (sortie NSE)
# Sortie : liste compressée — 5 à 12 symptômes clés
#
# Responsabilité : éliminer le bruit quand l'utilisateur entre trop de symptômes.
# Si ≤ 12 symptômes → passe sans modification.
# Si > 12 → sélectionne les plus spécifiques (moins de diagnostics associés = plus informatif).

from app.data.symptoms import SYMPTOM_DIAGNOSES

_MIN_SYMPTOMS = 5
_MAX_SYMPTOMS = 12


def _specificity_score(symptom: str) -> float:
    """
    Score de spécificité inverse : symptôme pointant vers peu de diagnostics = plus précieux.
    Retourne 1.0 pour un symptôme inconnu (neutre).
    """
    diags = SYMPTOM_DIAGNOSES.get(symptom, {})
    if not diags:
        return 1.0
    return 1.0 / len(diags)


def run(symptoms: list[str]) -> list[str]:
    """
    Si le nombre de symptômes est dans la fenêtre [5, 12] → retourne tel quel.
    Si > 12 → sélectionne les _MAX_SYMPTOMS symptômes les plus spécifiques.
    Si < 5 → retourne tel quel (pas assez pour compresser).
    """
    if len(symptoms) <= _MAX_SYMPTOMS:
        return symptoms

    # Trier par spécificité décroissante, garder les _MAX_SYMPTOMS premiers
    ranked = sorted(symptoms, key=_specificity_score, reverse=True)
    return ranked[:_MAX_SYMPTOMS]