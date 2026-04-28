"""
ClairDiag v3 — AND-Triggers Engine v1.0.0

Реалізує складені умовні тригери (AND-логіка між групами токенів).
Не залежить від порядку слів, розділових знаків, префіксів.

CTRL-16: urinary + fever + back/lumbar → medical_urgent / urinaire
CTRL-17: musculo + mollet + gonflement → medical_consultation escalation
"""

from typing import Dict, List, Optional


# ── Групи токенів ──────────────────────────────────────────────────────────────

_URINARY_TOKENS = [
    "dysurie", "brûlure urinaire", "brûlures urinaires",
    "brûlure pipi", "brulure pipi", "brûle quand j'urine",
    "brûle quand je fais pipi", "brûle en urinant",
    "cystite", "infection urinaire", "brûlures en urinant",
    "ça brûle quand je fais pipi", "ça brule quand je fais pipi",
]

_FEVER_TOKENS = [
    "fièvre", "fievre", "température", "temperature",
    "j'ai chaud", "j'ai froid", "chaud et froid", "frissons",
    "état fébrile", "etat febrile", "je fais de la température",
    "je fais de la fievre", "je fais de la fièvre",
]

_BACK_TOKENS = [
    "mal au dos", "douleur lombaire", "douleurs lombaires",
    "mal aux reins", "douleur aux reins", "mal dans le dos",
    "douleur dans le dos", "reins qui font mal", "lombalgie",
    "douleur lombaire", "mal en bas du dos", "douleur bas du dos",
]

_MOLLET_TOKENS = [
    "mollet", "mal au mollet", "douleur mollet",
    "douleur au mollet", "douleurs au mollet",
]

_GONFLEMENT_TOKENS = [
    "gonflement", "gonflé", "gonflée", "oedème", "oedeme",
    "enflé", "enflée", "mollet gonflé", "mollet qui gonfle",
    "jambe gonflée", "cheville gonflée",
]


def _any_token_in_text(tokens: List[str], text: str) -> Optional[str]:
    """Повертає перший знайдений токен або None."""
    for token in tokens:
        if token in text:
            return token
    return None


# ── CTRL-16 ────────────────────────────────────────────────────────────────────

def check_urinary_fever_back(text: str) -> Optional[Dict]:
    """
    CTRL-16: IF urinary AND fever AND back/lumbar → medical_urgent
    Повертає dict з urgency/category/message або None.
    """
    u = _any_token_in_text(_URINARY_TOKENS, text)
    if not u:
        return None
    f = _any_token_in_text(_FEVER_TOKENS, text)
    if not f:
        return None
    b = _any_token_in_text(_BACK_TOKENS, text)
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
    """
    CTRL-17: IF category=musculo_squelettique AND mollet AND gonflement
             → escalate urgency to medical_consultation + red_flags
    Повертає dict з overrides або None.
    """
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