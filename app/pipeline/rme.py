# ── RME — Risk Module Engine (étape 5) ──────────────────────────────────────
# Entrée : dict de probabilités (sortie BPU)
# Sortie : str urgency_level — "élevé" | "modéré" | "faible"
#
# Logique légère : évalue le niveau de risque basé sur les diagnostics détectés
# et leur probabilité. N'annule pas RFE — RFE reste prioritaire.

from app.data.symptoms import URGENT_DIAGNOSES

# ── TriageGate — v2.4 ─────────────────────────────────────────────────────────
# RÈGLE ABSOLUE : URGENCE seulement sur combinaisons définies
# Aucun symptôme isolé ne peut déclencher urgence (sauf RFE hard rules)

# Combinaisons autorisées → urgence
_URGENCE_COMBOS: list[frozenset[str]] = [
    frozenset({"douleur thoracique", "irradiation bras gauche"}),
    frozenset({"douleur thoracique", "irradiation machoire"}),
    frozenset({"douleur thoracique", "essoufflement"}),
    frozenset({"douleur thoracique", "syncope"}),
    frozenset({"détresse respiratoire", "essoufflement"}),
    frozenset({"perte de connaissance"}),          # isolée suffit
    frozenset({"syncope"}),                        # isolée suffit
    frozenset({"paralysie"}),                      # isolée suffit
    frozenset({"trouble parole", "paralysie"}),
    frozenset({"raideur nuque", "fièvre"}),
    frozenset({"douleur abdominale", "hématémèse", "fièvre"}),
    frozenset({"anaphylaxie"}),
]

# Symptômes qui ne peuvent PAS déclencher urgence isolément
_FORBIDDEN_SINGLE_URGENCE: frozenset[str] = frozenset({
    "fatigue", "malaise", "gonflement jambes", "gonflement visage",
    "palpitations", "ballonnements", "diarrhée", "nausées",
    "vertiges", "douleur abdominale", "prise de poids rapide",
    "œdème périphérique", "rétention hydrique",
    "douleur thoracique",  # seule → modéré, pas urgence
})


def triage_gate(sym_set: set[str], urgency_level: str) -> str:
    """
    Valide ou rétrograde le urgency_level calculé par RME.
    Retourne urgency_level validé : "élevé" | "modéré" | "faible".

    Règle : si urgency_level == "élevé" mais aucun combo d'urgence n'est présent
    ET le seul déclencheur est un symptôme interdit isolé → rétrogradation à "modéré".
    """
    if urgency_level != "élevé":
        return urgency_level

    # Vérifie si au moins un combo autorisé est présent
    for combo in _URGENCE_COMBOS:
        if combo.issubset(sym_set):
            return "élevé"  # combo validé → urgence légitime

    # Aucun combo → vérifier si le déclencheur est un symptôme isolé interdit
    red_flag_present = sym_set - _FORBIDDEN_SINGLE_URGENCE
    if not red_flag_present:
        return "modéré"  # rétrogradation

    # Symptômes non-interdits présents mais pas de combo → modéré par précaution
    # (ex: douleur thoracique seule sans irradiation/essoufflement)
    return "modéré"

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
    # Douleur thoracique urgente SEULEMENT si associée à symptômes cardio-respiratoires
    # Seule (≤2 symptômes) → modéré (à explorer, pas urgence immédiate)
    _RESPIRATORY_CARDIAC = frozenset({"essoufflement", "toux", "palpitations", "syncope", "irradiation bras gauche", "irradiation machoire"})
    if "douleur thoracique" in sym_set and sym_set & _RESPIRATORY_CARDIAC:
        return "élevé"
    if "douleur thoracique" in sym_set and len(sym_set) <= 2:
        return "modéré"  # pas élevé — douleur isolée sans combo cardiaque

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

    # ── Profil digestif sans signaux d'alarme → cap à "modéré" ───────────────
    _DIGESTIF_DIAGS: set[str] = {
        "Dysbiose", "Infection intestinale", "SII", "Gastrite", "RGO",
        "Dyspepsie", "Colite", "Clostridioides difficile",
    }
    _DIGESTIF_RED_FLAGS: frozenset = frozenset({
        "sang selles", "sang dans les selles", "fièvre", "déshydratation",
        "perte de poids", "rectorragie",
    })
    _top3_names = {d for d, _ in sorted(probs.items(), key=lambda x: -x[1])[:3]}
    _is_pure_digestif = bool(_top3_names) and _top3_names.issubset(_DIGESTIF_DIAGS)
    if _is_pure_digestif and not (sym_set & _DIGESTIF_RED_FLAGS) and top_prob >= 0.45:
        return "modéré"

    # Diagnostics qui ne déclenchent pas "élevé" sauf s'ils sont top1 dominant
    _NO_AUTO_HIGH: set[str] = {"Asthme", "Bronchite"}

    # ── Règle de sécurité : Angor / Infarctus dominant → élevé ─────────────
    # Si Angor ou Infarctus est top1 avec prob significative → élevé
    if top_diag in {"Angor", "Infarctus du myocarde"} and top_prob >= 0.35:
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