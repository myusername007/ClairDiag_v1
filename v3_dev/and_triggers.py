"""
ClairDiag v3 — AND-Triggers Engine v1.1.0

CTRL-16: urinary + fever + back → medical_urgent (з negation захистом)
CTRL-17: musculo + mollet + gonflement → medical_consultation escalation
CTRL-18: mollet + essoufflement → urgent (TVP/EP ризик)
CTRL-19: essoufflement + brutal/soudain → urgent
CTRL-20: enceinte + douleur bas ventre → medical_urgent
CTRL-21: gonflement visage (+eruption) → medical_urgent (анафілаксія)
"""

from typing import Dict, List, Optional


# ── Negation ───────────────────────────────────────────────────────────────────

_NEGATION_PREFIXES = [
    "sans ", "pas de ", "pas d'", "pas ", "ni ",
    "aucun", "aucune", "plus de ",
]


def _is_negated_in_context(text: str, token: str, window: int = 35) -> bool:
    idx = text.find(token)
    if idx == -1:
        return False
    context = text[max(0, idx - window):idx]
    return any(neg in context for neg in _NEGATION_PREFIXES)


# ── Token groups ───────────────────────────────────────────────────────────────

_URINARY_TOKENS = [
    "dysurie", "brûlure urinaire", "brûlures urinaires",
    "brûlure pipi", "brulure pipi", "brûle quand j'urine",
    "brûle quand je fais pipi", "brûle en urinant",
    "cystite", "infection urinaire", "brûlures en urinant",
    "ça brûle quand je fais pipi", "ça brule quand je fais pipi",
]

_FEVER_TOKENS = [
    "fièvre", "fievre", "température", "temperature",
    "j'ai chaud", "chaud et froid", "frissons",
    "état fébrile", "etat febrile",
    "je fais de la température", "je fais de la fievre", "je fais de la fièvre",
]

_BACK_TOKENS = [
    "mal au dos", "mal dos", "douleur dos", "douleur lombaire", "douleurs lombaires",
    "mal aux reins", "douleur aux reins", "mal dans le dos",
    "douleur dans le dos", "reins qui font mal", "lombalgie",
    "mal en bas du dos", "douleur bas du dos",
]

_MOLLET_TOKENS = [
    "mollet", "mal au mollet", "douleur mollet",
    "douleur au mollet", "douleurs au mollet",
]

_GONFLEMENT_TOKENS = [
    "gonflement", "gonflé", "gonflée", "oedème", "oedeme",
    "enflé", "enflée", "mollet gonflé", "mollet qui gonfle",
    "jambe gonflée", "cheville gonflée", "gonfle",
]

_ESSOUFFLEMENT_TOKENS = [
    "essoufflement", "essoufflé", "essoufflée",
    "souffle court", "manque de souffle", "j'étouffe",
    "du mal à respirer", "mal à respirer",
]

_BRUTAL_TOKENS = [
    "brutal", "brutale", "soudain", "soudaine", "brusque",
    "d'un coup", "subitement", "tout d'un coup",
]

_ENCEINTE_TOKENS = [
    "enceinte", "grossesse", "femme enceinte",
    "je suis enceinte", "en cours de grossesse",
]

_BAS_VENTRE_TOKENS = [
    "douleur bas ventre", "douleurs bas ventre", "mal bas ventre",
    "douleur pelvienne", "douleur ventre bas",
    "douleur abdominale basse", "crampes bas ventre",
]

_ERUPTION_TOKENS = [
    "éruption cutanée", "eruption cutanee",
    "urticaire", "plaques rouges", "rougeur soudaine",
]

_GONFLEMENT_VISAGE_TOKENS = [
    "gonflement visage", "visage gonflé", "lèvres gonflées",
    "lèvre gonflée", "gonflement lèvres", "gonflement du visage",
    "visage qui gonfle", "oedème visage", "oedeme visage",
    "gonfle visage", "gonfle du visage",
]


def _any_token_in_text(tokens: List[str], text: str) -> Optional[str]:
    for token in tokens:
        if token in text:
            return token
    return None


def _any_token_not_negated(tokens: List[str], text: str) -> Optional[str]:
    for token in tokens:
        if token in text and not _is_negated_in_context(text, token):
            return token
    return None


# ── CTRL-16 ────────────────────────────────────────────────────────────────────

def check_urinary_fever_back(text: str) -> Optional[Dict]:
    """urinary AND fever(not negated) AND back(not negated) → medical_urgent"""
    u = _any_token_in_text(_URINARY_TOKENS, text)
    if not u:
        return None
    f = _any_token_not_negated(_FEVER_TOKENS, text)
    if not f:
        return None
    b = _any_token_not_negated(_BACK_TOKENS, text)
    if not b:
        return None
    return {
        "and_trigger": "ctrl16_urinary_fever_back",
        "matched_tokens": {"urinary": u, "fever": f, "back": b},
        "urgency": "medical_urgent",
        "category": "urinaire",
        "message": (
            "Consultation médicale rapide recommandée. "
            "Fièvre + symptômes urinaires + douleur du dos peuvent "
            "nécessiter une évaluation médicale."
        ),
    }


