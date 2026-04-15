# ── RFE — Red Flag Engine (étape 3) ─────────────────────────────────────────
# Entrée : liste de symptômes (sortie SCM)
# Sortie : RFEResult {emergency, reason, category}
#
# CRITIQUE : s'exécute AVANT le scoring (BPU).
# Si un red flag est détecté → le pipeline retourne immédiatement EMERGENCY.
# Ne calcule aucun diagnostic — uniquement la détection de danger immédiat.
#
# Catégories :
#   respiratory | cardiac | neurological | digestive | infectious | systemic | vascular
#
# VERSION: v1.4 — expanded with dissection, AVC combo, TVP, abdomen aigu, méningite+photophobie

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
    # Nouveaux isolated red flags
    "faiblesse bras":             ("Faiblesse bras soudaine — suspicion d'AVC, appel du 15 immédiat.", "neurological"),
    "asymétrie visage":           ("Asymétrie visage — suspicion d'AVC, appel du 15 immédiat.", "neurological"),
    "gonflement gorge":           ("Gonflement gorge — suspicion anaphylaxie/œdème Quincke, appel du 15.", "respiratory"),
    "raideur nuque":              ("Raideur de nuque — suspicion méningite, appel du 15.", "neurological"),
    "sueurs froides":             ("Sueurs froides — signe d'alerte cardiaque, consultation urgente.", "cardiac"),
}

# Combinaisons de symptômes déclenchant une alerte
# Format : (frozenset requis, reason, category)
_RED_FLAG_COMBOS: list[tuple[frozenset[str], str, str]] = [
    # ── Existants ────────────────────────────────────────────────────────────
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
    # ── NOUVEAUX : Dissection aortique ────────────────────────────────────────
    (
        frozenset({"douleur thoracique", "douleur dos", "sensation déchirure"}),
        "Douleur thoracique + dorsale + déchirure — suspicion dissection aortique, appel du 15.",
        "vascular",
    ),
    (
        frozenset({"douleur thoracique", "douleur dorsale", "déchirure"}),
        "Douleur thoracique + dorsale + déchirure — suspicion dissection aortique, appel du 15.",
        "vascular",
    ),
    # ── NOUVEAUX : AVC ────────────────────────────────────────────────────────
    (
        frozenset({"faiblesse bras", "difficulté parler"}),
        "Faiblesse bras + trouble de la parole — suspicion d'AVC, appel du 15 immédiat.",
        "neurological",
    ),
    (
        frozenset({"faiblesse unilatérale", "trouble parole"}),
        "Faiblesse unilatérale + trouble parole — suspicion d'AVC, appel du 15 immédiat.",
        "neurological",
    ),
    (
        frozenset({"asymétrie visage", "faiblesse bras"}),
        "Asymétrie visage + faiblesse bras — suspicion d'AVC, appel du 15 immédiat.",
        "neurological",
    ),
    # ── NOUVEAUX : TVP isolée ─────────────────────────────────────────────────
    (
        frozenset({"jambe unilatérale gonflée", "douleur mollet"}),
        "Jambe unilatérale gonflée + douleur mollet — suspicion TVP, consultation urgente aujourd'hui.",
        "vascular",
    ),
    (
        frozenset({"œdème unilatéral", "douleur mollet"}),
        "Œdème unilatéral + douleur mollet — suspicion TVP, consultation urgente aujourd'hui.",
        "vascular",
    ),
    # ── NOUVEAUX : Méningite / HSA ────────────────────────────────────────────
    (
        frozenset({"céphalée brutale", "raideur nuque", "fièvre"}),
        "Céphalée brutale + raideur nuque + fièvre — suspicion méningite/HSA, appel du 15.",
        "neurological",
    ),
    (
        frozenset({"céphalée brutale", "photophobie", "fièvre"}),
        "Céphalée brutale + photophobie + fièvre — suspicion méningite, appel du 15.",
        "neurological",
    ),
    (
        frozenset({"céphalée brutale", "raideur nuque", "photophobie"}),
        "Céphalée brutale + raideur nuque + photophobie — suspicion HSA/méningite, appel du 15.",
        "neurological",
    ),
    # ── NOUVEAUX : Abdomen aigu ───────────────────────────────────────────────
    # RÈGLE: défense abdominale = signe de péritonite → EMERGENCY
    # Sans défense: abdomen aigu → URGENT seulement (pas appel 15 automatique)
    (
        frozenset({"douleur abdominale intense", "fièvre", "défense abdominale"}),
        "Douleur abdominale + fièvre + défense — péritonite possible, appel du 15.",
        "digestive",
    ),
    # ── NOUVEAUX : Anaphylaxie ────────────────────────────────────────────────
    (
        frozenset({"gonflement gorge", "difficulté respiratoire"}),
        "Gonflement gorge + détresse respiratoire — suspicion anaphylaxie, appel du 15.",
        "respiratory",
    ),
    (
        frozenset({"gonflement gorge", "essoufflement"}),
        "Gonflement gorge + essoufflement — suspicion œdème de Quincke, appel du 15.",
        "respiratory",
    ),
    (
        frozenset({"allergie", "essoufflement"}),
        "Allergie + essoufflement — suspicion réaction anaphylactique, appel du 15.",
        "respiratory",
    ),
    (
        frozenset({"allergie", "dyspnée"}),
        "Allergie + dyspnée — suspicion anaphylaxie, appel du 15.",
        "respiratory",
    ),
    (
        frozenset({"allergie", "gonflement gorge"}),
        "Allergie + gonflement gorge — suspicion anaphylaxie, appel du 15.",
        "respiratory",
    ),
    # ── NOUVEAUX : Méningite étendue ──────────────────────────────────────
    (
        frozenset({"fièvre", "raideur nuque"}),
        "Fièvre + raideur de nuque — suspicion méningite, appel du 15.",
        "neurological",
    ),
    (
        frozenset({"fièvre", "photophobie", "céphalées"}),
        "Fièvre + photophobie + céphalées — suspicion méningite, appel du 15.",
        "neurological",
    ),
    (
        frozenset({"altération état général", "fièvre", "céphalées"}),
        "Confusion + fièvre + céphalées — suspicion méningite/sepsis, appel du 15.",
        "neurological",
    ),
    # ── NOUVEAUX : Sueurs froides cardio ─────────────────────────────────
    (
        frozenset({"douleur thoracique", "sueurs froides"}),
        "Douleur thoracique + sueurs froides — suspicion SCA, appel du 15.",
        "cardiac",
    ),
    (
        frozenset({"oppression thoracique", "sueurs froides"}),
        "Oppression thoracique + sueurs froides — suspicion SCA, appel du 15.",
        "cardiac",
    ),
    (
        frozenset({"oppression thoracique", "nausées"}),
        "Oppression thoracique + nausées — suspicion SCA, appel du 15.",
        "cardiac",
    ),
    (
        frozenset({"douleur thoracique", "oppression thoracique"}),
        "Douleur thoracique + oppression — suspicion SCA, appel du 15.",
        "cardiac",
    ),
]

