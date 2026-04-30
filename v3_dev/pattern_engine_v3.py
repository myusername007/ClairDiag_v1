"""
ClairDiag v3 — Pattern Engine v1.1.0

Pre-triage layer: детектує клінічні патерни на normalized free text.
Підключається в core.py ПЕРЕД AND-triggers і urgent_triggers.

Покриває:
  PE-01: anticoagulant + trauma crânien → urgent
  PE-02: saignement abondant + malaise → urgent
  PE-03: fatigue brutale + essoufflement → urgent
  PE-04: confusion + fièvre → medical_urgent
  PE-05: douleur thoracique (ANCHOR-RESIST) → urgent
  PE-06: sang dans selles → medical_urgent
  PE-07: céphalée thunderclap → urgent
  PE-08: vertige + faiblesse membre → urgent (AVC)
  PE-09: orthopnée / IC décompensée → urgent
  PE-10: syncope → urgent
  PE-11: FAST/AVC (bouche, parole, visage) → urgent  [NEW]
  PE-12: méningite (nuque raide + fièvre / purpura) → urgent  [NEW]
  PE-13: sepsis (fièvre + confusion + faiblesse âgé) → urgent  [NEW]
  PE-14: neutropénie sous chimio + fièvre → urgent  [NEW]
  PE-15: GEU (règles retard + douleur ventre) → urgent_medical_review  [NEW]
  PE-16: dissection aortique (douleur déchirante dos/épaules) → urgent  [NEW]
  PE-17: DVT / EP (mollet + essoufflement; post-op/post-partum) → urgent  [NEW]
  PE-18: prééclampsie (enceinte + céphalée + troubles visuels) → urgent  [NEW]
  PE-19: HSD (âgé + confusion + chute) → urgent  [NEW]
  PE-20: hémorragie digestive haute (anticoag + vertiges + selles noires) → urgent_medical_review  [NEW]
  PE-21: idéation suicidaire → urgent  [NEW]
  PE-22: hémoptysie → urgent_medical_review  [NEW]
  PE-23: pyélonéphrite (brûlure + fièvre + dos) → urgent_medical_review  [NEW]
  PE-24: ischémie mésentérique (douleur ventre soudaine + âge/ACFA) → urgent_medical_review  [NEW]

Architecture:
  run_pattern_engine(text, patient_context) →
    {"triggered": bool, "urgency": str, "pattern_id": str,
     "pattern_name": str, "pattern_triggered": True, "message": str}
  ou None si pas de match.

Règles:
  - Ne modifie jamais v2 core
  - Ne touche pas urgent_triggers_v1.json ni and_triggers.py
  - Retourne uniquement urgent / medical_urgent / urgent_medical_review
  - Chaque pattern est tracé et explicable
"""

from typing import Dict, List, Optional, Tuple


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _any(tokens: List[str], text: str) -> Optional[str]:
    """Retourne le premier token trouvé dans le texte."""
    for t in tokens:
        if t in text:
            return t
    return None


def _all(tokens: List[str], text: str) -> bool:
    """Vrai si tous les tokens sont présents."""
    return all(t in text for t in tokens)


def _age_from_context(patient_context: Optional[Dict]) -> Optional[int]:
    try:
        return int(patient_context.get("age", 0)) if patient_context else None
    except (TypeError, ValueError):
        return None


# ── Token groups ─────────────────────────────────────────────────────────────────

_ANTICOAG = [
    "anticoagulant", "anticoagulants", "aod", "apixaban", "rivaroxaban",
    "dabigatran", "warfarine", "warfarin", "heparine", "xarelto", "eliquis",
    "sous anticoagulant", "traitement anticoagulant",
]

_TRAUMA_CRANE = [
    "trauma cranien", "traumatisme cranien", "choc tete", "coup tete",
    "hematome tete", "chute tete", "hematome crane", "bosse tete",
    "chute avec hematome tete", "chute + hematome", "blessure tete",
    "traumatisme cranien", "hematome cranien",
    "chute hier tete", "chute tete hier",
    "chute sur la tete", "tombe sur la tete",
    "chute et tete", "tete a cogne", "tete a tape",
    "cogne la tete", "tape la tete",
]

_CHUTE = [
    "chute", "tombe", "est tombe", "suis tombe", "tombee",
    "a chute", "ai chute", "il est tombe", "elle est tombee",
]

_CONFUSION = [
    "confusion", "confus", "confuse", "desoriente", "desorientation",
    "pas coherent", "ne repond plus", "regard vide", "perdu",
    "plus coherent", "bizarre", "etrange comportement",
    "ne reconnait pas", "ne reconnait plus", "ne sait plus ou il est",
    "somnolent", "somnolente", "endormi", "endormie", "difficile a reveiller",
    "ne se reveille pas bien", "dort beaucoup", "pas reveille",
]

_SAIGNEMENT_ABONDANT = [
    "saignement abondant", "saigne beaucoup", "hemorragie", "perte de sang",
    "saignement important", "sang partout", "saigne enormement",
    "beaucoup de sang", "saignement grave",
]

_MALAISE = [
    "malaise", "je me sens mal", "pas bien", "evanouissement",
    "vertiges", "faiblesse soudaine", "tourne", "tourneboule",
    "failli tomber", "failli perdre connaissance",
]

_FATIGUE_BRUTALE = [
    "fatigue brutale", "fatigue soudaine", "fatigue subite",
    "fatigue brusque", "epuisement brutal", "epuisement soudain",
    "fatigue d'un coup", "fatigue tout d'un coup",
]

_ORTHOPNEE_TOKENS = [
    "dors assis", "dormir assis", "je dors assis",
    "impossible de m allonger", "ne peut pas s allonger",
    "sinon je suffoque", "sinon ca etouffe", "sinon j etouffe",
    "plusieurs oreillers", "4 oreillers", "3 oreillers",
    "tete surelevee pour dormir",
]

_OEDEME_JAMBES = [
    "jambes gonflees", "jambes gonflees", "chevilles gonflees",
    "chevilles gonflees", "oedeme jambes", "oedeme jambes",
    "jambes enflees", "pieds gonfles", "pieds gonfles",
]

_SYNCOPE_TOKENS = [
    "perdu connaissance", "perte de connaissance", "syncope",
    "je me suis evanoui", "je me suis evanouie", "evanoui",
    "suis tombe dans les pommes", "dans les pommes",
    "j ai perdu connaissance", "j'ai perdu connaissance",
    "j ai perdu connaissanc",
]

_ESSOUFFLEMENT = [
    "essoufflement", "essoufle", "essouflee", "essouffle", "essoufflee",
    "souffle court", "manque de souffle", "j'etouffe", "j etouffe",
    "du mal a respirer", "mal a respirer", "respire mal",
    "respiration difficile", "respire pa bien", "respire pas bien",
    "etouffe", "ca etouffe", "suffoque", "je suffoque",
    "dors assis", "dormir assis",
    "tres essoufflee", "tres essoufle",
]

_FIEVRE = [
    "fievre", "temperature", "j'ai chaud", "chaud et froid",
    "frissons", "etat febrile", "je fais de la temperature",
    "je fais de la fievre", "38", "39", "40",
    "38.2", "38.5", "38.7", "39.5",
]

