# ── RME — Risk Module Engine (étape 5) ──────────────────────────────────────
# Entrée : dict de probabilités (sortie BPU)
# Sortie : str urgency_level — "élevé" | "modéré" | "faible"
#
# Logique légère : évalue le niveau de risque basé sur les diagnostics détectés
# et leur probabilité. N'annule pas RFE — RFE reste prioritaire.

from app.data.symptoms import URGENT_DIAGNOSES

# Diagnostics à risque modéré (nécessitent attention mais pas urgence immédiate)
# Trouble du rythme retiré : palpitations isolées sans syncope/douleur → faible
_MODERATE_RISK_DIAGNOSES: set[str] = {"Hypertension", "Insuffisance cardiaque"}

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

    # Diagnostics qui ne déclenchent pas "élevé" même s'ils sont dans URGENT_DIAGNOSES
    # (Asthme, Bronchite : urgence gérée par RFE, pas par probabilité seule)
    _NO_AUTO_HIGH: set[str] = {"Asthme", "Bronchite"}

    # Risque élevé : diagnostic urgent dominant
    if top_diag in URGENT_DIAGNOSES and top_diag not in _NO_AUTO_HIGH and top_prob >= _HIGH_RISK_THRESHOLD:
        return "élevé"

    # Risque élevé : diagnostic urgent très probable même si pas en top1
    # Seuil 0.65 pour éviter les faux positifs (Angor/Pneumonie secondaires)
    for diag in URGENT_DIAGNOSES:
        if diag in _NO_AUTO_HIGH:
            continue
        if probs.get(diag, 0) >= 0.65:
            return "élevé"

    # Risque modéré : diagnostic urgent probable mais pas dominant
    if top_diag in URGENT_DIAGNOSES and top_prob >= _MODERATE_RISK_THRESHOLD:
        return "modéré"

    # Risque modéré : diagnostic chronique connu avec haute probabilité
    if top_diag in _MODERATE_RISK_DIAGNOSES and top_prob >= 0.50:
        return "modéré"

    # Trouble du rythme → modéré seulement si présent avec d'autres signaux (malaise, fatigue)
    # palpitations seules → faible (géré plus bas)
    if probs.get("Trouble du rythme", 0) >= 0.70:
        return "modéré"

    # Risque urgent dans le différentiel (top3)
    sorted_diags = sorted(probs.items(), key=lambda x: -x[1])[:3]
    for diag, prob in sorted_diags:
        if diag in _NO_AUTO_HIGH:
            continue
        if diag in URGENT_DIAGNOSES and prob >= 0.44:
            return "élevé"
        if diag in URGENT_DIAGNOSES and prob >= 0.35:
            return "modéré"

    # Tous les autres cas (Grippe, Rhinopharyngite, Bronchite...) : faible
    return "faible"