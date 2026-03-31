# ── RME — Risk Module Engine (étape 5) ──────────────────────────────────────
# Entrée : dict de probabilités (sortie BPU)
# Sortie : str urgency_level — "élevé" | "modéré" | "faible"
#
# Logique légère : évalue le niveau de risque basé sur les diagnostics détectés
# et leur probabilité. N'annule pas RFE — RFE reste prioritaire.

from app.data.symptoms import URGENT_DIAGNOSES

# Diagnostics à risque modéré (nécessitent attention mais pas urgence immédiate)
_MODERATE_RISK_DIAGNOSES: set[str] = {"Hypertension", "Anémie", "Asthme"}

# Seuils de déclenchement
_HIGH_RISK_THRESHOLD: float = 0.40
_MODERATE_RISK_THRESHOLD: float = 0.35


def run(probs: dict[str, float]) -> str:
    """
    Évalue le niveau de risque global basé sur les diagnostics et leurs probabilités.
    Retourne "élevé" | "modéré" | "faible".
    """
    if not probs:
        return "faible"

    top_diag = max(probs, key=probs.get)
    top_prob = probs[top_diag]

    # Risque élevé : diagnostic urgent avec probabilité significative
    if top_diag in URGENT_DIAGNOSES and top_prob >= _HIGH_RISK_THRESHOLD:
        return "élevé"

    # Risque élevé : n'importe quel diagnostic urgent très probable
    for diag in URGENT_DIAGNOSES:
        if probs.get(diag, 0) >= 0.55:
            return "élevé"

    # Risque modéré : diagnostic urgent probable OU diagnostic modéré avec haute proba
    if top_diag in URGENT_DIAGNOSES and top_prob >= _MODERATE_RISK_THRESHOLD:
        return "modéré"
    if top_diag in _MODERATE_RISK_DIAGNOSES and top_prob >= 0.50:
        return "modéré"
    if top_prob >= 0.55:
        return "modéré"

    return "faible"