_DOULEUR_THORACIQUE = [
    "douleur thoracique", "douleur poitrine", "mal poitrine",
    "douleur au coeur", "oppression poitrine", "serrement poitrine",
    "ca serre poitrine", "ca serre", "mal a la poitrine",
    "douleur au niveau du coeur", "oppression thoracique",
    "mal dans la poitrine", "mal au niveau de la poitrine",
    "douleur dans la poitrine", "douleur dans le thorax",
    "ca fait mal dans la poitrine", "ca fait mal poitrine",
    "j ai mal a la poitrine", "j ai mal poitrine",
    "douleur au sternum", "sternum douloureux",
    # palpitations seules ne suffisent pas → couvertes par PE-36 anchor
    "le coeur qui serre", "coeur qui serre",
    "le c\u0153ur qui serre", "c\u0153ur qui serre",
    "le coeur serre", "coeur serre",
]

_SANG_SELLES = [
    "sang dans les selles", "selles avec sang", "sang selles",
    "rectorragie", "sang rouge selles", "sang dans selles",
    "sang au niveau des selles", "selles sanglantes",
    "sang rectum", "saignement rectal", "saigne en allant aux toilettes",
    "je saigne quand je vais aux toilettes",
    "saigne aux toilettes", "saigne quand je vais",
    "sang dans les wc", "sang dans les toilettes",
    "du sang quand je vais aux toilettes",
    "saigne apres les selles", "saignement apres selles",
]

_CEPHALEE_BRUTAL = [
    "mal de tete violent soudain", "cephalee violente soudaine",
    "mal tete brutal", "migraine violente soudaine",
    "jamais eu ca", "pire de ma vie", "mal de tete pire",
    "tete qui eclate soudainement", "coup de tonnerre",
    "douleur tete soudaine violente", "cephalee brutale",
    "cephalee foudroyante",
    # IND-002: "apparu d'un coup"
    "apparu d'un coup", "apparu d un coup",
    "arrive d'un coup", "arrive d un coup",
    "d'un coup", "d un coup",  # contexte tête requis → combo ci-dessous
]

_CEPHALEE_THUNDER_COMBO: List[Tuple[str, str]] = [
    ("mal de tete", "jamais eu ca"),
    ("mal de tete", "jamais eu ca"),
    ("cephalee", "jamais eu ca"),
    ("cephalee", "jamais eu ca"),
    ("tete", "jamais eu ca"),
    ("tete", "jamais eu ca"),
    ("mal tete", "violent"),
    ("mal de tete", "violent"),
    ("cephalee", "violent"),
    ("cephalee", "brutale"),
    ("cephalee", "brutal"),
    ("tete", "coup de tonnerre"),
    ("tete", "pire de ma vie"),
    # IND-002: "très mal à la tête... apparu d'un coup"
    ("mal a la tete", "d'un coup"),
    ("mal a la tete", "d un coup"),
    ("mal tete", "d'un coup"),
    ("mal tete", "d un coup"),
    ("tete", "d'un coup"),
    ("tete", "d un coup"),
    # "depuis 1 heure" / "il y a 1 heure" = onset soudain
    ("mal a la tete", "depuis 1 heure"),
    ("mal a la tete", "il y a 1 heure"),
    ("mal a la tete", "brusquement"),
    ("cephalee", "brusquement"),
]

_VERTIGE = [
    "vertige", "vertiges", "tourne", "tete qui tourne",
    "etourdissement", "etourdissements", "tournis",
]

_FAIBLESSE_MEMBRE = [
    "faiblesse bras", "faiblesse jambe", "faiblesse membre",
    "bras faible", "jambe faible", "membre faible",
    "faiblesse d'un bras", "faiblesse du bras",
    "faiblesse d un bras", "bras qui lache",
    "force dans le bras", "perd la force",
    "bras droit faible", "bras gauche faible",
    "faiblesse dans le bras", "faiblesse dans la jambe",
    "bras qui ne repond plus", "jambe qui ne repond plus",
    # IND-012: "faiblesse dans le bras droit"
    "faiblesse dans le bras", "bras droit", "bras gauche",
    "dans le bras", "dans la jambe",
]

# ── NEW token groups ─────────────────────────────────────────────────────────────

# PE-11: FAST / AVC
_FAST_VISAGE = [
    "bouche qui se deforme", "bouche deformee", "visage qui se deforme",
    "visage deforme", "coin de la bouche", "bouche tombante",
    "asymetrie visage", "visage asymetrique", "facial asymetrique",
    "sourire asymetrique", "bouche tordue",
]
_FAST_PAROLE = [
    "n'arrive plus a parler", "narrive plus a parler", "ne parle plus",
    "parole difficile", "du mal a parler", "difficulte a parler",
    "mots qui sortent pas", "mots qui ne sortent pas",
    "ne comprend plus", "langage trouble", "aphasie",
    "bredouille", "ne trouve plus ses mots", "ne trouve pas ses mots",
    "mots difficiles", "n'arrive pas a parler",
    # IND-040: "je n'arrivais plus à trouver mes mots"
    "trouver mes mots", "trouver les mots",
]
_FAST_CONTEXTE_SOUDAIN = [
    "depuis 20 minutes", "depuis 20 mn", "il y a 20 minutes",
    "depuis quelques minutes", "depuis 1 heure", "d'un coup", "d un coup",
    "soudain", "soudainement", "brusquement", "tout d'un coup",
    "depuis hier", "hier soir",
]

# PE-12: méningite
_NUQUE = [
    "nuque raide", "nuque douloureuse", "raideur nuque",
    "nuque qui fait mal", "douleur nuque", "raideur de la nuque",
    "nuque bloquee",
]
_PURPURA = [
    "taches rouges", "petites taches", "taches qui ne disparaissent pas",
    "taches pourpres", "purpura", "taches cutanees", "taches rouges qui apparaissent",
    "petechies",
]

# PE-13: sepsis
_SEPSIS_FAIBLESSE = [
    "tres faible", "tres fatigue", "fatigue extreme", "ne se leve plus",
    "alite", "ne peut pas se lever", "prostration", "abattement",
    "se sent vraiment pas bien", "vraiment pas bien",
    "ne tient plus debout", "s'est couche", "couche depuis",
    "vraiment faible", "vraiment mal",
    "du mal a respirer", "mal a respirer",
]
_SEPSIS_CONTEXTE = [
    "infection", "plaie", "operer", "opere", "catheter", "sonde",
    "hospitalise", "hospital", "drepanocytose", "immunodeprime",
    "diabetique", "diabete",
]

# PE-14: neutropénie/chimio
_CHIMIO_TOKENS = [
    "chimio", "chimiotherapie", "traitement du cancer", "cancer du sein",
    "leucemie", "lymphome", "cancer", "sous chimio", "en chimio",
    "traitement oncologique", "immunosuppresseur", "immunosupprime",
    "greffe", "transplante",
]

# PE-15: GEU
_REGLES_RETARD = [
    "regles en retard", "retard de regles", "pas eu mes regles",
    "pas de regles", "regles absentes", "amenorrhee",
    "retard menstruel", "pas de menstruations",
    "test de grossesse", "test grossesse",
    "enceinte", "je suis enceinte", "grossesse",
    # IND-017: "mes règles sont en retard de 10 jours"
    "mes regles sont en retard", "regles sont en retard",
    "regles en retard de", "retard de 10", "retard de 15",
]
_DOULEUR_VENTRE_LATERALE = [
    "douleur ventre cote droit", "douleur cote droit",
    "mal ventre cote droit", "douleur ventre cote gauche",
    "douleur cote gauche", "mal ventre cote gauche",
    "douleur abdominale cote", "douleur flanc",
    "mal au ventre", "douleur abdominale", "douleur dans le ventre",
    "mal dans le ventre", "ventre qui fait mal",
]

