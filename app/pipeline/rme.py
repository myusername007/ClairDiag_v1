# ── RME — Risk Module Engine (étape 5) ──────────────────────────────────────
# Entrée : dict de probabilités (sortie BPU)
# Sortie : str urgency_level — "élevé" | "modéré" | "faible"
#
# Logique légère : évalue le niveau de risque basé sur les diagnostics détectés
# et leur probabilité. N'annule pas RFE — RFE reste prioritaire.

from app.data.symptoms import URGENT_DIAGNOSES

# Diagnostics à risque modéré (nécessitent attention mais pas urgence immédiate)
_MODERATE_RISK_DIAGNOSES: set[str] = {"Hypertension", "Asthme"}

# Seuils de déclenchement
_HIGH_RISK_THRESHOLD: float = 0.40
_MODERATE_RISK_THRESHOLD: float = 0.35


def run(probs: dict[str, float]) -> str:
    """
    Évalue le niveau de risque global basé sur les diagnostics et leurs probabilités.
    Retourne "élevé" | "modéré" | "faible".

    Règle clé : "élevé" uniquement si le diagnostic est dans URGENT_DIAGNOSES.
    Un diagnostic non-urgent (Grippe, Bronchite...) ne peut jamais déclencher "élevé",
    même à probabilité maximale.
    """
    if not probs:
        return "faible"

    top_diag = max(probs, key=probs.get)
    top_prob = probs[top_diag]

    # Risque élevé : diagnostic urgent dominant
    if top_diag in URGENT_DIAGNOSES and top_prob >= _HIGH_RISK_THRESHOLD:
        return "élevé"

    # Risque élevé : diagnostic urgent très probable même si pas en top1
    for diag in URGENT_DIAGNOSES:
        if probs.get(diag, 0) >= 0.55:
            return "élevé"

    # Risque modéré : diagnostic urgent probable mais pas dominant
    if top_diag in URGENT_DIAGNOSES and top_prob >= _MODERATE_RISK_THRESHOLD:
        return "modéré"

    # Risque modéré : diagnostic chronique connu avec haute probabilité
    if top_diag in _MODERATE_RISK_DIAGNOSES and top_prob >= 0.50:
        return "modéré"

    # Risque modéré : diagnostic urgent présent dans le différentiel (top3)
    sorted_diags = sorted(probs.items(), key=lambda x: -x[1])[:3]
    for diag, prob in sorted_diags:
        if diag in URGENT_DIAGNOSES and prob >= 0.40:
            return "modéré"

    # Tous les autres cas (Grippe, Rhinopharyngite, Bronchite...) : faible
    return "faible"