# ── Emergency Override Layer ─────────────────────────────────────────────────
# Priorité absolue sur le score BPU/RME.
# Déclenché par patterns cliniques fixes, indépendamment des probabilités.
#
# Appelé dans orchestrator après étape 7b (RME), avant étape 8 (TCS).
# Si triggered → emergency=True, urgency="élevé", message SAMU obligatoire.

from dataclasses import dataclass, field


@dataclass
class EmergencyOverrideResult:
    triggered: bool = False
    reason: str = ""
    patterns_matched: list[str] = field(default_factory=list)


# ── Patterns ─────────────────────────────────────────────────────────────────
# Chaque pattern : (frozenset requis, frozenset exclusifs_optionnels, label)
# Un pattern match si TOUS les requis sont présents.

_PATTERNS: list[tuple[frozenset, frozenset, str]] = [

    # Cardio-respiratory — danger immédiat
    (frozenset({"syncope"}),                            frozenset(), "Syncope"),
    (frozenset({"cyanose"}),                            frozenset(), "Cyanose"),
    (frozenset({"hémoptysie"}),                         frozenset(), "Hémoptysie"),
    # FIX: utilise "essoufflement" (terme canonique après _CANON) au lieu de "dyspnée"
    # EXCL: toux/fièvre/fatigue → контекст інфекційний, не кардіо → не тригеримо
    (frozenset({"douleur thoracique", "essoufflement"}),
     frozenset({"toux", "fièvre", "fièvre élevée", "fatigue"}), "Douleur thoracique + dyspnée"),
    (frozenset({"essoufflement", "palpitations", "douleur thoracique"}),
                                                        frozenset(), "Dyspnée + palpitations + douleur thoracique"),
    (frozenset({"détresse respiratoire"}),              frozenset(), "Détresse respiratoire"),
    (frozenset({"dyspnée sévère", "altération état général"}),
                                                        frozenset(), "Dyspnée sévère + altération état général"),

    # Neurological red flags
    (frozenset({"perte de connaissance"}),              frozenset(), "Perte de connaissance"),
    (frozenset({"déficit neurologique"}),               frozenset(), "Déficit neurologique brutal"),
    (frozenset({"confusion aiguë"}),                    frozenset(), "Confusion aiguë sévère"),

    # Infection / systemic danger
    (frozenset({"fièvre", "altération état général", "hypotension"}),
                                                        frozenset(), "Sepsis-like (fièvre + AEG + hypotension)"),
    (frozenset({"fièvre", "altération état général", "tachycardie"}),
                                                        frozenset(), "Sepsis-like (fièvre + AEG + tachycardie)"),

    # ── PATCH v1.1 — 7 FAIL cases ────────────────────────────────────────────
    # N02: bouche déformée + trouble parole → AVC
    (frozenset({"trouble parole"}),                     frozenset(), "Trouble parole (AVC)"),

    # N10: fourmillement bras soudain → AVC
    (frozenset({"fourmillement bras droit soudain"}),   frozenset(), "Fourmillement bras soudain (AVC)"),
    (frozenset({"fourmillement bras gauche soudain"}),  frozenset(), "Fourmillement bras soudain (AVC)"),

    # C03: douleur thoracique + nausées → ACS atypique
    # EXCL: perte d'appétit/fièvre/toux → контекст digestif/infectieux
    (frozenset({"douleur thoracique", "nausées"}),
     frozenset({"perte d'appétit", "fièvre", "fièvre élevée", "toux", "diarrhée"}),
     "Douleur thoracique + nausées (ACS)"),

    # C10: douleur thoracique brutale seule → dissection / ACS
    (frozenset({"douleur thoracique brutale"}),         frozenset(), "Douleur thoracique brutale"),

    # R01: essoufflement soudain au repos → EP / OAP
    (frozenset({"essoufflement soudain"}),              frozenset(), "Essoufflement soudain au repos"),
]


# ── Aliases → symptômes canoniques ───────────────────────────────────────────
# Mapping supplémentaire pour les termes qui peuvent arriver sous forme
# compressée (SCM). Enrichir si besoin.
_CANON: dict[str, str] = {
    "perte conscience":          "perte de connaissance",
    "deficit neurologique":      "déficit neurologique",
    "dyspnee severe":            "dyspnée sévère",
    "alteration etat general":   "altération état général",
    "alteration generale":       "altération état général",
    "aeg":                       "altération état général",
    "detresse respiratoire":     "détresse respiratoire",
    # FIX: dyspnée → dyspnée (garde le terme, ne remplace plus par essoufflement)
    # Les patterns utilisent maintenant "essoufflement" comme terme canonique
    "dyspnée":                   "essoufflement",
    "dyspnee":                   "essoufflement",
    "souffle court":             "essoufflement",
    # PATCH v1.1 — aliases pour nouveaux patterns
    "trouble de la parole":      "trouble parole",
    "difficulté parler":         "trouble parole",
    "parle mal":                 "trouble parole",
    "ne peut plus parler":       "trouble parole",
    "fourmillement bras droit":  "fourmillement bras droit soudain",
    "fourmillement bras gauche": "fourmillement bras gauche soudain",
    "douleur thoracique aiguë brutale": "douleur thoracique brutale",
    "douleur thoracique brutale au repos": "douleur thoracique brutale",
    "manque d air soudain":      "essoufflement soudain",
    "essoufflement brutal":      "essoufflement soudain",
    "manque d'air soudain":      "essoufflement soudain",
}


def _normalize(symptoms: list[str]) -> frozenset[str]:
    """Normalise + expand aliases pour la comparaison."""
    out: set[str] = set()
    for s in symptoms:
        sl = s.lower().strip()
        out.add(sl)
        out.add(_CANON.get(sl, sl))
    return frozenset(out)


def run(symptoms: list[str]) -> EmergencyOverrideResult:
    """
    Vérifie les patterns d'urgence absolue.
    Retourne EmergencyOverrideResult avec triggered=True si au moins un match.
    """
    if not symptoms:
        return EmergencyOverrideResult()

    sym_set = _normalize(symptoms)
    matched: list[str] = []

    for required, exclusions, label in _PATTERNS:
        if required.issubset(sym_set) and not exclusions.intersection(sym_set):
            matched.append(label)

    if not matched:
        return EmergencyOverrideResult()

    reason = matched[0]  # premier match = raison principale affichée
    return EmergencyOverrideResult(
        triggered=True,
        reason=reason,
        patterns_matched=matched,
    )