# PE-16: dissection aortique
_DISSECTION_TOKENS = [
    "douleur dechirante", "douleur en eclair", "douleur qui dechire",
    "douleur qui irradie", "douleur dans le dos", "douleur dos",
    "douleur entre les epaules", "douleur dos qui descend",
    "douleur derriere", "douleur interscapulaire",
    "dos qui fait mal d'un coup", "douleur tres forte dos",
    "douleur forte entre les epaules",
    "douleur forte dos", "douleur soudaine dos",
    # IND-030: "douleur très forte entre les épaules d'un coup"
    "forte entre les epaules", "entre les epaules",
    "douleur tres forte entre", "tres forte entre les epaules",
]
_DISSECTION_SOUDAIN = [
    "d'un coup", "d un coup", "soudain", "brusquement", "tout d'un coup",
    "instantanement", "subitement",
]

# PE-17: DVT / EP
_MOLLET_TOKENS = [
    "mollet gonfle", "mollet douloureux", "mollet chaud",
    "jambe gonflée et douloureuse", "jambe gonflée",
    "gonflement mollet", "douleur mollet",
    "mollet droit gonfle", "mollet gauche gonfle",
    "veine gonflée", "veine dure",
    # IND-025: "mollet droit qui est gonflé, chaud et douloureux"
    "mollet", "gonfle",
]
_CONTEXTE_THROMBOSE = [
    "opere", "operation", "post-op", "post op", "postoperatoire",
    "alitement", "alite", "long voyage", "voyage avion", "avion",
    "accouche", "accouchement", "post-partum", "post partum",
    "vient d'accoucher", "viens d accoucher",
    "bpco", "cancer", "chimio",
    "immobilise", "immobilisation",
]
_DOULEUR_COTE_THORAX = [
    "douleur cote", "mal sur le cote", "douleur flanc thoracique",
    "cote qui fait mal", "douleur laterale thorax",
    "point de cote", "douleur pleurale",
]

# PE-18: prééclampsie
_GROSSESSE_AVANCEE = [
    "enceinte de 5 mois", "enceinte de 6 mois", "enceinte de 7 mois",
    "enceinte de 8 mois", "enceinte de 9 mois",
    "5 mois de grossesse", "6 mois de grossesse", "7 mois de grossesse",
    "8 mois de grossesse", "9 mois de grossesse",
    "enceinte", "grossesse",  # + céphalée + signes visuels = suffisant
]
_TROUBLES_VISUELS_AIT = [
    "vu trouble", "vu flou", "vision trouble", "vision floue",
    "voir flou", "voir trouble", "voir double",
    "perte de vision", "ne voyait plus", "ne voit plus",
    "yeux qui voient flou", "oeil trouble",
    # IND-026: "vu trouble d'un oeil"
    "trouble d'un oeil", "trouble d un oeil",
    "trouble d'un", "flou d'un oeil",
    "amaurose", "voir moins bien",
]
_TROUBLES_VISUELS_PREECLAMP = [
    "voir des etoiles", "voit des etoiles", "etoiles",
    "points noirs", "brouillard visuel", "vision trouble",
    "vision floue", "voir flou", "eclairs visuels",
    "phosphenes", "mouchettes",
]
# AIT transitoire
_AIT_TRANSITOIRE = [
    "pendant quelques minutes", "pendant 20 minutes", "pendant 30 minutes",
    "ca a passe", "c'est passe", "maintenant ca va", "disparu",
    "transitoire", "quelques minutes", "fugace",
    "pendant une heure", "pendant 10 minutes",
    "hier soir", "ce matin", "hier",
]
_CEPHALEE_GROSSESSE = [
    "mal a la tete", "mal de tete", "cephalee", "tete qui fait mal",
    "tete qui explose", "migraine",
]

# PE-19: HSD (hématome sous-dural)
_SUJET_AGE = [
    "70 ans", "71 ans", "72 ans", "73 ans", "74 ans",
    "75 ans", "76 ans", "77 ans", "78 ans", "79 ans", "80 ans",
    "81 ans", "82 ans", "83 ans", "84 ans", "85 ans", "86 ans",
    "87 ans", "88 ans", "89 ans", "90 ans",
    "mon pere", "ma mere", "mon grand-pere", "ma grand-mere",
    "personne agee", "sujet age", "une personne agee",
]
_SYMPTOMES_HSD = [
    "somnolent", "somnolente", "confusion", "confus", "confuse",
    "maux de tete persistants", "mal de tete qui dure",
    "cephalee progressive", "cephalee qui augmente",
    "ne repond plus bien",
]

# PE-20: hémorragie digestive haute
_SELLES_NOIRES = [
    "selles noires", "selles foncees", "selles tres foncees",
    "selles comme du goudron", "melena", "selles noires goudron",
    "selles plus foncees", "selles plus sombres",
    "selles foncees que d habitude", "selles foncees que d'habitude",
    "un peu plus foncees", "plus foncees que d habitude",
    "plus foncees que d'habitude",
    # IND-020: "mes selles sont noires"
    "selles sont noires", "selles sont foncees", "selles sont tres foncees",
]
_HEMATEMESE = [
    "vomit du sang", "vomissement de sang", "vomissements sanglants",
    "hematemese", "cafe moulu", "vomit rouge",
]
_VERTIGE_FAIBLESSE = [
    "vertige", "vertiges", "failli tomber", "failli perdre connaissance",
    "faiblesse", "malaise", "se sentir mal",
]

# PE-21: idéation suicidaire
_SUICIDAL_TOKENS = [
    "en finir avec ma vie", "en finir avec la vie", "mettre fin a ma vie",
    "mettre fin a mes jours", "me suicider", "penser au suicide",
    "idees noires", "pensees suicidaires", "ne veux plus vivre",
    "veux mourir", "je veux mourir", "penser a mourir",
    "idees de mort", "envie de mourir",
]

# PE-22: hémoptysie
_HEMOPTYSIE_TOKENS = [
    "sang dans les crachats", "crachat sanguin", "crachats avec sang",
    "hemoptysie", "sang quand je tousse", "je crache du sang",
    "crachat rouge", "sang en toussant",
    # IND-035
    "sang dans mes crachats", "du sang dans mes crachats",
    "sang dans les expectorations",
]

# PE-23: pyélonéphrite
_BRULURE_URINAIRE = [
    "brulure urinaire", "brulure quand j urine", "brulure pipi",
    "ca brule quand je fais pipi", "douleur urinaire",
    "brulure en urinant", "ca fait mal quand j urine",
    "cystite", "infection urinaire",
    # IND-021: "des brûlures quand je fais pipi"
    "brulures quand je fais pipi", "brulures pipi",
    "brulures quand j urine", "brulures urinaires",
    "brulure", "brulures",
]
_DOULEUR_DOS_LOMBAIRE = [
    "douleur lombaire", "douleur dos", "mal aux reins", "reins qui font mal",
    "douleur dans le dos", "dos douloureux", "lombalgies",
    "flanc qui fait mal", "douleur flanc",
    # IND-021: "mal au dos"
    "mal au dos", "mal dans le dos", "dos qui fait mal",
]