# Combinaisons urgentes NON-emergency (consultation aujourd'hui, pas appel 15)
# Format : (frozenset requis, reason, category)
_URGENT_COMBOS: list[tuple[frozenset[str], str, str]] = [
    # Formes brutes (avant NLP)
    (
        frozenset({"douleur abdominale intense", "fièvre", "vomissements"}),
        "Douleur abdominale intense + fièvre + vomissements — abdomen aigu probable, consultez aujourd'hui.",
        "digestive",
    ),
    (
        frozenset({"douleur abdominale", "fièvre élevée", "vomissements"}),
        "Douleur abdominale + fièvre élevée + vomissements — consultation urgente aujourd'hui.",
        "digestive",
    ),
    # Formes normalisées après NLP (douleur abdominale + nausées = vomissements normalisé)
    (
        frozenset({"douleur abdominale", "fièvre", "nausées"}),
        "Douleur abdominale + fièvre + nausées/vomissements — abdomen aigu probable, consultez aujourd'hui.",
        "digestive",
    ),
    (
        frozenset({"douleur abdominale", "fièvre", "vomissements"}),
        "Douleur abdominale + fièvre + vomissements — abdomen aigu probable, consultez aujourd'hui.",
        "digestive",
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
    "vascular":      "Alerte vasculaire",  # NEW
}

# ── Urgency level par catégorie ───────────────────────────────────────────────
# Utilisé par orchestrator pour forcer le minimum action level
# EMERGENCY = appel 15 immédiat
# URGENT = consultation aujourd'hui (min URGENT_MEDICAL_REVIEW)
RFE_URGENCY: dict[str, str] = {
    "cardiac":       "EMERGENCY",
    "respiratory":   "EMERGENCY",
    "neurological":  "EMERGENCY",
    "vascular":      "EMERGENCY",
    "infectious":    "EMERGENCY",
    "digestive":     "URGENT",      # abdomen aigu → URGENT_MEDICAL_REVIEW minimum
    "systemic":      "EMERGENCY",
}


class RFEResult:
    __slots__ = ("emergency", "urgent", "reason", "category", "urgency_override")

    def __init__(
        self,
        emergency: bool,
        reason: str = "",
        category: str = "",
        urgency_override: str = "",
        urgent: bool = False,
    ):
        self.emergency = emergency
        self.urgent = urgent          # True = urgent but NOT appel 15
        self.reason = reason
        self.category = category
        self.urgency_override = urgency_override  # "EMERGENCY" | "URGENT" | ""


def run(symptoms: list[str]) -> RFEResult:
    """
    Vérifie la présence de red flags dans la liste de symptômes.
    Retourne RFEResult(emergency=True, ...) si danger immédiat.
    Retourne RFEResult(emergency=False) si tout est normal — le pipeline continue.

    urgency_override est toujours rempli si triggered — utilisé par orchestrator
    pour interdire LOW_RISK_MONITOR et MEDICAL_REVIEW quand RFE = high-risk.
    """
    symptom_set = set(symptoms)

    # 1. Red flags isolés
    for flag, (reason, category) in _RED_FLAGS.items():
        if flag in symptom_set:
            urgency = RFE_URGENCY.get(category, "EMERGENCY")
            return RFEResult(emergency=True, reason=reason, category=category, urgency_override=urgency)

    # 2. Combinaisons dangereuses
    for combo, reason, category in _RED_FLAG_COMBOS:
        if combo.issubset(symptom_set):
            urgency = RFE_URGENCY.get(category, "EMERGENCY")
            return RFEResult(emergency=True, reason=reason, category=category, urgency_override=urgency)

    # 3. Urgent combos (non-emergency — consultation today, not appel 15)
    for combo, reason, category in _URGENT_COMBOS:
        if combo.issubset(symptom_set):
            return RFEResult(
                emergency=False,
                urgent=True,
                reason=reason,
                category=category,
                urgency_override="URGENT",
            )

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
        ["douleur", "poitrine", "thorax", "chest"],
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
    # Palpitations + douleur THORACIQUE → arythmie / SCA
    (
        ["palpitation", "cœur qui bat", "coeur qui bat", "tachycardie", "arythmie"],
        ["poitrine", "thorax", "thoracique", "oppression", "chest"],
        "Palpitations avec douleur thoracique — suspicion SCA ou arythmie, consultation urgente.",
        "cardiac",
    ),
    # Céphalée en coup de tonnerre → hémorragie sous-arachnoïdienne
    (
        ["tête", "crâne", "céphalée", "cephale", "tete"],
        ["violent", "brutal", "jamais eu", "pire", "plus violent", "vie", "coup de tonnerre", "soudain", "explosif"],
        "Céphalée d'intensité maximale brutale — suspicion d'hémorragie cérébrale, appel du 15.",
        "neurological",
    ),
    # Gonflement gorge / anaphylaxie → œdème de Quincke
    (
        ["gonflement", "enfle", "enflé", "enflée", "gonfle"],
        ["gorge", "langue", "respirer", "avaler", "déglutir", "anaphylaxie"],
        "Œdème de la gorge avec difficultés respiratoires — suspicion d'anaphylaxie, appel du 15.",
        "respiratory",
    ),
    # Raideur nuque + fièvre → méningite
    (
        ["nuque", "raideur", "cou raide", "méningite", "meningite"],
        ["fièvre", "fever", "température", "chaud"],
        "Raideur de nuque avec fièvre — suspicion de méningite, appel du 15.",
        "neurological",
    ),
    # Idées suicidaires / crise psychiatrique
    (
        ["tuer", "suicid", "veux mourir", "fin de vie", "mettre fin", "mourir", "me tuer"],
        ["je", "veux", "envie", "pensées", "moi", "me", "j'ai", "j ai"],
        "Idées suicidaires exprimées — orientation vers le 15 ou le 3114 (numéro national prévention suicide).",
        "systemic",
    ),
    # Troubles de la parole brutaux → AVC
    (
        ["parler", "parole", "s'exprimer", "exprimer", "aphasi", "dysarthr", "mot", "articuler"],
        ["difficult", "impossible", "plus", "soudain", "brutal", "perd", "plus capable", "plus pouvoir"],
        "Trouble de la parole brutal — suspicion d'AVC, appel du 15 immédiat.",
        "neurological",
    ),
    # Cyanose / lèvres bleues → hypoxie sévère
    (
        ["lèvres bleues", "lèvres bleutées", "lèvres violacées", "cyanose", "bleu", "bleutées", "bleues"],
        ["essoufflement", "respir", "souffle", "oxygène", "air", "repos"],
        "Cyanose avec essoufflement — hypoxie sévère, appel du 15 immédiat.",
        "respiratory",
    ),
    # Essoufflement au repos seul → détresse respiratoire
    (
        ["essoufflement", "respir", "souffle"],
        ["repos", "allongé", "assis", "sans effort", "immobile"],
        "Essoufflement au repos — détresse respiratoire possible, appel du 15.",
        "respiratory",
    ),
    # Jambe gonflée + symptômes thoraciques → TVP + embolie pulmonaire
    (
        ["jambe", "mollet", "cuisse"],
        ["essoufflement", "thoracique", "poitrine", "chest", "oppression"],
        "Jambe gonflée avec signes thoraciques — suspicion d'embolie pulmonaire, appel du 15.",
        "cardiac",
    ),
    # Purpura non-résolutif + fièvre → méningococcémie
    (
        ["taches", "purpura", "pétéchies", "petechies", "tache rouge", "boutons rouges"],
        ["disparaiss", "efface", "presse", "fièvre", "fever", "température"],
        "Purpura fébrile non résolutif — suspicion de méningococcémie, appel du 15 immédiat.",
        "infectious",
    ),
    # Vomissement de sang → hémorragie digestive haute
    (
        ["vomissement", "vomit", "vomi", "je vomis", "crache"],
        ["sang", "rouge", "noirâtre", "noir", "café", "hémorrhag", "hématémèse"],
        "Vomissement de sang — hémorragie digestive haute, appel du 15 immédiat.",
        "digestive",
    ),
    # NEW: Dissection aortique → douleur thoracique + dos + déchirure
    (
        ["douleur", "poitrine", "thorax", "thoracique", "chest"],
        ["dos", "dorsale", "déchirure", "déchire", "arrière", "inter-scapulaire", "déchirement"],
        "Douleur thoracique + dorsale avec sensation de déchirure — suspicion dissection aortique, appel du 15.",
        "vascular",
    ),
    # NEW: AVC — faiblesse + trouble parole (texte brut)
    (
        ["faiblesse", "faible", "force", "bras", "main", "côté"],
        ["parler", "parole", "mot", "s'exprimer", "comprendre", "langage", "bouche", "visage", "sourire"],
        "Faiblesse + trouble de la parole — suspicion d'AVC, appel du 15 immédiat.",
        "neurological",
    ),
    # NEW: TVP isolée — jambe unilatérale + mollet (sans signes thoraciques)
    (
        ["jambe", "mollet", "cuisse", "veine"],
        ["unilatéral", "unilatérale", "une seule", "gonflé", "gonflée", "rouge", "chaud", "chaude", "douleur"],
        "Jambe unilatérale gonflée/douloureuse — suspicion TVP, consultation urgente aujourd'hui.",
        "vascular",
    ),
    # NOTE: Abdomen aigu sans défense → géré par _URGENT_COMBOS (non-emergency)
    # Pas de pattern ici pour éviter false EMERGENCY via check_red_flags()
    # NEW: Méningite — céphalée + raideur nuque + photophobie
    (
        ["tête", "céphalée", "mal de tête", "tete"],
        ["nuque", "raideur", "photophobie", "lumière", "lumiere", "raide", "cou"],
        "Céphalée avec raideur de nuque — suspicion méningite/HSA, appel du 15.",
        "neurological",
    ),
    # NEW: Sueurs froides + douleur/poitrine → SCA
    (
        ["sueurs froides", "sueur froide", "en sueur froid"],
        ["poitrine", "thorax", "douleur", "chest", "oppression", "cardiaque"],
        "Sueurs froides avec symptômes thoraciques — suspicion SCA, appel du 15.",
        "cardiac",
    ),
    # NEW: Oppression thoracique + nausées/sueurs → SCA
    (
        ["oppression thoracique", "étau thoracique", "serre dans la poitrine", "serre dans le thorax", "serrement poitrine"],
        ["nausée", "nausee", "sueur", "vomit", "malaise", "bras", "mâchoire"],
        "Oppression/serrement thoracique — suspicion SCA, appel du 15.",
        "cardiac",
    ),
    # NEW: ça serre dans la poitrine → SCA atypique
    (
        ["serre", "étau", "pression"],
        ["poitrine", "thorax", "chest"],
        "Serrement thoracique — suspicion SCA, appel du 15.",
        "cardiac",
    ),
    # NEW: Allergie + dyspnée/respiration → anaphylaxie
    (
        ["allergi", "urticaire", "allergique"],
        ["respir", "souffle", "dyspnée", "dyspnee", "essouffl", "gonfle", "gorge", "levres", "lèvres"],
        "Allergie avec détresse respiratoire — suspicion anaphylaxie, appel du 15.",
        "respiratory",
    ),
    # NEW: Gorge serrée/qui ferme + déglutition → anaphylaxie
    (
        ["gorge", "glotte", "pharynx"],
        ["serre", "serrée", "ferme", "bloque", "bloquée", "avaler", "déglutir", "respir", "voix"],
        "Gorge serrée avec difficulté respiratoire/déglutition — suspicion anaphylaxie, appel du 15.",
        "respiratory",
    ),
    # NEW: Méningite — fièvre + nuque/raideur sans céphalée explicite
    (
        ["fièvre", "fever", "température", "chaud"],
        ["nuque", "raideur", "cou raide", "méningite", "photophobie", "lumière"],
        "Fièvre + raideur nuque/photophobie — suspicion méningite, appel du 15.",
        "neurological",
    ),
    # NEW: Confusion + fièvre → méningite/sepsis
    (
        ["confus", "désorienté", "desorientation", "perdu", "bizarre"],
        ["fièvre", "fever", "température", "chaud", "mal tête", "céphalée"],
        "Confusion avec fièvre — suspicion méningite/sepsis, appel du 15.",
        "neurological",
    ),
    # NEW: Photophobie + fièvre
    (
        ["photophobie", "lumière", "lumiere", "yeux", "sensible"],
        ["fièvre", "fever", "température", "vomit", "nausée", "tête", "céphalée"],
        "Photophobie avec fièvre — suspicion méningite, appel du 15.",
        "neurological",
    ),
    # NEW: Bras qui ne répond plus → AVC
    (
        ["bras", "main", "membre", "côté"],
        ["répond", "repond", "bouge", "paralyse", "paralysé", "lourd", "force", "plus"],
        "Bras qui ne répond plus — suspicion AVC, appel du 15.",
        "neurological",
    ),
]


