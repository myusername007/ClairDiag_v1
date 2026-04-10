# ── RFE — Red Flag Engine (étape 3) ─────────────────────────────────────────
# Entrée : liste de symptômes (sortie SCM)
# Sortie : RFEResult {emergency, reason, category}
#
# CRITIQUE : s'exécute AVANT le scoring (BPU).
# Si un red flag est détecté → le pipeline retourne immédiatement EMERGENCY.
# Ne calcule aucun diagnostic — uniquement la détection de danger immédiat.
#
# Catégories :
#   respiratory | cardiac | neurological | digestive | infectious | systemic

# Symptômes déclenchant une alerte d'urgence absolue
# Format : symptôme → (reason, category)
_RED_FLAGS: dict[str, tuple[str, str]] = {
    "cyanose":                    ("Cyanose détectée — appel du 15 (SAMU) immédiat requis.", "respiratory"),
    "syncope":                    ("Syncope — perte de connaissance, appel du 15 immédiat.", "cardiac"),
    "hémoptysie":                 ("Hémoptysie — sang dans les crachats, consultation urgente.", "respiratory"),
    "douleur thoracique intense": ("Douleur thoracique intense — suspicion d'infarctus, appel du 15.", "cardiac"),
    "paralysie":                  ("Paralysie soudaine — suspicion d'AVC, appel du 15 immédiat.", "neurological"),
    "détresse respiratoire":      ("Détresse respiratoire sévère — appel du 15 immédiat.", "respiratory"),
    "perte de connaissance":      ("Perte de connaissance — appel du 15 immédiat.", "neurological"),
    "déficit neurologique":       ("Déficit neurologique brutal — suspicion d'AVC, appel du 15.", "neurological"),
}

# Combinaisons de symptômes déclenchant une alerte
# Format : (frozenset requis, reason, category)
_RED_FLAG_COMBOS: list[tuple[frozenset[str], str, str]] = [
    (
        frozenset({"douleur thoracique intense", "essoufflement"}),
        "Douleur thoracique intense + essoufflement — suspicion d'infarctus, appel du 15.",
        "cardiac",
    ),
    (
        frozenset({"syncope", "douleur thoracique"}),
        "Syncope + douleur thoracique — risque cardiaque majeur, appel du 15.",
        "cardiac",
    ),
    (
        frozenset({"fièvre", "altération état général", "hypotension"}),
        "Syndrome septique probable — fièvre + AEG + hypotension, appel du 15.",
        "infectious",
    ),
]

# Catégories → labels lisibles
CATEGORY_LABELS: dict[str, str] = {
    "respiratory":   "Alerte respiratoire",
    "cardiac":       "Alerte cardiaque",
    "neurological":  "Alerte neurologique",
    "digestive":     "Alerte digestive",
    "infectious":    "Alerte infectieuse",
    "systemic":      "Alerte systémique",
}


class RFEResult:
    __slots__ = ("emergency", "reason", "category")

    def __init__(self, emergency: bool, reason: str = "", category: str = ""):
        self.emergency = emergency
        self.reason = reason
        self.category = category


def run(symptoms: list[str]) -> RFEResult:
    """
    Vérifie la présence de red flags dans la liste de symptômes.
    Retourne RFEResult(emergency=True, reason=..., category=...) si danger immédiat.
    Retourne RFEResult(emergency=False) si tout est normal — le pipeline continue.
    """
    symptom_set = set(symptoms)

    # 1. Red flags isolés
    for flag, (reason, category) in _RED_FLAGS.items():
        if flag in symptom_set:
            return RFEResult(emergency=True, reason=reason, category=category)

    # 2. Combinaisons dangereuses
    for combo, reason, category in _RED_FLAG_COMBOS:
        if combo.issubset(symptom_set):
            return RFEResult(emergency=True, reason=reason, category=category)

    return RFEResult(emergency=False)


# ── Patterns textuels pour check_red_flags() (avant NLP) ─────────────────────
# Format : (mots_primaires, mots_secondaires, reason, category)
RED_FLAG_PATTERNS: list[tuple[list[str], list[str], str, str]] = [
    # Douleur thoracique + irradiation bras/mâchoire → SCA
    (
        ["douleur", "poitrine", "thorax", "thoracique", "chest", "pain", "боль", "грудь", "oppression", "serrement", "étau"],
        ["bras", "gauche", "mâchoire", "jaw", "arm", "left", "рука", "челюсть", "irradie", "irradiation", "remonte"],
        "Douleur thoracique avec irradiation — suspicion d'infarctus, appel du 15.",
        "cardiac",
    ),
    # Syncope + douleur → urgence cardiaque
    (
        ["syncope", "évanoui", "évanouie", "perdu connaissance", "perte de connaissance", "malaise brutal"],
        ["douleur", "poitrine", "thorax", "chest"],
        "Syncope avec douleur thoracique — risque cardiaque majeur, appel du 15.",
        "cardiac",
    ),
    # Paralysie/engourdissement unilatéral → AVC
    (
        ["paralysie", "paralysé", "paralysée", "paralysis", "engourdissement"],
        ["visage", "face", "bras", "jambe", "côté", "gauche", "droit", "unilatéral", "hémiplégie"],
        "Paralysie/engourdissement unilatéral — suspicion d'AVC, appel du 15.",
        "neurological",
    ),
    # Détresse respiratoire + douleur thoracique
    (
        ["mal respirer", "pas respirer", "difficulté respirer", "impossible respirer",
         "détresse", "asphyxie", "étouffement"],
        ["douleur", "poitrine", "thorax", "poitrine", "chest"],
        "Détresse respiratoire avec douleur thoracique — appel du 15 immédiat.",
        "cardiac",
    ),
    # Fièvre + AEG + hypotension → sepsis
    (
        ["fièvre", "fever", "température"],
        ["hypotension", "choc", "confusion", "altération", "état général", "aeg"],
        "Syndrome septique probable — fièvre + AEG/hypotension, appel du 15.",
        "infectious",
    ),
]


def check_red_flags(symptoms_text: str) -> dict:
    """
    Vérifie le texte brut pour des patterns d'urgence AVANT le traitement NLP.
    Doit être appelé en premier, avant toute autre logique diagnostique.

    Retourne dict avec :
      triggered       : bool
      action          : "EMERGENCY" | absent
      block_reassurance : bool — masquer tout texte rassurant
      message         : str — message visible utilisateur
      reason          : str — raison technique
      category        : str — type d'urgence
    """
    text = symptoms_text.lower()

    for primary_words, secondary_words, reason, category in RED_FLAG_PATTERNS:
        has_primary = any(w in text for w in primary_words)
        has_secondary = any(w in text for w in secondary_words)
        if has_primary and has_secondary:
            return {
                "triggered": True,
                "action": "EMERGENCY",
                "block_reassurance": True,
                "message": "⚠️ Appelez le 15 / 112 immédiatement",
                "reason": reason,
                "category": category,
            }

    return {"triggered": False}