# ── CTRL-17 ────────────────────────────────────────────────────────────────────

def check_mollet_gonflement(category: str, matched_symptoms: List[str], text: str) -> Optional[Dict]:
    """musculo + mollet + gonflement → medical_consultation escalation"""
    if category != "musculo_squelettique":
        return None
    m = _any_token_in_text(_MOLLET_TOKENS, text)
    if not m:
        return None
    g = _any_token_in_text(_GONFLEMENT_TOKENS, text)
    if not g:
        return None
    return {
        "and_trigger": "ctrl17_mollet_gonflement",
        "matched_tokens": {"mollet": m, "gonflement": g},
        "urgency_override": "medical_consultation",
        "red_flags_to_watch": [
            "douleur importante ou qui augmente",
            "gonflement qui augmente",
            "essoufflement",
            "douleur thoracique",
        ],
        "reason": (
            "Douleur du mollet avec gonflement : "
            "avis médical recommandé pour vérifier l'origine."
        ),
    }


# ── CTRL-18 ────────────────────────────────────────────────────────────────────

def check_mollet_essoufflement(text: str) -> Optional[Dict]:
    """mollet + essoufflement → urgent (TVP/EP ризик)"""
    m = _any_token_in_text(_MOLLET_TOKENS, text)
    if not m:
        return None
    e = _any_token_in_text(_ESSOUFFLEMENT_TOKENS, text)
    if not e:
        return None
    return {
        "and_trigger": "ctrl18_mollet_essoufflement",
        "matched_tokens": {"mollet": m, "essoufflement": e},
        "urgency": "urgent",
        "category": "musculo_squelettique",
        "message": (
            "Douleur du mollet avec essoufflement : "
            "consultation urgente recommandée — risque de thrombose."
        ),
    }


# ── CTRL-19 ────────────────────────────────────────────────────────────────────

def check_essoufflement_brutal(text: str) -> Optional[Dict]:
    """essoufflement + brutal/soudain → urgent"""
    e = _any_token_in_text(_ESSOUFFLEMENT_TOKENS, text)
    if not e:
        return None
    b = _any_token_in_text(_BRUTAL_TOKENS, text)
    if not b:
        return None
    return {
        "and_trigger": "ctrl19_essoufflement_brutal",
        "matched_tokens": {"essoufflement": e, "brutal": b},
        "urgency": "urgent",
        "category": None,
        "message": "Essoufflement brutal ou soudain : consultation urgente requise.",
    }


# ── CTRL-20 ────────────────────────────────────────────────────────────────────

def check_enceinte_douleur(text: str) -> Optional[Dict]:
    """enceinte + douleur bas ventre → medical_urgent"""
    enc = _any_token_in_text(_ENCEINTE_TOKENS, text)
    if not enc:
        return None
    d = _any_token_in_text(_BAS_VENTRE_TOKENS, text)
    if not d:
        return None
    return {
        "and_trigger": "ctrl20_enceinte_douleur",
        "matched_tokens": {"enceinte": enc, "douleur": d},
        "urgency": "medical_urgent",
        "category": "gynecologique_simple",
        "message": (
            "Douleur abdominale basse chez une femme enceinte : "
            "consultation médicale rapide nécessaire."
        ),
    }


# ── CTRL-21 ────────────────────────────────────────────────────────────────────

def check_eruption_gonflement_visage(text: str) -> Optional[Dict]:
    """gonflement visage (+ éruption) → medical_urgent (анафілаксія)"""
    g = _any_token_in_text(_GONFLEMENT_VISAGE_TOKENS, text)
    if not g:
        return None
    e = _any_token_in_text(_ERUPTION_TOKENS, text)
    return {
        "and_trigger": "ctrl21_eruption_gonflement_visage",
        "matched_tokens": {"gonflement_visage": g, "eruption": e},
        "urgency": "medical_urgent",
        "category": "dermatologie_simple",
        "message": (
            "Gonflement du visage avec éruption cutanée : "
            "consultation médicale rapide recommandée — risque de réaction allergique."
        ),
    }



# ── CTRL-22 ────────────────────────────────────────────────────────────────────

_GYNO_TOKENS = [
    "retard regles", "retard règles", "règles en retard", "regles en retard",
    "règles", "regles", "douleur ventre règles", "douleur ventre regles",
    "pertes", "douleur pelvienne",
]

_MALAISE_TOKENS = [
    "malaise", "je me sens mal", "pas bien", "évanouissement",
    "vertiges", "faiblesse soudaine",
]