# Prefixes de négation — si un mot-clé est précédé de ces mots → ignorer
_NEGATION_PREFIXES = [
    "pas de ", "pas d'", "pas d ", "sans ", "aucun ", "aucune ",
    "absence de ", "absence d'", "no ", "not ", "ni ",
]


def _has_negated(text: str, word: str) -> bool:
    """Retourne True si le mot est précédé d'une négation dans le texte."""
    idx = text.find(word)
    if idx == -1:
        return False
    prefix = text[max(0, idx-15):idx]
    return any(neg in prefix for neg in _NEGATION_PREFIXES)


def check_red_flags(symptoms_text: str) -> dict:
    """
    Vérifie le texte brut pour des patterns d'urgence AVANT le traitement NLP.
    Doit être appelé en premier, avant toute autre logique diagnostique.

    Retourne dict avec :
      triggered         : bool
      action            : "EMERGENCY" | absent
      block_reassurance : bool — masquer tout texte rassurant
      message           : str — message visible utilisateur
      reason            : str — raison technique
      category          : str — type d'urgence
    """
    text = symptoms_text.lower()

    for primary_words, secondary_words, reason, category in RED_FLAG_PATTERNS:
        has_primary = any(w in text and not _has_negated(text, w) for w in primary_words)
        has_secondary = any(w in text and not _has_negated(text, w) for w in secondary_words)
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