# PE-24: ischémie mésentérique
_DOULEUR_VENTRE_SOUDAINE = [
    "tres mal au ventre", "douleur abdominale intense", "douleur ventre intense",
    "douleur abdominale soudaine", "douleur ventre soudaine",
    "douleur ventre brutale", "douleur abdominale brutale",
    "douleur abdo intense", "ventre qui fait tres mal",
    # IND-023: "très mal au ventre depuis ce matin, ça a commencé d'un coup"
    "mal au ventre", "douleur abdominale",  # + soudain = suffisant
]
_CONTEXTE_VASCULAIRE = [
    "fibrillation auriculaire", "acfa", "fa cardiaque", "arythmie",
    "troubles du rythme", "pace maker", "stent", "pontage",
    "arteriosclerose", "atherosclerose",
    "70 ans", "71 ans", "72 ans", "73 ans", "74 ans", "75 ans",
    "76 ans", "77 ans", "78 ans", "79 ans", "80 ans",
]


# ── Pattern functions ─────────────────────────────────────────────────────────────

def _check_anticoag_trauma_head(text: str, _ctx=None) -> Optional[Dict]:
    """PE-01: anticoagulant + trauma crânien → urgent"""
    ac = _any(_ANTICOAG, text)
    if not ac:
        return None
    tc = _any(_TRAUMA_CRANE, text)
    if tc:
        return {
            "pattern_id": "PE-01",
            "pattern_name": "Traumatisme crânien sous anticoagulant",
            "matched_tokens": {"anticoagulant": ac, "trauma": tc},
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "Traumatisme crânien sous anticoagulant : "
                "imagerie cérébrale urgente — risque d'hématome sous-dural."
            ),
        }
    conf = _any(_CONFUSION, text)
    chute = _any(_CHUTE, text)
    if conf and chute:
        return {
            "pattern_id": "PE-01b",
            "pattern_name": "Chute + confusion sous anticoagulant",
            "matched_tokens": {"anticoagulant": ac, "confusion": conf, "chute": chute},
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "Chute avec confusion sous anticoagulant : "
                "évaluation médicale urgente — hématome intracrânien à exclure."
            ),
        }
    return None


def _check_saignement_malaise(text: str, _ctx=None) -> Optional[Dict]:
    """PE-02: saignement abondant + malaise → urgent"""
    s = _any(_SAIGNEMENT_ABONDANT, text)
    if not s:
        return None
    m = _any(_MALAISE, text)
    if not m:
        return None
    return {
        "pattern_id": "PE-02",
        "pattern_name": "Hémorragie avec malaise",
        "matched_tokens": {"saignement": s, "malaise": m},
        "urgency": "urgent",
        "pattern_triggered": True,
        "message": (
            "Saignement abondant avec malaise : "
            "évaluation médicale urgente — risque d'état de choc."
        ),
    }


def _check_orthopnee_ic(text: str, _ctx=None) -> Optional[Dict]:
    """PE-09: orthopnée → urgent (IC décompensée)"""
    o = _any(_ORTHOPNEE_TOKENS, text)
    if not o:
        return None
    e = _any(_ESSOUFFLEMENT, text)
    oed = _any(_OEDEME_JAMBES, text)
    if not e and not oed:
        return None
    return {
        "pattern_id": "PE-09",
        "pattern_name": "Orthopnée / IC décompensée",
        "matched_tokens": {"orthopnee": o, "essoufflement_ou_oedeme": e or oed},
        "urgency": "urgent",
        "pattern_triggered": True,
        "message": (
            "Orthopnée avec essoufflement ou oedèmes : "
            "consultation urgente — insuffisance cardiaque décompensée à exclure."
        ),
    }


def _check_syncope(text: str, _ctx=None) -> Optional[Dict]:
    """PE-10: syncope → urgent"""
    s = _any(_SYNCOPE_TOKENS, text)
    if not s:
        return None
    return {
        "pattern_id": "PE-10",
        "pattern_name": "Syncope / perte de connaissance",
        "matched_tokens": {"syncope": s},
        "urgency": "urgent",
        "pattern_triggered": True,
        "message": (
            "Perte de connaissance : évaluation médicale urgente — "
            "cause cardiaque, neurologique ou métabolique à exclure."
        ),
    }


def _check_fatigue_brutale_essoufflement(text: str, _ctx=None) -> Optional[Dict]:
    """PE-03: fatigue brutale + essoufflement → urgent"""
    f = _any(_FATIGUE_BRUTALE, text)
    if not f:
        return None
    e = _any(_ESSOUFFLEMENT, text)
    if not e:
        return None
    return {
        "pattern_id": "PE-03",
        "pattern_name": "Fatigue brutale + essoufflement",
        "matched_tokens": {"fatigue_brutale": f, "essoufflement": e},
        "urgency": "urgent",
        "pattern_triggered": True,
        "message": (
            "Fatigue brutale avec essoufflement : "
            "consultation urgente — décompensation cardiaque ou embolie à exclure."
        ),
    }


def _check_thunderclap_headache(text: str, _ctx=None) -> Optional[Dict]:
    """PE-07: céphalée thunderclap → urgent (HSA)"""
    direct = _any(_CEPHALEE_BRUTAL, text)
    if direct:
        # "d'un coup" seul sans contexte tête = pas thunderclap
        if direct in ("d'un coup", "d un coup", "arrive d'un coup", "arrive d un coup",
                      "apparu d'un coup", "apparu d un coup"):
            # Vérifier qu'il y a un contexte tête
            has_tete = any(t in text for t in ["tete", "cephalee", "migraine", "mal a la tete"])
            if not has_tete:
                pass  # continue vers les combos
            else:
                return {
                    "pattern_id": "PE-07",
                    "pattern_name": "Céphalée thunderclap (HSA suspectée)",
                    "matched_tokens": {"cephalee_brutale": direct},
                    "urgency": "urgent",
                    "pattern_triggered": True,
                    "message": (
                        "Céphalée violente soudaine : évaluation médicale immédiate — "
                        "hémorragie sous-arachnoïdienne à exclure en urgence."
                    ),
                }
        else:
            return {
                "pattern_id": "PE-07",
                "pattern_name": "Céphalée thunderclap (HSA suspectée)",
                "matched_tokens": {"cephalee_brutale": direct},
                "urgency": "urgent",
                "pattern_triggered": True,
                "message": (
                    "Céphalée violente soudaine : évaluation médicale immédiate — "
                    "hémorragie sous-arachnoïdienne à exclure en urgence."
                ),
            }
    for t1, t2 in _CEPHALEE_THUNDER_COMBO:
        if t1 in text and t2 in text:
            return {
                "pattern_id": "PE-07",
                "pattern_name": "Céphalée thunderclap (HSA suspectée)",
                "matched_tokens": {"token1": t1, "token2": t2},
                "urgency": "urgent",
                "pattern_triggered": True,
                "message": (
                    "Céphalée violente inhabituelle : évaluation médicale immédiate — "
                    "hémorragie sous-arachnoïdienne à exclure en urgence."
                ),
            }
    return None


def _check_vertige_faiblesse_membre(text: str, _ctx=None) -> Optional[Dict]:
    """PE-08: vertige + faiblesse membre → urgent (AVC)"""
    v = _any(_VERTIGE, text)
    if not v:
        return None
    f = _any(_FAIBLESSE_MEMBRE, text)
    if not f:
        return None
    return {
        "pattern_id": "PE-08",
        "pattern_name": "Vertige + faiblesse membre (AVC)",
        "matched_tokens": {"vertige": v, "faiblesse": f},
        "urgency": "urgent",
        "pattern_triggered": True,
        "message": (
            "Vertiges avec faiblesse d'un membre : évaluation médicale immédiate — "
            "AVC à exclure, chaque minute compte."
        ),
    }


