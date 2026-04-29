"""
ClairDiag v3 — Pattern Engine v1.0.0

Pre-triage layer: детектує клінічні патерни на normalized free text.
Підключається в core.py ПЕРЕД AND-triggers і urgent_triggers.

Покриває:
  - CRIT-018: anticoagulant + trauma crânien + confusion → urgent
  - CRIT-019: saignement abondant + malaise → urgent
  - EDGE-002: fatigue brutale + essoufflement → urgent
  - EDGE-003: confusion + fièvre + âge → medical_urgent
  - EDGE-006: anticoagulant + chute + tête → urgent
  - EDGE-007: douleur thoracique seule → urgent (ANCHOR-RESIST: anxiété ne réduit pas)
  - EDGE-010: sang dans selles → medical_urgent
  - EDGE-011: mal de tête violent soudain (thunderclap) → urgent
  - EDGE-012: vertige + faiblesse membre → urgent (AVC)

Architecture:
  run_pattern_engine(text, patient_context) →
    {"triggered": bool, "urgency": str, "pattern_id": str,
     "pattern_name": str, "pattern_triggered": True, "message": str}
  ou None si pas de match.

Règles:
  - Ne modifie jamais v2 core
  - Ne touche pas urgent_triggers_v1.json ni and_triggers.py
  - Retourne uniquement urgent / medical_urgent (jamais non_urgent)
  - Chaque pattern est tracé et explicable
"""

from typing import Dict, List, Optional


# ── Helpers de détection ────────────────────────────────────────────────────────

def _any(tokens: List[str], text: str) -> Optional[str]:
    """Retourne le premier token trouvé dans le texte."""
    for t in tokens:
        if t in text:
            return t
    return None


def _all(tokens: List[str], text: str) -> bool:
    """Vrai si tous les tokens sont présents."""
    return all(t in text for t in tokens)


# ── Token groups ────────────────────────────────────────────────────────────────

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
]

_CHUTE = [
    "chute", "tombe", "tombe", "est tombe", "suis tombe", "tombee",
    "a chute", "ai chute",
]

_CONFUSION = [
    "confusion", "confus", "confuse", "desoriente", "desorientation",
    "pas coherent", "ne repond plus", "regard vide", "perdu",
    "plus coherent", "bizarre", "etrange comportement",
]

_SAIGNEMENT_ABONDANT = [
    "saignement abondant", "saigne beaucoup", "hemorragie", "perte de sang",
    "saignement important", "sang partout", "saigne enormement",
    "beaucoup de sang", "saignement grave",
]

_MALAISE = [
    "malaise", "je me sens mal", "pas bien", "evanouissement",
    "vertiges", "faiblesse soudaine", "tourne", "tourneboulé",
]

_FATIGUE_BRUTALE = [
    "fatigue brutale", "fatigue soudaine", "fatigue subite",
    "fatigue brusque", "epuisement brutal", "epuisement soudain",
    "fatigue d'un coup", "fatigue tout d'un coup",
]

_ESSOUFFLEMENT = [
    "essoufflement", "essoufflé", "essoufflee", "souffle court",
    "manque de souffle", "j'etouffe", "du mal a respirer",
    "mal a respirer", "respire mal", "respiration difficile",
    "du mal a respirer", "respire pa bien", "respire pas bien",
]

_FIEVRE = [
    "fievre", "temperature", "j'ai chaud", "chaud et froid",
    "frissons", "etat febrile", "je fais de la temperature",
    "je fais de la fievre",
]

_DOULEUR_THORACIQUE = [
    "douleur thoracique", "douleur poitrine", "mal poitrine",
    "douleur au coeur", "oppression poitrine", "serrement poitrine",
    "ca serre poitrine", "ca serre", "mal a la poitrine",
    "douleur au niveau du coeur", "oppression thoracique",
]

_SANG_SELLES = [
    "sang dans les selles", "selles avec sang", "sang selles",
    "rectorragie", "sang rouge selles", "sang dans selles",
    "sang au niveau des selles", "selles sanglantes",
    "sang rectum", "saignement rectal", "saigne en allant aux toilettes",
]

_CEPHALEE_BRUTAL = [
    "mal de tete violent soudain", "cephalee violente soudaine",
    "mal tete brutal", "migraine violente soudaine",
    "jamais eu ca", "pire de ma vie", "mal de tete pire",
    "tete qui eclate soudainement", "coup de tonnerre",
    "douleur tete soudaine violente", "cephalee brutale",
    "cephalee foudroyante",
]

