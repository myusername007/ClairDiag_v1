# ── RFE — Red Flag Engine (étape 3) ─────────────────────────────────────────
# Entrée : liste de symptômes (sortie SCM)
# Sortie : dict {emergency: bool, reason: str}
#
# CRITIQUE : s'exécute AVANT le scoring (BPU).
# Si un red flag est détecté → le pipeline retourne immédiatement EMERGENCY.
# Ne calcule aucun diagnostic — uniquement la détection de danger immédiat.

# Symptômes déclenchant une alerte d'urgence absolue
_RED_FLAGS: dict[str, str] = {
    "cyanose":                  "Cyanose détectée — appel du 15 (SAMU) immédiat requis.",
    "syncope":                  "Syncope — perte de connaissance, appel du 15 immédiat.",
    "hémoptysie":               "Hémoptysie — sang dans les crachats, consultation urgente.",
    "douleur thoracique intense": "Douleur thoracique intense — suspicion d'infarctus, appel du 15.",
    "paralysie":                "Paralysie soudaine — suspicion d'AVC, appel du 15 immédiat.",
}

# Combinaisons de symptômes déclenchant une alerte (même sans red flag isolé)
# IMPORTANT : uniquement les combinaisons vraiment critiques, pas les tableaux cliniques courants
_RED_FLAG_COMBOS: list[tuple[frozenset[str], str]] = [
    (
        frozenset({"douleur thoracique intense", "essoufflement"}),
        "Douleur thoracique intense + essoufflement — suspicion d'infarctus, appel du 15.",
    ),
    (
        frozenset({"syncope", "douleur thoracique"}),
        "Syncope + douleur thoracique — risque cardiaque majeur, appel du 15.",
    ),
]


class RFEResult:
    __slots__ = ("emergency", "reason")

    def __init__(self, emergency: bool, reason: str = ""):
        self.emergency = emergency
        self.reason = reason


def run(symptoms: list[str]) -> RFEResult:
    """
    Vérifie la présence de red flags dans la liste de symptômes.
    Retourne RFEResult(emergency=True, reason=...) si un danger immédiat est détecté.
    Retourne RFEResult(emergency=False) si tout est normal — le pipeline continue.
    """
    symptom_set = set(symptoms)

    # 1. Red flags isolés
    for flag, reason in _RED_FLAGS.items():
        if flag in symptom_set:
            return RFEResult(emergency=True, reason=reason)

    # 2. Combinaisons dangereuses
    for combo, reason in _RED_FLAG_COMBOS:
        if combo.issubset(symptom_set):
            return RFEResult(emergency=True, reason=reason)

    return RFEResult(emergency=False)