def _check_douleur_thoracique_isolee(text: str, _ctx=None) -> Optional[Dict]:
    """PE-05: douleur thoracique → urgent (ANCHOR-RESIST)"""
    dt = _any(_DOULEUR_THORACIQUE, text)
    if not dt:
        return None
    return {
        "pattern_id": "PE-05",
        "pattern_name": "Douleur thoracique (ANCHOR-RESIST)",
        "matched_tokens": {"douleur_thoracique": dt},
        "urgency": "urgent",
        "pattern_triggered": True,
        "message": (
            "Douleur thoracique : évaluation médicale urgente — "
            "syndrome coronarien à exclure avant toute autre conclusion."
        ),
    }


# ── NEW patterns ─────────────────────────────────────────────────────────────────

def _check_fast_avc(text: str, _ctx=None) -> Optional[Dict]:
    """PE-11: FAST/AVC — bouche déformée, troubles de la parole, faiblesse membre → urgent"""
    v = _any(_FAST_VISAGE, text)
    p = _any(_FAST_PAROLE, text)

    if v:
        return {
            "pattern_id": "PE-11",
            "pattern_name": "FAST — asymétrie faciale (AVC)",
            "matched_tokens": {"visage": v},
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "Déformation du visage ou asymétrie faciale : AVC suspecté — "
                "appel immédiat du 15, chaque minute compte."
            ),
        }

    if p:
        ctx = _any(_FAST_CONTEXTE_SOUDAIN, text)
        return {
            "pattern_id": "PE-11b",
            "pattern_name": "FAST — trouble de la parole (AVC/AIT)",
            "matched_tokens": {"parole": p, "soudain": ctx},
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "Difficulté à parler ou trouver ses mots : "
                "évaluation médicale urgente — AVC/AIT à exclure."
            ),
        }

    # IND-012: faiblesse bras seule (transitoire) = AIT jusqu'à preuve du contraire
    f = _any(_FAIBLESSE_MEMBRE, text)
    if f:
        return {
            "pattern_id": "PE-11c",
            "pattern_name": "AIT — faiblesse membre transitoire",
            "matched_tokens": {"faiblesse": f},
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "Faiblesse soudaine d'un membre : AIT suspecté — "
                "évaluation médicale immédiate même si les symptômes ont disparu."
            ),
        }

    return None


def _check_meningite(text: str, _ctx=None) -> Optional[Dict]:
    """PE-12: méningite — nuque raide + fièvre, ou purpura + fièvre → urgent"""
    # Purpura + fièvre = méningococcémie → urgent absolu
    pur = _any(_PURPURA, text)
    fiev = _any(_FIEVRE, text)
    if pur and fiev:
        return {
            "pattern_id": "PE-12a",
            "pattern_name": "Purpura + fièvre (méningococcémie)",
            "matched_tokens": {"purpura": pur, "fievre": fiev},
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "Fièvre avec taches cutanées : méningococcémie possible — "
                "appel immédiat du 15, urgence vitale."
            ),
        }
    # Nuque raide + fièvre
    nuque = _any(_NUQUE, text)
    if nuque and fiev:
        return {
            "pattern_id": "PE-12b",
            "pattern_name": "Méningite (nuque raide + fièvre)",
            "matched_tokens": {"nuque": nuque, "fievre": fiev},
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "Nuque raide avec fièvre : méningite à suspecter — "
                "évaluation médicale immédiate."
            ),
        }
    return None


def _check_sepsis(text: str, patient_context: Optional[Dict] = None) -> Optional[Dict]:
    """PE-13: sepsis — fièvre + confusion/prostration → urgent"""
    fiev = _any(_FIEVRE, text)
    if not fiev:
        return None

    # Négation explicite de fièvre → pas de sepsis
    negation_fievre = any(neg in text for neg in [
        "pas de fievre", "sans fievre", "pas fievre",
        "pas de temperature", "pas de fievre", "apyretique",
        "fievre non", "pas de t°",
    ])
    if negation_fievre:
        return None

    conf = _any(_CONFUSION, text)
    prostration = _any(_SEPSIS_FAIBLESSE, text)

    if not conf and not prostration:
        return None

    fiev_explicit = any(tok in text for tok in [
        "fievre", "temperature", "38", "39", "40", "frissons",
        "etat febrile", "je fais de la fievre",
    ])
    if not fiev_explicit:
        return None

    return {
        "pattern_id": "PE-13",
        "pattern_name": "Sepsis probable (fièvre + altération état général)",
        "matched_tokens": {"fievre": fiev, "alteration": conf or prostration},
        "urgency": "urgent",
        "pattern_triggered": True,
        "message": (
            "Fièvre avec altération de l'état général : sepsis à exclure — "
            "évaluation médicale urgente."
        ),
    }


def _check_neutropenie_chimio(text: str, _ctx=None) -> Optional[Dict]:
    """PE-14: neutropénie sous chimio + fièvre/frissons → urgent"""
    chimio = _any(_CHIMIO_TOKENS, text)
    if not chimio:
        return None
    fiev = _any(_FIEVRE, text)
    if not fiev:
        return None
    return {
        "pattern_id": "PE-14",
        "pattern_name": "Neutropénie fébrile (chimio + fièvre)",
        "matched_tokens": {"chimio": chimio, "fievre": fiev},
        "urgency": "urgent",
        "pattern_triggered": True,
        "message": (
            "Fièvre sous chimiothérapie : neutropénie fébrile à exclure — "
            "évaluation médicale urgente, risque infectieux majeur."
        ),
    }


def _check_geu(text: str, _ctx=None) -> Optional[Dict]:
    """PE-15: GEU — règles retard + douleur ventre → urgent_medical_review"""
    reg = _any(_REGLES_RETARD, text)
    if not reg:
        return None
    douleur = _any(_DOULEUR_VENTRE_LATERALE, text)
    if not douleur:
        return None
    # Exclusion: si enceinte confirmée et pas de douleur latérale = pas GEU
    return {
        "pattern_id": "PE-15",
        "pattern_name": "GEU suspectée (retard règles + douleur abdominale)",
        "matched_tokens": {"regles": reg, "douleur": douleur},
        "urgency": "urgent_medical_review",
        "pattern_triggered": True,
        "message": (
            "Retard de règles avec douleur abdominale : "
            "grossesse extra-utérine à exclure — consultation médicale rapide."
        ),
    }


def _check_dissection(text: str, _ctx=None) -> Optional[Dict]:
    """PE-16: dissection aortique — douleur déchirante dos/épaules soudaine → urgent"""
    diss = _any(_DISSECTION_TOKENS, text)
    if not diss:
        return None
    soudain = _any(_DISSECTION_SOUDAIN, text)
    if not soudain:
        return None
    return {
        "pattern_id": "PE-16",
        "pattern_name": "Dissection aortique (douleur déchirante + soudain)",
        "matched_tokens": {"douleur": diss, "soudain": soudain},
        "urgency": "urgent",
        "pattern_triggered": True,
        "message": (
            "Douleur déchirante dorsale soudaine : dissection aortique à exclure — "
            "appel immédiat du 15."
        ),
    }