# Фраза "mal de tête violent soudain, jamais eu ça" — треба ловити обидві частини
_CEPHALEE_THUNDER_COMBO = [
    ("mal de tete", "jamais eu ca"),
    ("mal de tete", "jamais eu ça"),
    ("cephalee", "jamais eu ca"),
    ("cephalee", "jamais eu ça"),
    ("tete", "jamais eu ca"),
    ("tete", "jamais eu ça"),
    ("mal tete", "violent"),
    ("mal de tete", "violent"),
    ("cephalee", "violent"),
    ("cephalee", "brutale"),
    ("cephalee", "brutal"),
    ("tete", "coup de tonnerre"),
    ("tete", "pire de ma vie"),
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
]


# ── Patterns ────────────────────────────────────────────────────────────────────

def _check_anticoag_trauma_head(text: str) -> Optional[Dict]:
    """PATTERN-15 adapt: anticoagulant + (trauma crânien OR chute+tête) → urgent"""
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
    # chute + confusion = aussi urgent sous anticoag
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


def _check_saignement_malaise(text: str) -> Optional[Dict]:
    """PATTERN-16 adapt: saignement abondant + malaise → urgent"""
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


def _check_fatigue_brutale_essoufflement(text: str) -> Optional[Dict]:
    """EDGE-002: fatigue brutale + essoufflement → urgent (IC décompensée, EP)"""
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


def _check_confusion_fievre(text: str, patient_context: Optional[Dict]) -> Optional[Dict]:
    """PATTERN-10 adapt: confusion + fièvre → medical_urgent (méningite âgée)"""
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


def _check_douleur_thoracique_isolee(text: str) -> Optional[Dict]:
    """ANCHOR-RESIST-01: douleur thoracique = urgent même si contexte anxieux.
    Ne pas réduire le triage même si 'anxieux' présent."""
    dt = _any(_DOULEUR_THORACIQUE, text)
    if not dt:
        return None
    # Vérifie que ce n'est pas déjà couvert par urgent_triggers existants
    # (douleur thoracique + essoufflement = déjà dans emergency_override)
    # Ici: douleur thoracique SEULE suffit → urgent
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


def _check_sang_selles(text: str) -> Optional[Dict]:
    """EDGE-010: sang dans les selles → medical_urgent"""
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


def _check_thunderclap_headache(text: str) -> Optional[Dict]:
    """PATTERN-06: céphalée thunderclap → urgent (HSA)"""
    # Phrasing directe
    direct = _any(_CEPHALEE_BRUTAL, text)
    if direct:
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
    # Combo: mal de tête + jamais eu ça / violent
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


def _check_vertige_faiblesse_membre(text: str) -> Optional[Dict]:
    """PATTERN-07/08 adapt: vertige + faiblesse membre → urgent (AVC)"""
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


# ── Ordre de priorité des patterns ─────────────────────────────────────────────
# urgent > medical_urgent
# Dans urgent : sécurité vitale immédiate en premier

_URGENT_CHECKS = [
    _check_anticoag_trauma_head,     # PE-01: HSD sous anticoag
    _check_saignement_malaise,       # PE-02: hémorragie + choc
    _check_fatigue_brutale_essoufflement,  # PE-03: IC/EP
    _check_thunderclap_headache,     # PE-07: HSA
    _check_vertige_faiblesse_membre, # PE-08: AVC
    _check_douleur_thoracique_isolee,  # PE-05: SCA (ANCHOR-RESIST)
]

_MEDICAL_URGENT_CHECKS = [
    _check_sang_selles,              # PE-06: rectorragie
]

# PE-04 (confusion+fièvre) prend patient_context → traité séparément


# ── Interface publique ──────────────────────────────────────────────────────────

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
        Dict avec urgency/pattern_id/message si pattern matché,
        None sinon.

    Priorité: urgent > medical_urgent.
    Premier match dans chaque groupe = retourné immédiatement.
    """
    if not text:
        return None

    # 1. Checks urgent (priorité absolue)
    for check_fn in _URGENT_CHECKS:
        result = check_fn(text)
        if result:
            return result

    # 2. Confusion + fièvre (prend patient_context)
    result = _check_confusion_fievre(text, patient_context)
    if result:
        return result

    # 3. Checks medical_urgent
    for check_fn in _MEDICAL_URGENT_CHECKS:
        result = check_fn(text)
        if result:
            return result

    return None