def check_gyno_malaise(text: str) -> Optional[Dict]:
    """CTRL-22: gyno symptom + malaise → medical_urgent"""
    g = _any_token_in_text(_GYNO_TOKENS, text)
    if not g:
        return None
    m = _any_token_in_text(_MALAISE_TOKENS, text)
    if not m:
        return None
    return {
        "and_trigger": "ctrl22_gyno_malaise",
        "matched_tokens": {"gyno": g, "malaise": m},
        "urgency": "medical_urgent",
        "category": "gynecologique_simple",
        "message": (
            "Symptôme gynécologique avec malaise : "
            "consultation médicale rapide recommandée."
        ),
    }

# ── CTRL-23 ────────────────────────────────────────────────────────────────────

_IRRADIATION_TOKENS = [
    "descend dans la jambe", "ca descend dans la jambe",
    "irradie dans la jambe", "douleur qui descend",
    "irradie", "irradiation",
]

_DOS_TOKENS = [
    "mal au dos", "douleur dos", "douleur lombaire", "lombalgie",
    "dos", "reins",
]


def check_dos_irradiation(text: str) -> Optional[Dict]:
    """CTRL-23: dos + irradiation jambe → medical_consultation"""
    d = _any_token_in_text(_DOS_TOKENS, text)
    if not d:
        return None
    i = _any_token_in_text(_IRRADIATION_TOKENS, text)
    if not i:
        return None
    return {
        "and_trigger": "ctrl23_dos_irradiation",
        "matched_tokens": {"dos": d, "irradiation": i},
        "urgency": "medical_consultation",
        "category": "musculo_squelettique",
        "message": (
            "Douleur du dos avec irradiation dans la jambe : "
            "consultation médicale recommandée."
        ),
    }


# ── CTRL-24 ────────────────────────────────────────────────────────────────────

_GENOU_TOKENS = [
    "genou", "mal au genou", "douleur genou",
]

_GONFLEMENT_ARTICUL_TOKENS = [
    "gonflé", "gonflée", "gonflement", "gonfle",
    "enflé", "enflée",
]

_SPORT_TOKENS = [
    "sport", "après sport", "effort", "entrainement", "entraînement",
    "course", "foot", "football", "hier",
]


def check_genou_gonfle_post_trauma(text: str) -> Optional[Dict]:
    """CTRL-24: genou gonflé (après sport/hier) → medical_consultation"""
    g = _any_token_in_text(_GENOU_TOKENS, text)
    if not g:
        return None
    gf = _any_token_in_text(_GONFLEMENT_ARTICUL_TOKENS, text)
    if not gf:
        return None
    return {
        "and_trigger": "ctrl24_genou_gonfle",
        "matched_tokens": {"genou": g, "gonflement": gf},
        "urgency": "medical_consultation",
        "category": "musculo_squelettique",
        "message": (
            "Genou gonflé : consultation médicale recommandée "
            "pour évaluation articulaire."
        ),
    }


# ── CTRL-25 ────────────────────────────────────────────────────────────────────

_ENFANT_TOKENS = [
    "enfant", "bebe", "bébé", "nourrisson",
    "ans", "mois",  # "5 ans", "8 mois"
]

_ENFANT_AGE_PATTERN = [
    "enfant", "bebe", "bébé", "nourrisson",
    "1 an", "2 ans", "3 ans", "4 ans", "5 ans", "6 ans",
    "7 ans", "8 ans", "9 ans", "10 ans", "11 ans", "12 ans",
    "13 ans", "14 ans", "15 ans",
    "mois",
]

_FIEVRE_TOKENS_PEDIATRIE = [
    "fievre", "fièvre", "temperature", "température",
    "chaud", "frissons", "il fait de la fievre",
]


def check_pediatrie_fievre(text: str) -> Optional[Dict]:
    """CTRL-25: enfant + fièvre → medical_consultation (jamais non_urgent)"""
    e = _any_token_in_text(_ENFANT_AGE_PATTERN, text)
    if not e:
        return None
    f = _any_token_in_text(_FIEVRE_TOKENS_PEDIATRIE, text)
    if not f:
        return None
    return {
        "and_trigger": "ctrl25_pediatrie_fievre",
        "matched_tokens": {"enfant": e, "fievre": f},
        "urgency": "medical_consultation",
        "category": "orl_simple",
        "message": (
            "Fièvre chez un enfant : consultation médicale recommandée."
        ),
    }


# ── Публічний інтерфейс ────────────────────────────────────────────────────────

def check_all_urgent_and_triggers(text: str) -> Optional[Dict]:
    """
    Перевіряє всі AND-triggers що дають urgency=urgent або medical_urgent.
    Пріоритет: urgent > medical_urgent > medical_consultation.
    """
    for fn in [check_mollet_essoufflement, check_essoufflement_brutal]:
        result = fn(text)
        if result:
            return result
    for fn in [check_urinary_fever_back, check_enceinte_douleur, check_eruption_gonflement_visage, check_gyno_malaise]:
        result = fn(text)
        if result:
            return result
    # medical_consultation escalations
    for fn in [check_dos_irradiation, check_genou_gonfle_post_trauma, check_pediatrie_fievre]:
        result = fn(text)
        if result:
            return result
    return None