def _check_dvt_ep(text: str, _ctx=None) -> Optional[Dict]:
    """PE-17: DVT/EP — mollet gonflé+douloureux, ou post-op/post-partum + essoufflement → urgent"""
    mollet = _any(_MOLLET_TOKENS, text)
    essouff = _any(_ESSOUFFLEMENT, text)
    ctx_thrombose = _any(_CONTEXTE_THROMBOSE, text)
    douleur_cote = _any(_DOULEUR_COTE_THORAX, text)

    # DVT: mollet + gonflement/chaleur/douleur
    if mollet:
        # "mollet gonfle et chaud et douloureux" = DVT quasi-certain
        if _any(["gonfle", "gonflee", "chaud", "douloureux", "dur"], text):
            return {
                "pattern_id": "PE-17a",
                "pattern_name": "TVP suspectée (mollet gonflé/douloureux)",
                "matched_tokens": {"mollet": mollet},
                "urgency": "urgent_medical_review",
                "pattern_triggered": True,
                "message": (
                    "Mollet gonflé, chaud ou douloureux : "
                    "thrombose veineuse profonde à exclure — consultation médicale rapide."
                ),
            }

    # EP: post-op/post-partum + essoufflement → urgent
    if ctx_thrombose and essouff:
        return {
            "pattern_id": "PE-17b",
            "pattern_name": "EP suspectée (contexte thrombose + essoufflement)",
            "matched_tokens": {"contexte": ctx_thrombose, "essoufflement": essouff},
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "Essoufflement dans un contexte à risque thromboembolique : "
                "embolie pulmonaire à exclure — évaluation médicale urgente."
            ),
        }

    # BPCO + essoufflement + douleur côté = EP
    if _any(["bpco"], text) and essouff and douleur_cote:
        return {
            "pattern_id": "PE-17c",
            "pattern_name": "EP suspectée (BPCO + essoufflement + douleur thoracique)",
            "matched_tokens": {"essoufflement": essouff, "cote": douleur_cote},
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "BPCO avec aggravation dyspnée et douleur thoracique : "
                "embolie pulmonaire à exclure — évaluation urgente."
            ),
        }

    return None


def _check_ait_amaurose(text: str, _ctx=None) -> Optional[Dict]:
    """PE-25: AIT/amaurose fugace — trouble visuel transitoire → urgent"""
    vis = _any(_TROUBLES_VISUELS_AIT, text)
    if not vis:
        return None
    return {
        "pattern_id": "PE-25",
        "pattern_name": "AIT / Amaurose fugace (trouble visuel soudain)",
        "matched_tokens": {"trouble_visuel": vis},
        "urgency": "urgent",
        "pattern_triggered": True,
        "message": (
            "Trouble visuel soudain (même transitoire) : "
            "AIT ou amaurose fugace à exclure — évaluation médicale immédiate."
        ),
    }


def _check_preeclampsie(text: str, _ctx=None) -> Optional[Dict]:
    """PE-18: prééclampsie — enceinte + céphalée + troubles visuels → urgent"""
    gros = _any(_GROSSESSE_AVANCEE, text)
    if not gros:
        return None
    ceph = _any(_CEPHALEE_GROSSESSE, text)
    visuels = _any(_TROUBLES_VISUELS_PREECLAMP, text)
    if ceph and visuels:
        return {
            "pattern_id": "PE-18",
            "pattern_name": "Prééclampsie (grossesse + céphalée + troubles visuels)",
            "matched_tokens": {"grossesse": gros, "cephalee": ceph, "visuels": visuels},
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "Céphalée avec troubles visuels pendant la grossesse : "
                "prééclampsie à exclure — évaluation médicale immédiate."
            ),
        }
    return None
    """PE-18: prééclampsie — enceinte + céphalée + troubles visuels → urgent"""
    gros = _any(_GROSSESSE_AVANCEE, text)
    if not gros:
        return None
    ceph = _any(_CEPHALEE_GROSSESSE, text)
    visuels = _any(_TROUBLES_VISUELS_PREECLAMP, text)
    if ceph and visuels:
        return {
            "pattern_id": "PE-18",
            "pattern_name": "Prééclampsie (grossesse + céphalée + troubles visuels)",
            "matched_tokens": {"grossesse": gros, "cephalee": ceph, "visuels": visuels},
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "Céphalée avec troubles visuels pendant la grossesse : "
                "prééclampsie à exclure — évaluation médicale immédiate."
            ),
        }
    return None


def _check_hsd(text: str, patient_context: Optional[Dict] = None) -> Optional[Dict]:
    """PE-19: HSD — âgé + confusion + chute → urgent"""
    conf = _any(_CONFUSION, text)
    sym = _any(_SYMPTOMES_HSD, text)
    if not conf and not sym:
        return None

    chute = _any(_CHUTE, text)
    # Avec ou sans chute explicite, sujet âgé + confusion = HSD possible
    age_token = _any(_SUJET_AGE, text)
    age_val = _age_from_context(patient_context)
    is_aged = bool(age_token) or (age_val and age_val >= 70)

    if is_aged:
        return {
            "pattern_id": "PE-19",
            "pattern_name": "HSD probable (âgé + confusion)",
            "matched_tokens": {
                "confusion": conf or sym,
                "chute": chute,
                "age": age_token or age_val,
            },
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "Confusion chez un sujet âgé : hématome sous-dural à exclure — "
                "évaluation médicale urgente."
            ),
        }
    return None


def _check_hemorragie_digestive(text: str, _ctx=None) -> Optional[Dict]:
    """PE-20: hémorragie digestive haute — selles noires/hématemèse → urgent_medical_review"""
    sn = _any(_SELLES_NOIRES, text)
    hem = _any(_HEMATEMESE, text)
    sang_selles = _any(_SANG_SELLES, text)

    if hem:
        return {
            "pattern_id": "PE-20a",
            "pattern_name": "Hématemèse (vomissement de sang)",
            "matched_tokens": {"hematemese": hem},
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "Vomissement de sang : hémorragie digestive haute — "
                "appel du 15 immédiat."
            ),
        }

    if sn:
        # Selles noires + vertiges/malaise = hémorragie significative
        vt = _any(_VERTIGE_FAIBLESSE, text)
        anticoag = _any(_ANTICOAG, text)
        if vt or anticoag:
            return {
                "pattern_id": "PE-20b",
                "pattern_name": "Hémorragie digestive (selles noires + symptômes)",
                "matched_tokens": {"selles_noires": sn, "signe": vt or anticoag},
                "urgency": "urgent_medical_review",
                "pattern_triggered": True,
                "message": (
                    "Selles noires avec vertiges ou anticoagulant : "
                    "hémorragie digestive à exclure — consultation médicale rapide."
                ),
            }
        # Selles noires seules = déjà medical_urgent via PE-06 (sang_selles)
        return {
            "pattern_id": "PE-20c",
            "pattern_name": "Méléna (selles noires)",
            "matched_tokens": {"selles_noires": sn},
            "urgency": "urgent_medical_review",
            "pattern_triggered": True,
            "message": (
                "Selles noires : méléna possible — "
                "consultation médicale rapide recommandée."
            ),
        }

    return None


def _check_suicidal(text: str, _ctx=None) -> Optional[Dict]:
    """PE-21: idéation suicidaire → urgent"""
    s = _any(_SUICIDAL_TOKENS, text)
    if not s:
        return None
    return {
        "pattern_id": "PE-21",
        "pattern_name": "Idéation suicidaire",
        "matched_tokens": {"idee": s},
        "urgency": "urgent",
        "pattern_triggered": True,
        "message": (
            "Pensées de fin de vie exprimées : "
            "consultation médicale urgente — ne restez pas seul(e), appelez le 15 ou le 3114."
        ),
    }


