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


def run(probs: dict[str, float], symptoms: list[str] | None = None) -> str:
    """
    Évalue le niveau de risque global basé sur les diagnostics et leurs probabilités.
    Retourne "élevé" | "modéré" | "faible".
    """
    sym_set = set(symptoms or [])

    # ── Règles symptomatiques directes — priorité même si probs vide ─────────

    # Douleur thoracique seule → risque élevé (origine cardiaque à écarter)
    # Douleur thoracique urgente seulement si associée à symptômes respiratoires/cardiaques
    # Seule ou avec contexte digestif (nausées, perte d'appétit) → pas automatiquement urgent
    _RESPIRATORY_CARDIAC = frozenset({"essoufflement", "toux", "palpitations", "syncope"})
    if "douleur thoracique" in sym_set and sym_set & _RESPIRATORY_CARDIAC:
        return "élevé"
    if "douleur thoracique" in sym_set and len(sym_set) <= 2:
        return "élevé"

    # Fièvre + altération état général → risque élevé (sepsis-like à écarter)
    _AEG_VARIANTS: frozenset = frozenset({
        "altération état général", "alteration etat general",
        "aeg", "altération de l'état général",
    })
    if "fièvre" in sym_set and sym_set & _AEG_VARIANTS:
        return "élevé"

    if not probs:
        return "faible"

    top_diag = max(probs, key=probs.get)
    top_prob = probs[top_diag]

    # Diagnostics qui ne déclenchent pas "élevé" sauf s'ils sont top1 dominant
    _NO_AUTO_HIGH: set[str] = {"Asthme", "Bronchite"}

    # ── Règle de sécurité : Angor dominant même avec peu de symptômes ────────
    # Si Angor est top1 avec prob significative → élevé
    # (couvre douleur thoracique seule après normalisation BPU)
    if top_diag == "Angor" and top_prob >= 0.35:
        return "élevé"

    # Risque élevé : diagnostic urgent dominant (top1)
    if top_diag in URGENT_DIAGNOSES and top_diag not in _NO_AUTO_HIGH and top_prob >= _HIGH_RISK_THRESHOLD:
        return "élevé"

    # Risque élevé : Pneumonie ou Embolie très probable même si pas en top1
    _DIFFERENTIAL_URGENT: set[str] = {"Pneumonie", "Embolie pulmonaire"}
    for diag in _DIFFERENTIAL_URGENT:
        if probs.get(diag, 0) >= 0.65:
            return "élevé"

    # Risque modéré : diagnostic urgent probable mais pas dominant
    if top_diag in URGENT_DIAGNOSES and top_prob >= _MODERATE_RISK_THRESHOLD:
        return "modéré"

    # Risque modéré : diagnostic chronique connu avec haute probabilité
    if top_diag in _MODERATE_RISK_DIAGNOSES and top_prob >= 0.50:
        return "modéré"

    # Trouble du rythme → modéré seulement si score très élevé
    # palpitations isolées → faible (validé Gold Pack C7/F4)
    if probs.get("Trouble du rythme", 0) >= 0.70:
        return "modéré"

    # Risque urgent dans le différentiel (top3)
    sorted_diags = sorted(probs.items(), key=lambda x: -x[1])[:3]
    for diag, prob in sorted_diags:
        if diag in _NO_AUTO_HIGH:
            continue
        if diag == "Angor":
            continue
        if diag in URGENT_DIAGNOSES and prob >= 0.44:
            return "élevé"
        if diag in URGENT_DIAGNOSES and prob >= 0.50:
            return "modéré"

    # Tous les autres cas (Grippe, Rhinopharyngite, Bronchite...) : faible
    return "faible"