def _check_hemoptysie(text: str, _ctx=None) -> Optional[Dict]:
    """PE-22: hémoptysie — sang dans les crachats → urgent_medical_review"""
    h = _any(_HEMOPTYSIE_TOKENS, text)
    if not h:
        return None
    return {
        "pattern_id": "PE-22",
        "pattern_name": "Hémoptysie",
        "matched_tokens": {"hemoptysie": h},
        "urgency": "urgent_medical_review",
        "pattern_triggered": True,
        "message": (
            "Sang dans les crachats : consultation médicale rapide — "
            "bilan pulmonaire nécessaire (TB, EP, néoplasie à exclure)."
        ),
    }


def _check_pyelonephrite(text: str, _ctx=None) -> Optional[Dict]:
    """PE-23: pyélonéphrite — brûlure urinaire + fièvre + douleur lombaire → urgent_medical_review"""
    br = _any(_BRULURE_URINAIRE, text)
    if not br:
        return None
    fiev = _any(_FIEVRE, text)
    if not fiev:
        return None
    dos = _any(_DOULEUR_DOS_LOMBAIRE, text)
    if not dos:
        return None
    return {
        "pattern_id": "PE-23",
        "pattern_name": "Pyélonéphrite (brûlure + fièvre + dos)",
        "matched_tokens": {"brulure": br, "fievre": fiev, "dos": dos},
        "urgency": "urgent_medical_review",
        "pattern_triggered": True,
        "message": (
            "Brûlure urinaire avec fièvre et douleur lombaire : "
            "pyélonéphrite à traiter rapidement — consultation médicale urgente."
        ),
    }


def _check_ischemie_mesenterique(text: str, _ctx=None) -> Optional[Dict]:
    """PE-24: ischémie mésentérique — douleur ventre intense soudaine → urgent_medical_review"""
    dv = _any(_DOULEUR_VENTRE_SOUDAINE, text)
    if not dv:
        return None
    soudain = _any(_DISSECTION_SOUDAIN, text)
    ctx = _any(_CONTEXTE_VASCULAIRE, text)
    intense = _any(["tres mal", "douleur intense", "douleur brutale", "tres forte", "tres mal au ventre"], text)

    # Avec contexte vasculaire + soudain
    if (soudain or intense) and ctx:
        return {
            "pattern_id": "PE-24",
            "pattern_name": "Ischémie mésentérique (douleur ventre soudaine + contexte)",
            "matched_tokens": {"douleur": dv, "contexte": ctx},
            "urgency": "urgent_medical_review",
            "pattern_triggered": True,
            "message": (
                "Douleur abdominale intense et soudaine dans un contexte vasculaire : "
                "ischémie mésentérique à exclure — consultation urgente."
            ),
        }

    # IND-023: "très mal au ventre + d'un coup" sans contexte = aussi urgent_medical_review
    if intense and soudain:
        return {
            "pattern_id": "PE-24b",
            "pattern_name": "Douleur abdominale intense et soudaine",
            "matched_tokens": {"douleur": dv, "soudain": soudain},
            "urgency": "urgent_medical_review",
            "pattern_triggered": True,
            "message": (
                "Douleur abdominale très intense et brutale : "
                "cause chirurgicale à exclure — consultation médicale rapide."
            ),
        }

    return None


def _check_dyspnee_severe(text: str, _ctx=None) -> Optional[Dict]:
    """PE-26: dyspnée sévère isolée — j'étouffe, ne respire plus → urgent"""
    severe = _any([
        "j etouffe", "j'etouffe", "etouffe", "suffoque", "je suffoque",
        "n'arrive plus a respirer", "narrive plus a respirer",
        "ne respire plus", "ne peut plus respirer",
        "impossible de respirer", "respire pas", "respire plus",
        "manque d'air", "manque d air",
        "crise d'asthme qui ne passe pas", "crise asthme qui ne passe",
        "ventoline ne fait plus effet", "ventoline ne marche plus",
    ], text)
    if not severe:
        return None
    return {
        "pattern_id": "PE-26",
        "pattern_name": "Dyspnée sévère (j'étouffe / ne respire plus)",
        "matched_tokens": {"dyspnee": severe},
        "urgency": "urgent",
        "pattern_triggered": True,
        "message": (
            "Difficulté respiratoire sévère : évaluation médicale immédiate — "
            "appel du 15 si aggravation rapide."
        ),
    }


def _check_sca_atypique(text: str, _ctx=None) -> Optional[Dict]:
    """PE-27: SCA atypique — sueurs + nausée + malaise sans douleur thoracique → urgent"""
    # Sueurs + nausée = présentation atypique SCA (femme, diabétique)
    sueurs = _any(["sueurs", "transpiration", "moite", "transpire"], text)
    nausee = _any(["nausee", "nausees", "envie de vomir", "j'ai la nausee"], text)
    malaise = _any(["vraiment pas bien", "tres mal", "malaise", "me sens mal"], text)

    if sueurs and nausee and malaise:
        return {
            "pattern_id": "PE-27",
            "pattern_name": "SCA atypique (sueurs + nausée + malaise)",
            "matched_tokens": {"sueurs": sueurs, "nausee": nausee, "malaise": malaise},
            "urgency": "urgent",
            "pattern_triggered": True,
            "message": (
                "Sueurs, nausées et malaise : syndrome coronarien atypique possible — "
                "évaluation médicale urgente, surtout chez la femme ou le diabétique."
            ),
        }
    return None


def _check_grossesse_dyspnee(text: str, _ctx=None) -> Optional[Dict]:
    """PE-28: grossesse + dyspnée → urgent (EP, prééclampsie)"""
    gros = _any(_GROSSESSE_AVANCEE, text)
    if not gros:
        return None
    essouff = _any(_ESSOUFFLEMENT, text)
    if not essouff:
        return None
    return {
        "pattern_id": "PE-28",
        "pattern_name": "Grossesse + dyspnée (EP / prééclampsie)",
        "matched_tokens": {"grossesse": gros, "dyspnee": essouff},
        "urgency": "urgent",
        "pattern_triggered": True,
        "message": (
            "Essoufflement pendant la grossesse : embolie pulmonaire ou prééclampsie à exclure — "
            "évaluation médicale urgente."
        ),
    }


def _check_hemorragie_anticoag(text: str, _ctx=None) -> Optional[Dict]:
    """PE-29: anticoagulant + signe hémorragique + malaise → urgent_medical_review"""
    ac = _any(_ANTICOAG, text)
    if not ac:
        return None
    signe_hemo = _any([
        "selles noires", "selles foncees", "melena",
        "sang dans les selles", "sang dans selles",
        "vomit du sang", "hematemese",
        "saigne", "saignement",
    ], text)
    if not signe_hemo:
        return None
    malaise = _any(["failli tomber", "malaise", "vertiges", "faiblesse", "faible"], text)
    if malaise:
        return {
            "pattern_id": "PE-29",
            "pattern_name": "Hémorragie sous anticoagulant + malaise",
            "matched_tokens": {"anticoag": ac, "hemo": signe_hemo, "malaise": malaise},
            "urgency": "urgent_medical_review",
            "pattern_triggered": True,
            "message": (
                "Signe hémorragique sous anticoagulant avec malaise : "
                "évaluation médicale urgente — hémorragie active à exclure."
            ),
        }
    return None


def _check_migraine_atypique(text: str, _ctx=None) -> Optional[Dict]:
    """PE-30: migraine différente/inhabituelle → urgent_medical_review"""
    migraine = _any(["migraine", "mal de tete habituel", "ma migraine"], text)
    if not migraine:
        return None
    different = _any([
        "c'est different", "c est different", "cette fois c'est different",
        "pas comme d'habitude", "pas comme d habitude",
        "jamais eu ca comme ca", "inhabituel", "bizarre cette fois",
        "ca dure depuis", "dure depuis 3 jours", "dure depuis 2 jours",
        "ne passe pas", "ne part pas",
        "pire que d'habitude", "pire que d habitude",
    ], text)
    if not different:
        return None
    return {
        "pattern_id": "PE-30",
        "pattern_name": "Migraine atypique / inhabituelle",
        "matched_tokens": {"migraine": migraine, "atypique": different},
        "urgency": "urgent_medical_review",
        "pattern_triggered": True,
        "message": (
            "Migraine inhabituelle ou différente des crises habituelles : "
            "consultation médicale rapide — AVC, HSA ou CVST à exclure."
        ),
    }



    """PE-04: confusion + fièvre → medical_urgent (méningite âgée)"""
    conf = _any(_CONFUSION, text)
    if not conf:
        return None
    fiev = _any(_FIEVRE, text)
    if not fiev:
        return None
    return {
        "pattern_id": "PE-04",
        "pattern_name": "Confusion + fièvre",
        "matched_tokens": {"confusion": conf, "fievre": fiev},
        "urgency": "medical_urgent",
        "pattern_triggered": True,
        "message": (
            "Confusion avec fièvre : consultation médicale rapide — "
            "méningite ou sepsis à exclure, surtout chez le sujet âgé."
        ),
    }


def _check_sang_selles(text: str, _ctx=None) -> Optional[Dict]:
    """PE-06: sang dans les selles → medical_urgent"""
    s = _any(_SANG_SELLES, text)
    if not s:
        return None
    return {
        "pattern_id": "PE-06",
        "pattern_name": "Rectorragie",
        "matched_tokens": {"sang_selles": s},
        "urgency": "medical_urgent",
        "pattern_triggered": True,
        "message": (
            "Sang dans les selles : consultation médicale rapide recommandée — "
            "bilan digestif nécessaire."
        ),
    }


# ── Ordre de priorité ────────────────────────────────────────────────────────────
# urgent vitaux immédiats → urgent → urgent_medical_review → medical_urgent

def _check_confusion_fievre(text: str, patient_context: Optional[Dict] = None) -> Optional[Dict]:
    """PE-04: confusion + fièvre → medical_urgent (méningite âgée)"""
    conf = _any(_CONFUSION, text)
    if not conf:
        return None
    fiev = _any(_FIEVRE, text)
    if not fiev:
        return None
    fiev_explicit = any(tok in text for tok in [
        "fievre", "temperature", "38", "39", "40", "frissons",
        "etat febrile", "je fais de la fievre",
    ])
    if not fiev_explicit:
        return None
    return {
        "pattern_id": "PE-04",
        "pattern_name": "Confusion + fièvre",
        "matched_tokens": {"confusion": conf, "fievre": fiev},
        "urgency": "medical_urgent",
        "pattern_triggered": True,
        "message": (
            "Confusion avec fièvre : consultation médicale rapide — "
            "méningite ou sepsis à exclure, surtout chez le sujet âgé."
        ),
    }


def _check_sang_selles(text: str, _ctx=None) -> Optional[Dict]:
    """PE-06: sang dans les selles → medical_urgent"""
    s = _any(_SANG_SELLES, text)
    if not s:
        return None
    return {
        "pattern_id": "PE-06",
        "pattern_name": "Rectorragie",
        "matched_tokens": {"sang_selles": s},
        "urgency": "medical_urgent",
        "pattern_triggered": True,
        "message": (
            "Sang dans les selles : consultation médicale rapide recommandée — "
            "bilan digestif nécessaire."
        ),
    }



_URGENT_CHECKS = [
    # Vitaux immédiats
    _check_suicidal,                        # PE-21: idéation suicidaire
    _check_fast_avc,                        # PE-11: FAST/AVC/AIT
    _check_ait_amaurose,                    # PE-25: AIT/amaurose
    _check_dyspnee_severe,                  # PE-26: j'étouffe / dyspnée sévère
    _check_meningite,                       # PE-12: méningite/purpura
    _check_anticoag_trauma_head,            # PE-01: HSD sous anticoag
    _check_saignement_malaise,              # PE-02: hémorragie + choc
    _check_orthopnee_ic,                    # PE-09: orthopnée IC
    _check_syncope,                         # PE-10: syncope
    _check_neutropenie_chimio,              # PE-14: neutropénie fébrile
    _check_dissection,                      # PE-16: dissection aortique
    _check_sca_atypique,                    # PE-27: SCA atypique (sueurs+nausée)
    _check_fatigue_brutale_essoufflement,   # PE-03: IC/EP
    _check_thunderclap_headache,            # PE-07: HSA
    _check_vertige_faiblesse_membre,        # PE-08: AVC
    _check_douleur_thoracique_isolee,       # PE-05: SCA anchor-resist
    _check_preeclampsie,                    # PE-18: prééclampsie
    _check_grossesse_dyspnee,               # PE-28: grossesse + dyspnée
    _check_dvt_ep,                          # PE-17: DVT/EP
]

# PE-13 sepsis, PE-19 HSD → prennent patient_context → traités séparément

_URGENT_MEDICAL_REVIEW_CHECKS = [
    _check_hemorragie_anticoag,             # PE-29: anticoag + hémorragie
    _check_hemorragie_digestive,            # PE-20: hémorragie digestive
    _check_hemoptysie,                      # PE-22: hémoptysie
    _check_pyelonephrite,                   # PE-23: pyélonéphrite
    _check_geu,                             # PE-15: GEU
    _check_migraine_atypique,               # PE-30: migraine atypique
    _check_ischemie_mesenterique,           # PE-24: ischémie mésentérique
]

_MEDICAL_URGENT_CHECKS = [
    _check_sang_selles,                     # PE-06: rectorragie
]


# ── Interface publique ────────────────────────────────────────────────────────────

def run_pattern_engine(
    text: str,
    patient_context: Optional[Dict] = None,
) -> Optional[Dict]:
    """
    Vérifie les patterns cliniques sur le texte normalisé.

    Args:
        text: texte normalisé (normalize_text() déjà appliqué)
        patient_context: dict optionnel {age, sex, duration_days, ...}

    Returns:
        Dict avec urgency/pattern_id/message si pattern matché, None sinon.

    Priorité: urgent > urgent_medical_review > medical_urgent.
    """
    if not text:
        return None

    # 1. Urgent vitaux
    for check_fn in _URGENT_CHECKS:
        result = check_fn(text)
        if result:
            return result

    # 2. Sepsis + HSD (prennent patient_context)
    result = _check_sepsis(text, patient_context)
    if result:
        return result

    result = _check_hsd(text, patient_context)
    if result:
        return result

    # 3. Confusion + fièvre (PE-04)
    result = _check_confusion_fievre(text, patient_context)
    if result:
        return result

    # 4. urgent_medical_review
    for check_fn in _URGENT_MEDICAL_REVIEW_CHECKS:
        result = check_fn(text)
        if result:
            return result

    # 5. medical_urgent
    for check_fn in _MEDICAL_URGENT_CHECKS:
        result = check_fn(text)
        if result:
            return result

    return None