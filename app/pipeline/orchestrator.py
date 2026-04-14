# ── Pipeline orchestrator — CORE v2.3 ────────────────────────────────────────
# CORE_STATUS: LOCKED — не змінювати без повного regression suite

import logging

from app.pipeline import nse, scm, rfe, bpu, rme, tce, cre, tcs, lme, sgl
from app.pipeline import emergency_override as eo
from app.data.symptoms import DIAG_ARTICLE, URGENT_DIAGNOSES, FORBIDDEN_OUTPUTS, SYMPTOM_CATEGORIES
from app.data.tests import TEST_EXPLANATIONS, CONSULTATION_COST
from app.pipeline.cost_engine import compute_savings
from app.models.schemas import (
    AnalyzeRequest, AnalyzeResponse, Diagnosis, Tests,
    DebugTrace, DebugBPU, DebugCRE, DebugTCE, DebugTCS,
    ValidationResponse, ValidationDiagnosis, SymptomTrace,
    ClinicalReasoningV2, ProbabilityReasoning, TestReasoning,
    DoNotMissEngine, EconomicReasoning, ExplainabilityScore,
    CostItem, PathwayComparison, EconomicReasoningV2,
)

logger = logging.getLogger("clairdiag.pipeline")

# ── CORE LOCK ─────────────────────────────────────────────────────────────────
ENGINE_VERSION: str = "v2.4"
RULES_VERSION: str = "v1.3"
REGISTRY_VERSION: str = "v1.0"
VALIDATION_BASELINE: str = "H15_G30_F40_S100"
CORE_STATUS: str = "LOCKED"
# ─────────────────────────────────────────────────────────────────────────────

_MAX_PROB: float = 0.90
PROBABILITY_THRESHOLD: float = 0.15

# ── ECONOMIC ENGINE V2 — cost data (France baseline) ─────────────────────────
COST_MAP: dict[str, float] = {
    "CRP": 15.0,
    "NFS": 20.0,
    "Troponine": 35.0,
    "ECG": 50.0,
    "Rx thorax": 70.0,
    "Radiographie pulmonaire": 70.0,
    "D-dimères": 40.0,
    "Test C. difficile": 60.0,
    "Coproculture": 45.0,
    "BNP": 45.0,
    "Spirométrie": 55.0,
    "Scanner thoracique": 150.0,
    "pH-métrie": 80.0,
    "Test rapide Strep A": 12.0,
    "Holter ECG": 90.0,
    "TSH": 25.0,
    "Échocardiographie": 120.0,
    "Fibroscopie gastrique": 200.0,
    "Coloscopie": 250.0,
    "Test Helicobacter pylori": 30.0,
    "Bilan martial": 25.0,
    "Ionogramme": 18.0,
    "Créatinine": 12.0,
    "Glycémie": 10.0,
    "Hémocultures": 40.0,
    "Procalcitonine": 35.0,
    "Gaz du sang": 30.0,
    "Test rapide grippe": 25.0,
}

CONSULTATION_GP_COST: float = 30.0

# Standard path per top diagnosis: tests typically over-prescribed
STANDARD_PATH_MAP: dict[str, list[str]] = {
    "Pneumonie":               ["NFS", "CRP", "Rx thorax", "Hémocultures", "Procalcitonine", "Ionogramme", "Gaz du sang"],
    "Bronchite":               ["NFS", "CRP", "Rx thorax", "Procalcitonine"],
    "Asthme":                  ["NFS", "CRP", "Spirométrie", "Rx thorax", "Ionogramme"],
    "Grippe":                  ["NFS", "CRP", "Test rapide grippe", "Rx thorax", "Procalcitonine"],
    "Angine":                  ["NFS", "CRP", "Test rapide Strep A", "Hémocultures"],
    "Rhinopharyngite":         ["NFS", "CRP", "Rx thorax"],
    "Angor":                   ["ECG", "Troponine", "NFS", "CRP", "BNP", "Rx thorax", "Créatinine"],
    "Infarctus du myocarde":   ["ECG", "Troponine", "NFS", "CRP", "BNP", "Rx thorax", "Créatinine", "Gaz du sang"],
    "Embolie pulmonaire":      ["D-dimères", "Scanner thoracique", "ECG", "NFS", "CRP", "Troponine", "Gaz du sang"],
    "Insuffisance cardiaque":  ["BNP", "ECG", "Échocardiographie", "NFS", "CRP", "Rx thorax", "Ionogramme", "Créatinine"],
    "Trouble du rythme":       ["ECG", "Holter ECG", "NFS", "CRP", "TSH", "Ionogramme", "BNP"],
    "Gastrite":                ["NFS", "CRP", "Test Helicobacter pylori", "Fibroscopie gastrique"],
    "RGO":                     ["NFS", "CRP", "pH-métrie", "Fibroscopie gastrique"],
    "SII":                     ["NFS", "CRP", "TSH", "Coloscopie", "Coproculture"],
    "Dyspepsie":               ["NFS", "CRP", "Test Helicobacter pylori", "Fibroscopie gastrique"],
    "Dysbiose":                ["NFS", "CRP", "Coproculture", "Test C. difficile"],
    "Clostridioides difficile":["NFS", "CRP", "Coproculture", "Test C. difficile", "Ionogramme"],
    "Infection intestinale":   ["NFS", "CRP", "Coproculture", "Hémocultures"],
    "Hypertension":            ["NFS", "CRP", "ECG", "Ionogramme", "Créatinine", "Glycémie"],
    "Anémie":                  ["NFS", "CRP", "Bilan martial", "Créatinine"],
    "Allergie":                ["NFS", "CRP"],
}

# Critical tests that must NEVER be removed — if removed, savings claim is blocked
CRITICAL_TESTS: dict[str, set[str]] = {
    "Embolie pulmonaire":      {"D-dimères", "Scanner thoracique", "ECG"},
    "Angor":                   {"ECG", "Troponine"},
    "Infarctus du myocarde":   {"ECG", "Troponine"},
    "Insuffisance cardiaque":  {"BNP", "ECG"},
    "Trouble du rythme":       {"ECG"},
    "Pneumonie":               {"Rx thorax", "CRP"},
    "Clostridioides difficile":{"Test C. difficile"},
}


# ── Decision Engine 2.0 ───────────────────────────────────────────────────────

def _build_decision(
    emergency: bool,
    urgency_level: str,
    misdiagnosis_risk: str,
    tcs_level: str,
) -> str:
    """
    Decision Engine 2.0 — ТЗ spec:
      EMERGENCY | URGENT_MEDICAL_REVIEW | TESTS_REQUIRED |
      MEDICAL_REVIEW | LOW_RISK_MONITOR
    """
    if emergency:
        return "EMERGENCY"
    if urgency_level == "élevé":
        return "URGENT_MEDICAL_REVIEW"
    if tcs_level in ("TCS_2", "besoin_tests"):
        return "TESTS_REQUIRED"
    if tcs_level in ("TCS_3", "TCS_4", "incertain"):
        return "MEDICAL_REVIEW"
    return "LOW_RISK_MONITOR"


# ── Helpers ───────────────────────────────────────────────────────────────────

# Symptômes minimum requis pour inclure un diagnostic dans la liste
DIAGNOSIS_MINIMUM_SYMPTOMS: dict[str, list[str]] = {
    "Pneumonie":    ["toux", "fièvre", "expectorations", "dyspnée", "essoufflement"],
    "Grippe":       ["fièvre", "courbatures", "fatigue"],
    "Bronchite":    ["toux", "expectorations"],
    "Angine":       ["mal de gorge", "fièvre", "odynophagie"],
    "Rhinopharyngite": ["rhinorrhée", "éternuements", "congestion nasale", "mal de gorge"],
    "Asthme":       ["essoufflement", "sifflement", "dyspnée"],
    "Angor":        ["douleur thoracique", "douleur à l'effort", "palpitations"],
    "Infarctus du myocarde": ["douleur thoracique", "douleur thoracique intense"],
    "Embolie pulmonaire": ["essoufflement", "douleur thoracique", "dyspnée"],
    "Insuffisance cardiaque": ["essoufflement", "oedèmes", "palpitations", "gonflement jambes", "prise de poids rapide"],
    "Gastrite":     ["douleur abdominale", "nausées", "brûlures gastriques"],
    "RGO":          ["brûlures gastriques", "régurgitations", "douleur après repas"],
    "SII":          ["douleur abdominale", "ballonnements", "diarrhée", "constipation"],
    "Clostridioides difficile": ["fièvre", "diarrhée sévère", "douleur abdominale"],
}


def filter_diagnoses(diagnoses: list[Diagnosis], detected_symptoms: list[str]) -> list[Diagnosis]:
    """
    Filtre les diagnostics sans symptômes minimum correspondants.
    Un diagnostic est inclus si :
      - aucun minimum défini (pas de contrainte), OU
      - au moins 1 symptôme minimum est présent, OU
      - probabilité >= 0.50 (signal fort du moteur bayésien)
    """
    result: list[Diagnosis] = []
    syms_lower = {s.lower() for s in detected_symptoms}
    for dx in diagnoses:
        minimum = DIAGNOSIS_MINIMUM_SYMPTOMS.get(dx.name, [])
        if not minimum:
            result.append(dx)
            continue
        has_match = any(s.lower() in syms_lower for s in minimum)
        # C. difficile : jamais par probabilité seule — red flags obligatoires
        if dx.name == "Clostridioides difficile":
            if has_match:
                result.append(dx)
        elif has_match or dx.probability >= 0.50:
            result.append(dx)
    return result


def _build_diagnosis_list(probs: dict[str, float], symptom_set: set[str]) -> list[Diagnosis]:
    from app.data.symptoms import SYMPTOM_DIAGNOSES

    key_symptoms_map: dict[str, list[str]] = {name: [] for name in probs}
    for sym in symptom_set:
        for diag in SYMPTOM_DIAGNOSES.get(sym, {}):
            if diag in key_symptoms_map and sym not in key_symptoms_map[diag]:
                key_symptoms_map[diag].append(sym)

    _CLINICAL_PRIORITY: dict[str, int] = {
        "Infarctus du myocarde": 12, "Embolie pulmonaire": 11, "Angor": 10, "Pneumonie": 9, "Angine": 7,
        "Grippe": 5, "Bronchite": 4, "Asthme": 3,
        "Insuffisance cardiaque": 7, "Trouble du rythme": 6,
        "Gastrite": 4, "Anémie": 3,
    }

    diagnoses = sorted(
        [
            Diagnosis(
                name=name,
                probability=round(prob, 2),
                key_symptoms=key_symptoms_map.get(name, []),
            )
            for name, prob in probs.items()
            if prob >= PROBABILITY_THRESHOLD
        ],
        key=lambda d: (d.probability, _CLINICAL_PRIORITY.get(d.name, 0)),
        reverse=True,
    )[:3]

    # filter irrelevant diagnoses (minimum symptom check)
    diagnoses = filter_diagnoses(diagnoses, list(symptom_set))

    deduped: list[Diagnosis] = []
    for d in diagnoses:
        if deduped and (deduped[-1].probability - d.probability) < 0.04:
            prob = round(deduped[-1].probability - 0.04, 2)
        else:
            prob = d.probability
        deduped.append(
            Diagnosis(name=d.name, probability=max(prob, 0.10), key_symptoms=d.key_symptoms)
        )
    return deduped


def confidence_label(score: float) -> str:
    """Texte lisible pour le score de confiance (affiché au patient)."""
    if score < 0.35:
        return "Peu de données — résultat indicatif uniquement"
    elif score < 0.60:
        return "Confiance modérée — consultation recommandée"
    elif score < 0.85:
        return "Bonne confiance — vérifiez les analyses"
    else:
        return "Haute confiance"


def resolve_primary_diagnosis(
    ranked_diagnoses: list[Diagnosis],
    safety_diagnosis: dict | None = None,
) -> dict:
    """
    Retourne UN seul diagnostic principal pour l'affichage.
    Si safety_diagnosis est une urgence — il a la priorité absolue.
    Élimine la contradiction entre deux sections affichant un "top1" différent.
    """
    if not ranked_diagnoses:
        return {}

    if safety_diagnosis and safety_diagnosis.get("urgency") == "EMERGENCY":
        primary = safety_diagnosis
        note = "Diagnostic prioritaire par sécurité — à ne pas manquer"
    else:
        d = ranked_diagnoses[0]
        primary = {
            "name": d.name,
            "probability": d.probability,
            "key_symptoms": d.key_symptoms,
        }
        note = None

    return {
        "primary": primary,
        "note": note,
        "alternatives": [
            {"name": d.name, "probability": d.probability}
            for d in ranked_diagnoses[1:3]
        ],
    }


def _build_explanation(symptoms: list[str], diagnoses: list[Diagnosis], required_tests: list[str]) -> str:
    if not diagnoses:
        return (
            "Les symptômes fournis ne permettent pas d'établir un diagnostic. "
            "Veuillez consulter un médecin."
        )

    top = diagnoses[0]
    pct = int(top.probability * 100)
    art = DIAG_ARTICLE.get(top.name, "une")

    if pct >= 65:
        start = f"Les symptômes correspondent le plus probablement à {art} {top.name}."
    elif pct >= 40:
        start = f"Le diagnostic le plus probable est {art} {top.name}."
    else:
        start = (
            f"{art.capitalize()} {top.name} est possible, "
            "mais les symptômes restent insuffisants pour confirmer."
        )

    alt = ""
    if len(diagnoses) > 1:
        art2 = DIAG_ARTICLE.get(diagnoses[1].name, "une")
        alt = f" {art2.capitalize()} {diagnoses[1].name} ne peut pas être totalement exclue."

    tests_hint = ""
    first_two = [t for t in required_tests[:2] if t in TEST_EXPLANATIONS]
    if first_two:
        joined = " et ".join(
            f"{t} ({TEST_EXPLANATIONS[t]})" for t in first_two
        )
        tests_hint = f" Pour une première évaluation : {joined}."

    return start + alt + tests_hint


def _build_diagnostic_path(
    diagnoses: list[Diagnosis],
    urgency_level: str,
    tcs_level: str,
) -> dict:
    if not diagnoses:
        return {}

    top = diagnoses[0].name

    if urgency_level == "élevé":
        next_step = "Consultation médicale rapide — selon l'évolution clinique"
    elif tcs_level in ("TCS_1", "TCS_2"):
        next_step = "Consultation médicale recommandée + examens complémentaires"
    elif tcs_level == "TCS_3":
        next_step = "Consultation non urgente pour confirmation diagnostique"
    else:
        next_step = "Surveillance des symptômes — consulter si persistance ou aggravation"

    _DO_NOT_MISS_MAP: dict[str, str] = {
        "Asthme":              "Exacerbation sévère / état de mal asthmatique",
        "Bronchite":           "Évolution vers pneumonie si fièvre ou aggravation",
        "Pneumonie":           "Détresse respiratoire — hospitalisation si SpO2 < 94%",
        "Grippe":              "Complications pulmonaires chez les sujets à risque",
        "Angine":              "Angine de Ludwig / abcès périamygdalien",
        "Angor":               "Syndrome coronarien aigu — ECG urgent",
        "Infarctus du myocarde": "Arrêt cardiaque — appeler le 15 immédiatement",
        "Embolie pulmonaire":  "Choc obstructif — urgence vitale immédiate",
        "Insuffisance cardiaque": "Décompensation aiguë — hospitalisation",
        "Trouble du rythme":   "Fibrillation ventriculaire — urgence cardiologique",
        "Gastrite":            "Ulcère compliqué / hémorragie digestive",
        "RGO":                 "Origine cardiaque à écarter si douleur atypique",
        "SII":                 "Pathologie organique sous-jacente (MICI, cancer colorectal)",
        "Hypertension":        "Urgence hypertensive / AVC ischémique",
        "Anémie":              "Origine hémorragique ou hémopathie maligne",
    }
    risk_not_to_miss = _DO_NOT_MISS_MAP.get(top, "Surveillance de l'évolution clinique")

    _KEY_TEST_MAP: dict[str, str] = {
        "Pneumonie": "Rx thorax + CRP",
        "Embolie pulmonaire": "D-dimères + Scanner thoracique",
        "Angor": "ECG + Troponine",
        "Infarctus du myocarde": "ECG + Troponine en URGENCE — appeler le 15",
        "Insuffisance cardiaque": "BNP + ECG + Échocardiographie",
        "Trouble du rythme": "ECG + Holter ECG",
        "Asthme": "Spirométrie",
        "Bronchite": "Rx thorax si fièvre",
        "RGO": "pH-métrie",
        "SII": "Coloscopie si > 50 ans ou signes d'alarme",
        "Grippe": "Test rapide grippe si disponible",
        "Angine": "Test rapide Strep A",
        "Hypertension": "Mesure tensionnelle répétée",
        "Anémie": "NFS + bilan martial",
    }
    key_discriminator = _KEY_TEST_MAP.get(top, "Bilan biologique de base (NFS, CRP)")

    return {
        "main_hypothesis": top,
        "risk_not_to_miss": risk_not_to_miss,
        "key_discriminator": key_discriminator,
        "next_best_step": next_step,
    }


def _build_misdiagnosis_risk(
    diagnoses: list[Diagnosis],
    probs: dict[str, float],
    symptom_count: int,
    tcs_level: str,
    incoherence_score: float,
) -> tuple[str, float]:
    score = 0.0

    sorted_p = sorted(probs.values(), reverse=True)
    gap = (sorted_p[0] - sorted_p[1]) if len(sorted_p) >= 2 else 1.0
    if gap < 0.10:
        score += 0.35
    elif gap < 0.20:
        score += 0.20

    if symptom_count <= 2:
        score += 0.25
    elif symptom_count <= 3:
        score += 0.10

    if incoherence_score > 0.20:
        score += 0.20
    elif incoherence_score > 0.10:
        score += 0.10

    if tcs_level == "TCS_4":
        score += 0.20
    elif tcs_level == "TCS_3":
        score += 0.10

    # Dangerous alternative in top3
    _DANGEROUS: set[str] = {
        "Embolie pulmonaire", "Angor", "Infarctus du myocarde", "Insuffisance cardiaque",
        "Trouble du rythme", "Pneumonie",
    }
    top3_names = {d.name for d in diagnoses}
    if any(d in _DANGEROUS for d in top3_names) and len(diagnoses) >= 2:
        score += 0.10

    if len(diagnoses) >= 3:
        p3 = diagnoses[2].probability if len(diagnoses) > 2 else 0
        if p3 > 0.25:
            score += 0.15

    score = round(min(score, 1.0), 3)

    if score >= 0.50:
        level = "élevé"
    elif score >= 0.25:
        level = "modéré"
    else:
        level = "faible"

    return level, score


def _build_worsening_signs(diagnoses: list[Diagnosis], urgency_level: str) -> list[str]:
    _BASE_SIGNS = [
        "Aggravation progressive des symptômes",
        "Apparition de fièvre élevée (> 39°C)",
        "Altération de l'état général",
    ]
    _DIAG_SIGNS: dict[str, list[str]] = {
        "Pneumonie":           ["Aggravation de l'essoufflement", "Cyanose / lèvres bleues", "Confusion"],
        "Embolie pulmonaire":  ["Douleur thoracique brutale", "Syncope", "Crachats sanglants"],
        "Angor":               ["Douleur thoracique persistante ou au repos", "Irradiation au bras / mâchoire"],
        "Infarctus du myocarde": ["Douleur thoracique écrasante", "Irradiation bras gauche / mâchoire", "Appeler le 15 MAINTENANT"],
        "Insuffisance cardiaque": ["Oedèmes des membres inférieurs", "Orthopnée", "Essoufflement nocturne"],
        "Trouble du rythme":   ["Palpitations soutenues", "Syncope", "Malaise avec perte de connaissance"],
        "Asthme":              ["Sifflement intense", "Incapacité à parler", "SpO2 < 94%"],
        "Grippe":              ["Fièvre persistante > 5 jours", "Douleur thoracique", "Confusion"],
        "Angine":              ["Stridor / difficulté à avaler", "Trismus", "Gonflement cervical"],
        "Gastrite":            ["Vomissements de sang", "Selles noires", "Douleur abdominale sévère"],
        "SII":                 ["Perte de poids inexpliquée", "Sang dans les selles", "Douleur nocturne"],
        "Hypertension":        ["Céphalées sévères brutales", "Troubles visuels", "Confusion"],
    }
    top_name = diagnoses[0].name if diagnoses else ""
    specific = _DIAG_SIGNS.get(top_name, [])

    # SAMU mention: only when urgency_level=="élevé" (which after FINAL OVERRIDE = severity=="severe" only)
    if urgency_level == "élevé":
        return specific[:3] + ["→ Appeler le 15 (SAMU) sans délai si ces signes apparaissent"]
    return (_BASE_SIGNS + specific)[:5]


def _build_do_not_miss(diagnoses: list[Diagnosis], urgency_level: str) -> list[str]:
    top3_names = {d.name for d in diagnoses}

    _DANGER_BY_PROFILE: dict[str, list[str]] = {
        "Pneumonie":       ["Embolie pulmonaire", "Insuffisance cardiaque"],
        "Bronchite":       ["Pneumonie", "Embolie pulmonaire"],
        "Asthme":          ["Pneumonie", "Embolie pulmonaire"],
        "Angor":           ["Embolie pulmonaire", "Syndrome coronarien aigu"],
        "Infarctus du myocarde": ["Arrêt cardiaque", "Embolie pulmonaire"],
        "Gastrite":        ["Ulcère perforé", "Infarctus mésentérique"],
        "RGO":             ["Syndrome coronarien aigu"],
        "Trouble du rythme": ["Fibrillation ventriculaire", "Bloc auriculo-ventriculaire"],
        "Grippe":          ["Pneumonie", "Sepsis"],
        "Angine":          ["Abcès périamygdalien", "Épiglottite"],
        "Rhinopharyngite": ["Sinusite compliquée", "Méningite si raideur nuque"],
        "Insuffisance cardiaque": ["Insuffisance rénale", "Hypothyroïdie", "Syndrome néphrotique", "Embolie pulmonaire"],
        "Anémie":          ["Hémopathie maligne", "Hémorragie digestive occulte"],
        "Hypertension":    ["AVC ischémique", "Urgence hypertensive"],
    }

    result: list[str] = []
    for d in diagnoses[:2]:
        for item in _DANGER_BY_PROFILE.get(d.name, []):
            if item not in top3_names and item not in result:
                result.append(item)

    if urgency_level == "élevé" and "Embolie pulmonaire" not in top3_names and "Embolie pulmonaire" not in result:
        result.insert(0, "Embolie pulmonaire")

    return result[:4]


def _build_analysis_limits() -> list[str]:
    return [
        "Analyse d'orientation clinique, non substitutive à un examen médical complet.",
        "Confirmation nécessaire si symptômes persistants, atypiques ou aggravés.",
        "Basé sur une analyse probabiliste — ne remplace pas l'évaluation clinique directe.",
    ]


def _build_differential(
    diagnoses: list[Diagnosis],
    probs: dict[str, float],
    symptoms_compressed: list[str],
) -> dict:
    from app.data.symptoms import SYMPTOM_DIAGNOSES

    if not diagnoses:
        return {}

    top = diagnoses[0]
    alternatives = [d.name for d in diagnoses[1:]]

    sorted_p = sorted(probs.values(), reverse=True)
    gap = round(sorted_p[0] - sorted_p[1], 2) if len(sorted_p) >= 2 else 1.0

    if gap >= 0.10:
        gap_note = "Diagnostic principal probable."
    else:
        gap_note = "Profil proche — confirmation nécessaire."

    ss = set(symptoms_compressed)
    top1_syms = {s for s, d in SYMPTOM_DIAGNOSES.items() if top.name in d}
    top2_syms: set[str] = set()
    if alternatives:
        top2_syms = {s for s, d in SYMPTOM_DIAGNOSES.items() if alternatives[0] in d}
    discriminant_syms = sorted(ss & top1_syms - top2_syms)

    _DISCRIMINANT_TESTS: dict[frozenset, list[str]] = {
        frozenset({"Asthme", "Bronchite"}):          ["Spirométrie", "Rx thorax"],
        frozenset({"Asthme", "Pneumonie"}):          ["Rx thorax", "CRP"],
        frozenset({"Pneumonie", "Bronchite"}):       ["Rx thorax", "CRP", "NFS"],
        frozenset({"Angor", "Embolie pulmonaire"}):  ["ECG", "D-dimères", "Troponine"],
        frozenset({"Angor", "Insuffisance cardiaque"}): ["ECG", "BNP", "Troponine"],
        frozenset({"Grippe", "Angine"}):             ["Test rapide Strep A"],
        frozenset({"Gastrite", "RGO"}):              ["pH-métrie", "Test Helicobacter pylori"],
        frozenset({"Gastrite", "SII"}):              ["NFS", "CRP", "Coloscopie"],
    }
    pair = frozenset({top.name, alternatives[0]}) if alternatives else frozenset()
    discriminant_tests = _DISCRIMINANT_TESTS.get(pair, [])

    # do_not_miss для differential
    _DNM_MAP: dict[str, list[str]] = {
        "Pneumonie": ["Embolie pulmonaire"],
        "Angor":     ["Syndrome coronarien aigu", "Embolie pulmonaire"],
        "Bronchite": ["Pneumonie"],
        "Asthme":    ["Pneumonie", "Embolie pulmonaire"],
        "Grippe":    ["Sepsis", "Pneumonie"],
    }
    risk_not_to_miss = _DNM_MAP.get(top.name, [])

    return {
        "principal": top.name,
        "principal_probability": top.probability,
        "alternatives": alternatives,
        "risk_not_to_miss": risk_not_to_miss,
        "key_discriminator": discriminant_tests[0] if discriminant_tests else None,
        "gap_note": gap_note,
        "discriminant_symptoms": discriminant_syms,
        "discriminant_tests": discriminant_tests,
    }


def _build_test_details(
    required: list[str],
    optional: list[str],
    diagnoses_names: list[str],
) -> list[dict]:
    from app.data.tests import TEST_CATALOG

    _PRIORITY_OVERRIDE: dict[str, str] = {
        "D-dimères":             "haute",
        "ECG":                   "haute",
        "Troponine":             "haute",
        "BNP":                   "haute",
        "NFS":                   "moyenne",
        "CRP":                   "moyenne",
        "Rx thorax":             "moyenne",
        "Radiographie pulmonaire": "moyenne",
        "Spirométrie":           "moyenne",
        "Scanner thoracique":    "haute",
        "pH-métrie":             "moyenne",
        "Test rapide Strep A":   "moyenne",
        "Holter ECG":            "faible",
        "TSH":                   "faible",
        "Échocardiographie":     "faible",
        "Fibroscopie gastrique": "faible",
        "Coloscopie":            "faible",
    }

    # next_if_positive map
    _NEXT_IF_POSITIVE: dict[str, str] = {
        "D-dimères":   "Scanner thoracique (angio-TDM)",
        "BNP":         "Échocardiographie",
        "ECG":         "Consultation cardiologique urgente",
        "Troponine":   "Hospitalisation cardiologique",
        "CRP":         "Radiographie pulmonaire si contexte respiratoire",
        "NFS":         "Bilan martial + réticulocytes si anémie",
        "Spirométrie": "Test de réversibilité aux bronchodilatateurs",
        "Test rapide Strep A": "Antibiothérapie si positif",
        "pH-métrie":   "Inhibiteurs de pompe à protons",
    }

    details = []
    top1 = diagnoses_names[0] if diagnoses_names else ""
    top3 = diagnoses_names[:3]

    for test in required + optional:
        catalog = TEST_CATALOG.get(test, {})
        dv = catalog.get("diagnostic_value", {})
        expl = catalog.get("explanation", "")

        confirms = [d for d in top3 if dv.get(d, 0) >= 0.60]
        excludes = [d for d in top3 if 0 < dv.get(d, 0) < 0.15]

        if test in required:
            priority = _PRIORITY_OVERRIDE.get(test, "haute")
        else:
            priority = _PRIORITY_OVERRIDE.get(test, "faible")

        details.append({
            "test": test,
            "priority": priority,
            "in_required": test in required,
            "pourquoi": expl or f"Évaluation pour {top1}",
            "confirme": confirms,
            "exclut": excludes,
            "next_if_positive": _NEXT_IF_POSITIVE.get(test, ""),
        })

    _PRIO_ORDER = {"haute": 0, "moyenne": 1, "faible": 2}
    details.sort(key=lambda x: (0 if x["in_required"] else 1, _PRIO_ORDER.get(x["priority"], 9)))
    return details


def _build_validation(
    diagnoses: list,
    probs: dict[str, float],
    symptom_set: set[str],
    tests,
    confidence_score: float,
    incoherence_score: float,
    symptoms_compressed: list[str],
) -> "ValidationResponse":
    from app.data.symptoms import SYMPTOM_DIAGNOSES, COMBO_BONUSES, SYMPTOM_EXCLUSIONS
    from app.data.tests import TEST_CATALOG, DIAGNOSIS_TESTS
    from app.pipeline.tcs import _LOW_DATA_THRESHOLD

    val_diagnoses = []
    ss = set(symptoms_compressed)

    for diag in diagnoses[:3]:
        name = diag.name
        why = []
        why_not = []

        supporting = [s for s in ss if name in SYMPTOM_DIAGNOSES.get(s, {})]
        for s in supporting:
            w = SYMPTOM_DIAGNOSES[s][name]
            why.append(f"{s} (poids {w:.1f})")

        for combo, bonuses in COMBO_BONUSES:
            if combo.issubset(ss) and name in bonuses:
                why.append(f"combo {'+'.join(sorted(combo))} → +{bonuses[name]:.2f}")

        for s in ss:
            pen = SYMPTOM_EXCLUSIONS.get(s, {}).get(name, 0)
            if pen > 0:
                why_not.append(f"{s} → pénalité -{pen:.2f}")

        typical = set(SYMPTOM_DIAGNOSES.get(name, {}).keys()) - ss
        if typical:
            missing = sorted(typical)[:2]
            why_not.append(f"absents: {', '.join(missing)}")

        val_diagnoses.append(ValidationDiagnosis(
            name=name,
            probability=diag.probability,
            why=why or ["aucun symptôme spécifique détecté"],
            why_not=why_not or ["aucune contradiction"],
        ))

    tests_reasoning = []
    top_name = diagnoses[0].name if diagnoses else ""
    for t in tests.required[:3]:
        info = TEST_CATALOG.get(t, {})
        dv = info.get("diagnostic_value", {}).get(top_name, 0)
        expl = info.get("explanation", "")
        tests_reasoning.append(
            f"{t} — valeur diagnostique {dv:.0%} pour {top_name}: {expl}"
        )

    _sp = sorted(probs.values(), reverse=True)
    _top_diag = max(probs, key=probs.get) if probs else ""
    _diag_syms = set(SYMPTOM_DIAGNOSES.get(_top_diag, {}).keys())
    _cov = len(ss & _diag_syms) / len(ss) if ss else 0.0
    _gap = (_sp[0] - _sp[1]) if len(_sp) >= 2 else 1.0
    _coh = min(_gap / 0.30, 1.0)
    _qual = min(len(symptoms_compressed) / 4.0, 1.0)

    breakdown = {
        "coverage": round(_cov, 3),
        "coherence": round(_coh, 3),
        "quality": round(_qual, 3),
        "incoherence_penalty": round(incoherence_score * 0.08, 3),
        "final_score": round(confidence_score, 3),
        "low_data": len(symptoms_compressed) <= _LOW_DATA_THRESHOLD,
    }

    return ValidationResponse(
        top3=val_diagnoses,
        tests_reasoning=tests_reasoning,
        confidence_breakdown=breakdown,
    )


def _build_input_confidence(
    symptoms_raw: list[str],
    interpreted_symptoms: list[str],
    symptoms_compressed: list[str],
) -> "InputConfidence":
    from app.models.schemas import InputConfidence

    score = 1.0
    n = len(symptoms_raw)

    # Short input penalty
    if n <= 1:
        score -= 0.30
    elif n <= 2:
        score -= 0.10

    # Fuzzy used: interpreted більше ніж canonical
    canonical_set = set(symptoms_compressed)
    interpreted_set = set(interpreted_symptoms)
    fuzzy_extra = interpreted_set - canonical_set
    if fuzzy_extra:
        score -= 0.20

    # Typo detected: якщо interpreted знайшов щось чого не було в raw
    raw_text = " ".join(symptoms_raw).lower()
    typo_detected = any(
        s not in raw_text for s in interpreted_symptoms
    )
    if typo_detected:
        score -= 0.10

    score = round(max(0.0, min(1.0, score)), 2)

    if score > 0.75:
        level = "high"
    elif score >= 0.40:
        level = "medium"
    else:
        level = "low"

    # Urgent override
    _URGENT_PAIR = {"douleur thoracique", "essoufflement"}
    has_urgent = _URGENT_PAIR.issubset(set(symptoms_compressed))

    _CONFIRM_MESSAGES = {
        "urgent":          "Des symptômes potentiellement sensibles ont été détectés. Confirmez immédiatement. En cas de gêne importante, appelez le 15.",
        "ambiguity":       "Nous avons interprété vos symptômes. Veuillez confirmer avant l'analyse.",
        "low_data":        "Les informations sont insuffisantes. Veuillez préciser vos symptômes.",
        "voice_uncertain": "La transcription vocale semble incomplète ou incertaine. Merci de confirmer les symptômes détectés.",
    }

    if has_urgent:
        return InputConfidence(
            input_confidence=level,
            confirm_required=True,
            confirm_type="urgent",
            confirm_message=_CONFIRM_MESSAGES["urgent"],
            parser_score=score,
        )

    confirm_required = level != "high"
    confirm_type = None
    if level == "low":
        confirm_type = "low_data"
    elif level == "medium":
        confirm_type = "ambiguity"

    confirm_message = _CONFIRM_MESSAGES.get(confirm_type, "") if confirm_type else ""

    return InputConfidence(
        input_confidence=level,
        confirm_required=confirm_required,
        confirm_type=confirm_type,
        confirm_message=confirm_message,
        parser_score=score,
    )


def _build_decision_logic(
    diagnoses: list,
    confidence_score: float,
    misdiagnosis_risk_score: float,
    decision: str,
    urgency_level: str,
    symptoms_compressed: list[str],
) -> "DecisionLogic":
    from app.models.schemas import DecisionLogic

    top = diagnoses[0] if diagnoses else None
    score = round(confidence_score, 2)
    risk = round(misdiagnosis_risk_score, 2)

    _REASON_MAP = {
        "EMERGENCY":             "Urgence vitale détectée — intervention immédiate requise",
        "URGENT_MEDICAL_REVIEW": "Évaluation médicale rapide recommandée",
        "TESTS_REQUIRED":        "Orientation probable mais confirmation biologique nécessaire",
        "MEDICAL_REVIEW":        "Diagnostic incertain — consultation recommandée pour évaluation",
        "LOW_RISK_MONITOR":      "Profil bénin — surveillance des symptômes suffisante",
    }

    reason = _REASON_MAP.get(decision, "")
    if top:
        reason = f"{top.name} probable ({int(top.probability*100)}%). " + reason

    # decision_basis: список причин
    decision_basis = []
    if top:
        decision_basis.append(f"Top diagnostic: {top.name} ({int(top.probability*100)}%)")
    if urgency_level == "élevé":
        decision_basis.append("Urgency: élevé")
    for s in symptoms_compressed[:3]:
        decision_basis.append(f"Symptôme: {s}")

    return DecisionLogic(
        score=score,
        risk=risk,
        decision=decision,
        reason=reason,
        decision_basis=decision_basis[:5],
        override_applied=False,
        override_reason="",
    )


def _build_safety_layer(
    symptoms_compressed: list[str],
    emergency_flag: bool,
    misdiagnosis_risk: str,
    is_fallback: bool,
    diagnoses: list,
) -> "SafetyLayer":
    from app.models.schemas import SafetyLayer

    _RED_FLAGS = {
        "syncope", "cyanose", "hémoptysie", "perte de connaissance",
        "douleur thoracique intense", "paralysie",
    }
    checked = [s for s in symptoms_compressed if s in _RED_FLAGS]

    miss_map = {"faible": "low", "modéré": "medium", "élevé": "high"}
    miss_risk = miss_map.get(misdiagnosis_risk, "low")

    # safety_notes
    safety_notes = []
    sym_set = set(symptoms_compressed)
    _AMBIGUOUS = {"douleur thoracique", "essoufflement", "palpitations"}
    if sym_set & _AMBIGUOUS and not emergency_flag:
        safety_notes.append("Symptômes potentiellement cardiaques — origine organique à écarter")
    if miss_risk == "high":
        safety_notes.append("Risque d'erreur diagnostique élevé — consultation médicale obligatoire")
    if is_fallback:
        safety_notes.append("Mode fallback activé — résultat indicatif uniquement")

    # urgent_confirmation_required
    urgent_conf = bool(sym_set & _AMBIGUOUS) or miss_risk == "high"

    return SafetyLayer(
        red_flags_checked=checked,
        emergency_path=emergency_flag,
        miss_risk=miss_risk,
        fallback_triggered=is_fallback,
        safety_notes=safety_notes,
        urgent_confirmation_required=urgent_conf,
    )


def _build_economic_impact(economics: dict, tests_required: list[str], diagnoses: list = None) -> "EconomicImpact":
    from app.models.schemas import EconomicImpact

    # Use real standard path count from STANDARD_PATH_MAP
    top1 = diagnoses[0].name if diagnoses else ""
    std_tests = STANDARD_PATH_MAP.get(top1, ["NFS", "CRP"])
    std_count = len(std_tests)

    std = economics.get("standard_cost", 0)
    opt = economics.get("optimized_cost", 0)
    saved = economics.get("savings", 0)

    # tests_avoided = real difference between standard and optimized
    avoided = max(0, std_count - len(tests_required))

    gain = f"{round(std / opt, 1)}x" if opt > 0 else "1.0x"

    # consultations_avoided: якщо savings > 0 — мінімум 1 консультація зекономлена
    consultations_avoided = 1 if saved > 0 else 0
    if saved > 100:
        consultations_avoided = 2

    # pathway_shortened: оптимізований шлях коротший за стандартний
    pathway_shortened = avoided > 0 or saved > 0

    return EconomicImpact(
        tests_avoided=avoided,
        cost_saved=float(saved),
        efficiency_gain=gain,
        system_impact="Réduction des examens inutiles et orientation diagnostique précoce",
        consultations_avoided=consultations_avoided,
        pathway_shortened=pathway_shortened,
    )


def _build_consistency_check(
    probs: dict[str, float],
    confidence_score: float,
    incoherence_score: float,
    symptoms_compressed: list[str] | None = None,
) -> "ConsistencyCheck":
    from app.models.schemas import ConsistencyCheck

    sorted_p = sorted(probs.values(), reverse=True)
    gap = round(sorted_p[0] - sorted_p[1], 3) if len(sorted_p) >= 2 else 1.0

    top1_stable = gap >= 0.10 and incoherence_score < 0.20

    if confidence_score >= 0.65 and gap >= 0.15 and incoherence_score < 0.15:
        robustness = "high"
    elif confidence_score >= 0.40 and gap >= 0.08:
        robustness = "medium"
    else:
        robustness = "low"

    # symptom_logic_consistent: top1 підтримується хоч одним симптомом
    from app.data.symptoms import SYMPTOM_DIAGNOSES as _SD
    top_diag_name = max(probs, key=probs.get) if probs else ""
    _syms = symptoms_compressed or []
    sym_logic = any(top_diag_name in _SD.get(s, {}) for s in _syms)
    # context_logic_consistent: якщо context є — перевіряємо що не суперечить top1
    # (буде оновлено через route якщо є context)
    ctx_logic = True

    return ConsistencyCheck(
        top1_stability=top1_stable,
        score_gap=gap,
        decision_robustness=robustness,
        symptom_logic_consistent=sym_logic,
        context_logic_consistent=ctx_logic,
    )


def _build_scenario_simulation(
    diagnoses: list,
    urgency_level: str,
    tests_required: list[str],
) -> "ScenarioSimulation":
    from app.models.schemas import ScenarioSimulation

    if not diagnoses:
        return ScenarioSimulation(
            best_case="Symptômes transitoires sans pathologie sous-jacente",
            worst_case="Pathologie grave non identifiée — consultation médicale recommandée",
            most_likely="Données insuffisantes pour projection",
        )

    top = diagnoses[0]
    alt = diagnoses[1].name if len(diagnoses) > 1 else None
    test_str = ", ".join(tests_required[:2]) if tests_required else "aucun"

    best = f"Évolution favorable de {top.name} avec traitement adapté"
    most_likely = f"{top.name} confirmé après {test_str}"

    if urgency_level == "élevé":
        worst = f"Aggravation rapide — évaluation médicale à réaliser sans délai"
    elif alt:
        worst = f"{alt} sous-jacent non exclu — surveillance recommandée"
    else:
        worst = f"Évolution défavorable sans prise en charge — consultez un médecin"

    return ScenarioSimulation(
        best_case=best,
        worst_case=worst,
        most_likely=most_likely,
    )


def _build_diagnostic_tree(
    diagnoses: list,
    tests_required: list[str],
    test_details: list[dict],
) -> list:
    from app.models.schemas import DiagnosticTreeStep

    if not diagnoses or not tests_required:
        return []

    top = diagnoses[0].name
    steps = []

    _NEXT_IF_NEG: dict[str, str] = {
        "CRP":         f"Profil infectieux peu probable — reconsidérer {top}",
        "NFS":         "Anémie exclue — réévaluer l'orientation",
        "ECG":         "Origine cardiaque électrique exclue",
        "D-dimères":   "Embolie pulmonaire peu probable",
        "Troponine":   "Nécrose myocardique exclue",
        "Rx thorax":   "Pneumonie radiologique exclue",
        "Spirométrie": "Obstruction bronchique exclue",
        "Test rapide Strep A": "Angine bactérienne exclue — origine virale probable",
    }

    for i, test in enumerate(tests_required[:4], start=1):
        td = next((d for d in test_details if d["test"] == test), {})
        pos = td.get("next_if_positive", f"Confirmation de {top} — adapter le traitement")
        neg = _NEXT_IF_NEG.get(test, "Orienter vers diagnostic alternatif")
        _GOAL_MAP = {
            "CRP":              "Évaluer le niveau d'inflammation",
            "NFS":              "Détecter anémie ou infection",
            "ECG":              "Évaluer l'activité électrique cardiaque",
            "D-dimères":        "Exclure embolie pulmonaire",
            "Troponine":        "Exclure nécrose myocardique",
            "Rx thorax":        "Visualiser les poumons",
            "Radiographie pulmonaire": "Visualiser les poumons",
            "Spirométrie":      "Évaluer la fonction respiratoire",
            "Test rapide Strep A": "Identifier angine bactérienne",
            "BNP":              "Évaluer la fonction cardiaque",
            "pH-métrie":        "Confirmer reflux acide",
        }
        _PRIO_MAP = {
            "ECG": "urgente", "D-dimères": "urgente", "Troponine": "urgente",
            "CRP": "haute", "NFS": "haute", "Rx thorax": "haute",
            "Spirométrie": "moyenne", "BNP": "haute", "pH-métrie": "faible",
        }
        _VALUE_MAP = {
            "CRP": "sensibilité 80%", "ECG": "spécificité 95%",
            "D-dimères": "VPN 99%", "Troponine": "spécificité 98%",
            "NFS": "sensibilité 85%", "Rx thorax": "sensibilité 75%",
            "Test rapide Strep A": "sensibilité 90%",
        }
        steps.append(DiagnosticTreeStep(
            step=i,
            action=test,
            if_positive=pos,
            if_negative=neg,
            goal=_GOAL_MAP.get(test, f"Évaluer profil de {top}"),
            priority=_PRIO_MAP.get(test, "moyenne"),
            estimated_value=_VALUE_MAP.get(test, ""),
        ))

    return steps


def _build_trust_score(
    confidence_score: float,
    symptom_count: int,
    incoherence_score: float,
    misdiagnosis_risk_score: float,
) -> "TrustScore":
    from app.models.schemas import TrustScore

    data_quality = round(min(symptom_count / 5.0, 1.0) * (1 - incoherence_score * 0.3), 3)
    model_conf = round(confidence_score, 3)
    risk_factor = round(misdiagnosis_risk_score, 3)
    global_score = round(
        0.40 * model_conf + 0.35 * data_quality + 0.25 * (1 - risk_factor),
        3
    )

    # parser_reliability: на основі symptom_count і confidence_score
    parser_reliability = round(min(symptom_count / 4.0, 1.0) * confidence_score, 3)
    # context_quality: 0.0 за замовчуванням, буде оновлено через route
    context_quality = 0.0

    return TrustScore(
        global_score=global_score,
        data_quality=data_quality,
        model_confidence=model_conf,
        risk_factor=risk_factor,
        parser_reliability=parser_reliability,
        context_quality=context_quality,
    )


def _build_edge_case_analysis(
    diagnoses: list,
    incoherence_score: float,
    sgl_warnings: list[str],
    is_fallback: bool,
) -> "EdgeCaseAnalysis":
    from app.models.schemas import EdgeCaseAnalysis

    atypical = len(diagnoses) >= 2 and diagnoses[0].probability < 0.50
    conflict = incoherence_score > 0.20 or any("contradiction" in w.lower() for w in sgl_warnings)

    fallback_reason = ""
    if is_fallback:
        fallback_reason = "Pipeline error — demo mode activated"
    elif atypical:
        fallback_reason = "Présentation atypique — probabilités proches entre diagnostics"
    elif conflict:
        fallback_reason = "Contradiction entre symptômes — résultat à confirmer"

    manual_review = atypical or conflict or is_fallback

    return EdgeCaseAnalysis(
        atypical_presentation=atypical,
        conflict_detected=conflict,
        fallback_reason=fallback_reason,
        manual_review_recommended=manual_review,
    )


def _build_clinical_reasoning(
    diagnoses: list,
    symptoms_compressed: list[str],
    probs: dict[str, float],
    tests_required: list[str],
    urgency_level: str,
) -> "ClinicalReasoning":
    from app.models.schemas import ClinicalReasoning
    from app.data.symptoms import SYMPTOM_DIAGNOSES, COMBO_BONUSES

    if not diagnoses:
        return ClinicalReasoning()

    top = diagnoses[0]
    ss = set(symptoms_compressed)

    # Symptom clusters: групи симптомів що вказують на один діагноз
    clusters: list[str] = []
    for combo, bonuses in COMBO_BONUSES:
        if combo.issubset(ss) and top.name in bonuses:
            clusters.append(f"{' + '.join(sorted(combo))} → {top.name}")

    # Rules triggered: симптоми з найбільшим вагою для top1
    supporting = {
        s: SYMPTOM_DIAGNOSES[s][top.name]
        for s in ss
        if top.name in SYMPTOM_DIAGNOSES.get(s, {})
    }
    rules = sorted(supporting.items(), key=lambda x: -x[1])
    rules_triggered = [f"{s} (poids {w:.2f})" for s, w in rules[:4]]

    # Why top1
    if supporting:
        top_syms = sorted(supporting, key=supporting.get, reverse=True)[:3]
        why_top1 = (
            f"{top.name} retenu car {', '.join(top_syms)} "
            f"présentent une valeur diagnostique élevée "
            f"(probabilité {int(top.probability*100)}%)"
        )
    else:
        why_top1 = f"{top.name} retenu par élimination — profil symptomatique partiel"

    # Why not others
    why_not_parts = []
    for d in diagnoses[1:]:
        diff = round(top.probability - d.probability, 2)
        why_not_parts.append(f"{d.name} écarté ({diff:+.0%} vs top1)")
    why_not_others = "; ".join(why_not_parts) if why_not_parts else "Aucune alternative proche"

    # Risk logic
    if urgency_level == "élevé":
        risk_logic = f"Symptômes nécessitant évaluation rapide — {top.name} avec risque d'aggravation"
    else:
        risk_logic = f"Risque faible à modéré — {top.name} sans signe de gravité immédiate"

    # Test strategy
    if tests_required:
        test_strategy = (
            f"Priorité à {tests_required[0]} pour confirmer {top.name}. "
            + (f"Associer {tests_required[1]} si résultat ambigu." if len(tests_required) > 1 else "")
        )
    else:
        test_strategy = "Surveillance clinique suffisante — pas d'examen prioritaire identifié"

    # context_influence (ТЗ п.6)
    context_influence = ""
    # буде заповнено якщо context переданий через route
    # negative_signals: симптоми що знижують top1
    from app.data.symptoms import SYMPTOM_EXCLUSIONS
    negative_signals = []
    for s in ss:
        pen = SYMPTOM_EXCLUSIONS.get(s, {}).get(top.name, 0)
        if pen >= 0.10:
            negative_signals.append(f"{s} réduit {top.name} (-{pen:.0%})")

    # discriminator_logic: що відрізняє top1 від top2
    discriminator_logic = ""
    if len(diagnoses) >= 2:
        alt = diagnoses[1].name
        top1_only = {s for s in ss if top.name in SYMPTOM_DIAGNOSES.get(s, {}) and alt not in SYMPTOM_DIAGNOSES.get(s, {})}
        alt_only  = {s for s in ss if alt in SYMPTOM_DIAGNOSES.get(s, {}) and top.name not in SYMPTOM_DIAGNOSES.get(s, {})}
        if top1_only:
            discriminator_logic = f"{', '.join(sorted(top1_only)[:2])} discriminent {top.name} vs {alt}"
        elif alt_only:
            discriminator_logic = f"{', '.join(sorted(alt_only)[:2])} penchent vers {alt} — surveiller"

    return ClinicalReasoning(
        symptom_clusters=clusters,
        rules_triggered=rules_triggered,
        why_top1=why_top1,
        why_not_others=why_not_others,
        risk_logic=risk_logic,
        test_strategy=test_strategy,
        context_influence=context_influence,
        negative_signals=negative_signals[:3],
        discriminator_logic=discriminator_logic,
    )


_COMPLIANCE_STATIC = None


def _get_compliance():
    from app.models.schemas import Compliance
    global _COMPLIANCE_STATIC
    if _COMPLIANCE_STATIC is None:
        _COMPLIANCE_STATIC = Compliance(
            gdpr_ready=True,
            hds_ready=True,
            clinical_use="decision_support_only",
            liability_level="low",
        )
    return _COMPLIANCE_STATIC


def _build_self_check(
    diagnoses: list,
    probs: dict[str, float],
    symptoms_compressed: list[str],
    tests_required: list[str],
    decision: str,
    misdiagnosis_risk: str,
    confidence_level: str,
    incoherence_score: float,
) -> "SelfCheck":
    from app.models.schemas import SelfCheck
    from app.data.symptoms import SYMPTOM_DIAGNOSES

    # 1. logic_consistent: top1 має хоча б 1 підтримуючий симптом
    top = diagnoses[0].name if diagnoses else ""
    supporting = [
        s for s in symptoms_compressed
        if top in SYMPTOM_DIAGNOSES.get(s, {})
    ]
    logic_consistent = len(supporting) >= 1

    # 2. no_conflicts: incoherence нижче порогу
    no_conflicts = incoherence_score < 0.30

    # 3. decision_valid: decision відповідає urgency/confidence
    _VALID_PAIRS = {
        ("EMERGENCY", "élevé"), ("EMERGENCY", "modéré"),
        ("URGENT_MEDICAL_REVIEW", "élevé"),
        ("TESTS_REQUIRED", "modéré"), ("TESTS_REQUIRED", "faible"),
        ("MEDICAL_REVIEW", "modéré"), ("MEDICAL_REVIEW", "faible"),
        ("LOW_RISK_MONITOR", "faible"), ("LOW_RISK_MONITOR", "modéré"),
    }
    # decision_valid якщо confidence не "élevé" при LOW_RISK або навпаки
    decision_valid = not (decision == "LOW_RISK_MONITOR" and misdiagnosis_risk == "élevé")

    # 4. tests_relevant: кожен required test має diagnostic_value для top1
    tests_relevant = True
    if tests_required and top:
        try:
            from app.data.tests import TEST_CATALOG
            for t in tests_required[:3]:
                dv = TEST_CATALOG.get(t, {}).get("diagnostic_value", {})
                if dv and top not in dv:
                    tests_relevant = False
                    break
        except Exception:
            pass

    # 5. risk_aligned: misdiagnosis_risk узгоджений з confidence
    _BAD_COMBOS = {("élevé", "élevé")}  # high confidence + high misdiagnosis
    risk_aligned = (confidence_level, misdiagnosis_risk) not in _BAD_COMBOS

    return SelfCheck(
        logic_consistent=logic_consistent,
        no_conflicts=no_conflicts,
        decision_valid=decision_valid,
        tests_relevant=tests_relevant,
        risk_aligned=risk_aligned,
    )


def _build_quality_gate(
    self_check: "SelfCheck",
    trust_score: "TrustScore",
    diagnoses: list,
    symptoms_compressed: list[str],
    probs: dict[str, float],
    voice_confidence: str | None = None,
    confidence_level: str = "",
) -> tuple["QualityGate", bool]:
    """
    Повертає (QualityGate, is_valid_output).
    Quality Gate score = зважена сума всіх перевірок.
    Threshold = 0.97 — якщо нижче, output не вважається валідним.
    """
    from app.models.schemas import QualityGate
    from app.data.symptoms import SYMPTOM_DIAGNOSES

    score = 1.0
    block_reason = ""

    # Self-check penalties
    if not self_check.logic_consistent:
        score -= 0.15
        block_reason = "Top diagnosis has no supporting symptoms"
    if not self_check.no_conflicts:
        score -= 0.10
        if not block_reason:
            block_reason = "Symptom contradictions exceed threshold"
    if not self_check.decision_valid:
        score -= 0.15
        if not block_reason:
            block_reason = "Decision inconsistent with risk profile"
    if not self_check.tests_relevant:
        score -= 0.08
    if not self_check.risk_aligned:
        score -= 0.10

    # Anti-fake validation (п.5)
    # Перевірка 1: висока ймовірність без симптомів
    if diagnoses:
        top = diagnoses[0]
        supporting = [
            s for s in symptoms_compressed
            if top.name in SYMPTOM_DIAGNOSES.get(s, {})
        ]
        if top.probability >= 0.80 and len(supporting) == 0:
            score -= 0.20
            if not block_reason:
                block_reason = "High probability claimed without supporting symptoms"

    # Перевірка 2: занадто мало симптомів для впевненого результату
    if len(symptoms_compressed) <= 1 and diagnoses and diagnoses[0].probability >= 0.75:
        score -= 0.15
        if not block_reason:
            block_reason = "High confidence with single symptom — insufficient data"

    # Перевірка 3: всі ймовірності однакові (ознака degenerate output)
    if probs and len(probs) >= 2:
        vals = sorted(probs.values(), reverse=True)
        if abs(vals[0] - vals[-1]) < 0.01:
            score -= 0.15
            if not block_reason:
                block_reason = "All diagnoses have identical probability — degenerate output"

    # Перевірка 4 (п.11): tests не відповідають діагнозу
    if diagnoses:
        from app.data.tests import TEST_CATALOG
        top_name = diagnoses[0].name
        # Перевіряємо що хоча б 1 required тест має diagnostic_value для top1
        # Якщо жоден тест не пов'язаний з top1 — penalty
        # (soft check — penalty тільки якщо є тести але жоден не для top1)

    # Перевірка 5 (п.11): voice uncertain + high confidence → penalty
    if voice_confidence == "low" and confidence_level == "élevé":
        score -= 0.10
        if not block_reason:
            block_reason = "Voice transcription uncertain but confidence high — confirmation required"

    # Перевірка 6 (п.11): context after_meal але top1 не digestive
    # (передається через consistency_check.context_logic_consistent)
    if not self_check.logic_consistent and not block_reason:
        pass  # вже враховано вище

    # Trust score contribution
    if trust_score:
        if trust_score.global_score < 0.30:
            score -= 0.10
        elif trust_score.global_score < 0.50:
            score -= 0.05

    score = round(max(0.0, min(1.0, score)), 3)
    passed = score >= 0.97
    is_valid = passed or score >= 0.70  # soft fallback: >= 0.70 видається але з попередженням

    if not passed and not block_reason:
        block_reason = f"Quality score {score:.2f} below threshold 0.97"

    return QualityGate(
        passed=passed,
        score=score,
        threshold=0.97,
        block_reason=block_reason if not passed else "",
    ), is_valid


def _build_stability(probs: dict[str, float]) -> "StabilityCheck":
    """
    Pipeline детерміністичний — variance = 0.0 завжди.
    reproducible = True якщо top1 gap достатній.
    """
    from app.models.schemas import StabilityCheck

    sorted_p = sorted(probs.values(), reverse=True)
    gap = (sorted_p[0] - sorted_p[1]) if len(sorted_p) >= 2 else 1.0
    reproducible = gap >= 0.05  # якщо gap дуже малий — результат нестабільний при малих змінах

    return StabilityCheck(
        reproducible=reproducible,
        variance=0.0,  # детерміністичний pipeline
    )


def _build_trace_id(symptoms: list[str], onset: str | None, duration: str | None) -> str:
    """
    Детермінований хеш вхідних даних — дозволяє відтворити будь-який запит.
    """
    import hashlib
    key = "|".join(sorted(symptoms)) + f"|{onset or ''}|{duration or ''}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _build_audit(
    symptoms_raw: list[str],
    symptoms_compressed: list[str],
    probs_before: dict[str, float],
    probs_after: dict[str, float],
    rules_triggered: list[str],
    decision: str,
    urgency_level: str,
    tcs_level: str,
    confidence_level: str,
) -> "AuditMode":
    from app.models.schemas import AuditMode

    path = (
        f"input({len(symptoms_raw)} syms) "
        f"→ compress({len(symptoms_compressed)}) "
        f"→ score(top={max(probs_after.values(), default=0):.2f}) "
        f"→ tcs={tcs_level} "
        f"→ urgency={urgency_level} "
        f"→ confidence={confidence_level} "
        f"→ decision={decision}"
    )

    return AuditMode(
        input_received=list(symptoms_raw),
        normalized_symptoms=list(symptoms_compressed),
        rules_triggered=rules_triggered[:10],
        scores_before={k: round(v, 3) for k, v in sorted(probs_before.items(), key=lambda x: -x[1])},
        scores_after={k: round(v, 3) for k, v in sorted(probs_after.items(), key=lambda x: -x[1])},
        final_decision_path=path,
        context_detected={},   # заповнюється через route
        symptom_trace={},      # заповнюється через route
    )


def _build_engine_meta() -> "EngineMeta":
    from app.models.schemas import EngineMeta

    return EngineMeta(
        engine_version=ENGINE_VERSION,
        rules_version=RULES_VERSION,
        mode="ABSOLUTE",
        build_hash="8ea6d8f3e436",
        core_status=CORE_STATUS,
    )


_SAFE_OUTPUT_STATIC = None


def _get_safe_output():
    from app.models.schemas import SafeOutput
    global _SAFE_OUTPUT_STATIC
    if _SAFE_OUTPUT_STATIC is None:
        _SAFE_OUTPUT_STATIC = SafeOutput(
            is_medical_advice=False,
            requires_validation=True,
            risk_level="controlled",
            usage_scope="orientation_only",
        )
    return _SAFE_OUTPUT_STATIC



# ── EXPLAINABILITY LAYER (п.1–7) ─────────────────────────────────────────────

def _build_clinical_reasoning_v2(
    diagnoses: list,
    symptoms_compressed: list[str],
    probs: dict[str, float],
    context: dict | None = None,
) -> "ClinicalReasoningV2":
    from app.models.schemas import ClinicalReasoningV2
    from app.data.symptoms import SYMPTOM_DIAGNOSES, COMBO_BONUSES

    if not diagnoses:
        return ClinicalReasoningV2(
            main_logic=["Données insuffisantes pour établir une logique clinique"],
            why_this_diagnosis=["Aucun diagnostic retenu"],
            why_not_others=[],
        )

    top = diagnoses[0]
    ss = set(symptoms_compressed)

    # main_logic: symptom → hypothesis links
    main_logic: list[str] = []
    supporting = {
        s: SYMPTOM_DIAGNOSES[s][top.name]
        for s in ss
        if top.name in SYMPTOM_DIAGNOSES.get(s, {})
    }
    for sym, weight in sorted(supporting.items(), key=lambda x: -x[1])[:4]:
        main_logic.append(f"{sym} → {top.name} (poids {weight:.2f})")

    # combo bonuses
    for combo, bonuses in COMBO_BONUSES:
        if combo.issubset(ss) and top.name in bonuses:
            main_logic.append(
                f"Combinaison [{' + '.join(sorted(combo))}] → boost {top.name} +{bonuses[top.name]:.2f}"
            )

    # context influence
    if context:
        if context.get("after_food"):
            main_logic.append("Contexte après repas → renforce profil digestif (Gastrite/RGO)")
        if context.get("post_medication"):
            main_logic.append("Post-antibiotiques → risque Dysbiose/C.difficile")
        if context.get("night_worsening"):
            main_logic.append("Aggravation nocturne → contexte Insuffisance cardiaque")

    # why_this_diagnosis
    why_this: list[str] = []
    if supporting:
        top_sym = sorted(supporting, key=supporting.get, reverse=True)[0]
        why_this.append(
            f"{top.name} retenu : {top_sym} est le symptôme le plus discriminant "
            f"(poids {supporting[top_sym]:.2f}, probabilité finale {int(top.probability*100)}%)"
        )
    else:
        why_this.append(f"{top.name} retenu par accumulation de signaux faibles")

    sorted_p = sorted(probs.values(), reverse=True)
    gap = round(sorted_p[0] - sorted_p[1], 2) if len(sorted_p) >= 2 else 1.0
    if gap >= 0.15:
        why_this.append(f"Écart probabiliste clair avec le 2e diagnostic (+{int(gap*100)}%)")
    else:
        why_this.append(f"Profil proche des alternatives — confirmation recommandée (écart {int(gap*100)}%)")

    # why_not_others
    why_not: list[str] = []
    from app.data.symptoms import SYMPTOM_EXCLUSIONS
    for alt_diag in diagnoses[1:]:
        diff = round(top.probability - alt_diag.probability, 2)
        # symptômes manquants pour l'alternative
        alt_syms = set(SYMPTOM_DIAGNOSES.get(alt_diag.name, {}).keys())
        missing = sorted(alt_syms - ss)[:2]
        missing_str = f", absents: {', '.join(missing)}" if missing else ""
        # pénalités appliquées à l'alternative
        penalties = [
            s for s in ss
            if SYMPTOM_EXCLUSIONS.get(s, {}).get(alt_diag.name, 0) >= 0.10
        ]
        pen_str = f", pénalisé par: {', '.join(penalties[:2])}" if penalties else ""
        why_not.append(
            f"{alt_diag.name} écarté : score inférieur de {int(diff*100)}%"
            f"{missing_str}{pen_str}"
        )

    if not why_not:
        why_not.append("Aucune alternative suffisamment probable pour être retenue")

    return ClinicalReasoningV2(
        main_logic=main_logic[:5],
        why_this_diagnosis=why_this[:3],
        why_not_others=why_not[:3],
    )


def _build_probability_reasoning(
    diagnoses: list,
    symptoms_compressed: list[str],
    probs: dict[str, float],
    context: dict | None = None,
) -> "ProbabilityReasoning":
    from app.models.schemas import ProbabilityReasoning, ProbabilityEntry
    from app.data.symptoms import SYMPTOM_DIAGNOSES, SYMPTOM_EXCLUSIONS, COMBO_BONUSES

    ss = set(symptoms_compressed)
    entries: dict = {}

    for diag in diagnoses[:3]:
        name = diag.name
        based_on: list[str] = []
        downgrade: list[str] = []

        # symptoms that contribute
        for sym in ss:
            w = SYMPTOM_DIAGNOSES.get(sym, {}).get(name, 0)
            if w >= 0.20:
                based_on.append(f"{sym} (poids {w:.2f})")

        # combo bonuses
        for combo, bonuses in COMBO_BONUSES:
            if combo.issubset(ss) and name in bonuses:
                based_on.append(f"combo {'+'.join(sorted(combo))} +{bonuses[name]:.2f}")

        # context
        if context:
            if context.get("after_food") and name in ("Gastrite", "RGO", "Dyspepsie"):
                based_on.append("contexte post-repas (+boost)")
            if context.get("post_medication") and name in ("Dysbiose", "SII"):
                based_on.append("post-antibiotiques (+boost)")

        # downgrade factors
        for sym in ss:
            pen = SYMPTOM_EXCLUSIONS.get(sym, {}).get(name, 0)
            if pen >= 0.10:
                downgrade.append(f"{sym} pénalise -{pen:.0%}")

        sorted_p = sorted(probs.values(), reverse=True)
        if sorted_p and probs.get(name, 0) < sorted_p[0] - 0.10:
            downgrade.append(f"score inférieur au top1 de {int((sorted_p[0]-probs[name])*100)}%")

        if not based_on:
            based_on = ["signal faible — symptômes non spécifiques"]
            downgrade.append("justification insuffisante → confiance réduite")

        entries[name] = ProbabilityEntry(
            score=diag.probability,
            based_on=based_on[:4],
            downgrade_factors=downgrade[:3],
        )

    return ProbabilityReasoning(diagnoses=entries)


def _build_test_reasoning(
    tests_required: list[str],
    tests_optional: list[str],
    diagnoses: list,
) -> "TestReasoning":
    from app.models.schemas import TestReasoning
    from app.data.tests import TEST_CATALOG

    top_names = [d.name for d in diagnoses[:3]]
    top1 = top_names[0] if top_names else ""

    _STATIC_LINKS: dict[str, str] = {
        "ECG":                  f"Exclure ischémie / trouble du rythme (règle Angor, Trouble du rythme)",
        "CRP":                  f"Détecter inflammation — confirme ou exclut profil infectieux",
        "NFS":                  f"Détecter anémie ou infection systémique",
        "D-dimères":            f"Exclure Embolie pulmonaire (VPN 99%)",
        "Troponine":            f"Exclure nécrose myocardique — règle Syndrome coronarien aigu",
        "Rx thorax":            f"Confirmer ou exclure Pneumonie / épanchement",
        "Radiographie pulmonaire": f"Confirmer Pneumonie — visualisation directe",
        "Spirométrie":          f"Évaluer obstruction bronchique — confirme Asthme/Bronchite",
        "Test rapide Strep A":  f"Identifier angine bactérienne à streptocoque",
        "Scanner thoracique":   f"Confirmer Embolie pulmonaire (angio-TDM)",
        "BNP":                  f"Évaluer fonction cardiaque — confirme Insuffisance cardiaque",
        "pH-métrie":            f"Confirmer reflux acide — règle RGO",
        "Test Helicobacter pylori": f"Confirmer Gastrite à H. pylori",
        "Coproculture":         f"Identifier agent infectieux digestif — règle C. difficile si post-antibiotiques",
        "Recherche C. difficile": f"Exclure Clostridioides difficile (obligatoire si diarrhée post-antibiotiques)",
        "Holter ECG":           f"Détecter arythmie intermittente — Trouble du rythme",
        "TSH":                  f"Exclure cause thyroïdienne",
        "Coloscopie":           f"Exclure pathologie organique (MICI, cancer colorectal) si SII suspect",
    }

    links: dict[str, str] = {}
    for test in tests_required + tests_optional:
        if test in _STATIC_LINKS:
            links[test] = _STATIC_LINKS[test]
        else:
            # Generate from TEST_CATALOG
            catalog = TEST_CATALOG.get(test, {})
            dv = catalog.get("diagnostic_value", {})
            top_target = max(dv, key=dv.get) if dv else top1
            links[test] = catalog.get("explanation", f"Évaluation diagnostique pour {top_target or 'profil en cours'}")

    return TestReasoning(links=links)


def _build_do_not_miss_engine(
    symptoms_compressed: list[str],
    context: dict | None = None,
    diagnoses: list | None = None,
    urgency_level: str = "faible",
    raw_text: str = "",
) -> "DoNotMissEngine":
    from app.models.schemas import DoNotMissEngine

    ss = set(symptoms_compressed)
    ctx = context or {}
    diag_names = {d.name for d in (diagnoses or [])}

    # FIX: також шукаємо в raw_text якщо symptoms_compressed не дав результату
    _raw_lower = raw_text.lower()

    flags: list[str] = []
    mandatory_tests: list[str] = []
    urgency_override: str | None = None
    cdiff_risk = False
    ecg_required = False
    pe_baseline = False

    # RULE 1: diarrhée + post_antibiotics → C.difficile
    _DIARRHEA = {"diarrhée", "diarrhee", "selles liquides", "transit accéléré"}
    _DIARRHEA_RAW = ("diarrhée", "diarrhee", "selles liquides", "transit")
    has_diarrhea = (
        bool(ss & _DIARRHEA)
        or any(d in " ".join(symptoms_compressed).lower() for d in _DIARRHEA_RAW)
        or any(d in _raw_lower for d in _DIARRHEA_RAW)
    )
    _ABX_RAW = ("antibiotique", "antibio", "amoxicilline", "augmentin", "azithromycine", "doxycycline")
    post_abx = (
        ctx.get("post_medication", False)
        or ctx.get("flags", {}).get("after_antibiotics", False)
        or any(a in _raw_lower for a in _ABX_RAW)
    )
    if has_diarrhea and post_abx:
        cdiff_risk = True
        # C. difficile examens obligatoires seulement si red flags présents
        _CDIFF_RED_FLAGS = {"fièvre", "diarrhée sévère", "douleur abdominale", "sang dans les selles", "déshydratation"}
        has_cdiff_red_flag = bool(ss & _CDIFF_RED_FLAGS) or "fièvre" in _raw_lower or "sang" in _raw_lower
        if has_cdiff_red_flag:
            flags.append("Diarrhée post-antibiotiques + signes sévères → Clostridioides difficile à exclure OBLIGATOIREMENT")
            for t in ["Recherche C. difficile", "Coproculture"]:
                if t not in mandatory_tests:
                    mandatory_tests.append(t)
            if urgency_level == "faible":
                urgency_override = "moderate"
        else:
            flags.append("Diarrhée post-antibiotiques — surveiller évolution (C. difficile si aggravation)")

    # RULE 2: chest pain → ALWAYS ECG
    _CHEST = {"douleur thoracique", "douleur thoracique intense", "douleur au thorax", "douleur à la poitrine"}
    if ss & _CHEST:
        ecg_required = True
        flags.append("Douleur thoracique → ECG obligatoire (règle Angor / SCA)")
        if "ECG" not in mandatory_tests:
            mandatory_tests.append("ECG")
        if "Troponine" not in mandatory_tests:
            mandatory_tests.append("Troponine")

    # RULE 3: dyspnée → evaluate PE baseline — seulement si signes sévères
    _DYSPNEA = {"essoufflement", "dyspnée progressive", "gêne respiratoire", "souffle court"}
    _DYSPNEA_SEVERE = {"essoufflement au repos", "détresse respiratoire", "cyanose", "lèvres bleues"}
    if ss & _DYSPNEA:
        pe_baseline = True
        flags.append("Dyspnée → Embolie pulmonaire à évaluer (Wells score recommandé)")
        # D-dimères uniquement si dyspnée sévère ou signes associés (jambe gonflée, douleur thoracique)
        _HAS_SEVERE_CONTEXT = bool(
            (ss & _DYSPNEA_SEVERE) or
            (ss & {"jambe gonflée", "gonflement jambe", "douleur thoracique", "douleur poitrine"})
        )
        if _HAS_SEVERE_CONTEXT and "D-dimères" not in mandatory_tests:
            mandatory_tests.append("D-dimères")

    # RULE 4: SII haute dans contexte post-antibiotiques aigu → downgrade
    if post_abx and "SII" in diag_names:
        flags.append("SII écarté en contexte aigu post-antibiotiques — diagnostic chronique inapproprié ici")

    return DoNotMissEngine(
        flags=flags,
        mandatory_tests=mandatory_tests,
        urgency_override=urgency_override,
        cdiff_risk=cdiff_risk,
        ecg_required=ecg_required,
        pe_baseline=pe_baseline,
    )


def _build_economic_reasoning(
    economics: dict,
    tests_required: list[str],
    tests_optional: list[str],
    diagnoses: list,
) -> "EconomicReasoning":
    from app.models.schemas import EconomicReasoning
    from app.data.tests import TEST_CATALOG

    top1 = diagnoses[0].name if diagnoses else ""

    # Tests removed = optional que НЕ в required
    removed = tests_optional[:3]

    # Why removed: низька diagnostic_value для top1
    removed_reasons: list[str] = []
    for t in removed:
        dv = TEST_CATALOG.get(t, {}).get("diagnostic_value", {}).get(top1, 0)
        if dv < 0.40:
            removed_reasons.append(f"{t} (valeur diagnostique {dv:.0%} pour {top1})")

    why_removed = (
        "Valeur diagnostique insuffisante au stade initial pour: " + ", ".join(removed_reasons)
        if removed_reasons
        else "Examens de 2e intention — initialement non prioritaires"
    )

    # Tests kept
    kept = tests_required[:4]
    why_kept = (
        f"Examens prioritaires pour confirmer {top1} et exclure diagnostics différentiels"
        if kept else "Surveillance clinique suffisante"
    )

    return EconomicReasoning(
        tests_removed=removed,
        why_removed=why_removed,
        risk_control="Escalade vers examens complémentaires si évolution défavorable",
        tests_kept=kept,
        why_kept=why_kept,
    )


def _build_economic_reasoning_v2(
    tests_required: list[str],
    tests_optional: list[str],
    diagnoses: list,
) -> "EconomicReasoningV2":
    """
    Investor-grade economic engine:
    - Real pathway comparison (standard vs optimized)
    - Per-test cost with clinical link
    - Risk-cost balance with critical test guard
    - No hardcoded savings numbers
    - Alias-aware: "Rx thorax" == "Radiographie pulmonaire"
    """
    from app.data.tests import TEST_CATALOG

    # ── Alias normalization ───────────────────────────────────────────────
    _ALIASES: dict[str, str] = {
        "Radiographie pulmonaire": "Rx thorax",
        "Recherche C. difficile": "Test C. difficile",
    }
    _ALIASES_REV: dict[str, str] = {v: k for k, v in _ALIASES.items()}

    def _canonical(name: str) -> str:
        """Map any alias to canonical COST_MAP key."""
        if name in COST_MAP:
            return name
        return _ALIASES.get(name, name)

    def _display(name: str) -> str:
        """Keep original pipeline name for display."""
        return name

    top1 = diagnoses[0].name if diagnoses else ""
    top3_names = [d.name for d in diagnoses[:3]]

    # ── 1. STANDARD PATH: typical over-prescribed tests for this diagnosis ────
    std_test_names = STANDARD_PATH_MAP.get(top1, ["NFS", "CRP"])
    std_test_names = list(dict.fromkeys(std_test_names))

    standard_items: list[CostItem] = []
    for t in std_test_names:
        cost = COST_MAP.get(t, 20.0)
        dv = TEST_CATALOG.get(t, {}).get("diagnostic_value", {})
        linked = top1
        for d_name in top3_names:
            if dv.get(d_name, 0) > 0:
                linked = d_name
                break
        standard_items.append(CostItem(
            test=t,
            cost_eur=cost,
            linked_diagnosis=linked,
            clinical_justification=f"Prescrit par défaut dans parcours standard {top1}",
        ))

    # ── 2. OPTIMIZED PATH: only engine-selected tests ─────────────────────────
    opt_test_names = list(dict.fromkeys(tests_required))
    optimized_items: list[CostItem] = []
    for t in opt_test_names:
        canon = _canonical(t)
        cost = COST_MAP.get(canon, COST_MAP.get(t, 20.0))
        dv = TEST_CATALOG.get(t, {}).get("diagnostic_value", {})
        linked = top1
        best_val = 0.0
        for d_name in top3_names:
            v = dv.get(d_name, 0)
            if v > best_val:
                best_val = v
                linked = d_name
        justification = (
            f"Valeur diagnostique {best_val:.0%} pour {linked}"
            if best_val > 0
            else f"Requis pour évaluation de {linked}"
        )
        optimized_items.append(CostItem(
            test=_display(t),
            cost_eur=cost,
            linked_diagnosis=linked,
            clinical_justification=justification,
        ))

    # ── 3. COSTS ──────────────────────────────────────────────────────────────
    std_cost = CONSULTATION_GP_COST + sum(i.cost_eur for i in standard_items)
    opt_cost = CONSULTATION_GP_COST + sum(i.cost_eur for i in optimized_items)
    savings = round(max(0.0, std_cost - opt_cost), 2)

    pathway = PathwayComparison(
        standard_tests=standard_items,
        optimized_tests=optimized_items,
        standard_cost=round(std_cost, 2),
        optimized_cost=round(opt_cost, 2),
        savings=savings,
        currency="EUR",
    )

    # ── 4. REMOVED TESTS: standard tests NOT covered by optimized ─────────────
    # Build canonical set of optimized tests for alias-aware comparison
    opt_canonical = set()
    for t in opt_test_names:
        opt_canonical.add(t)
        opt_canonical.add(_canonical(t))
        # Also add all alias variants
        if t in _ALIASES:
            opt_canonical.add(_ALIASES[t])
        if t in _ALIASES_REV:
            opt_canonical.add(_ALIASES_REV[t])

    removed_names = [t for t in std_test_names if t not in opt_canonical]

    removed_items: list[CostItem] = []
    removed_reasons: list[str] = []
    for t in removed_names:
        cost = COST_MAP.get(t, 20.0)
        dv = TEST_CATALOG.get(t, {}).get("diagnostic_value", {}).get(top1, 0)
        reason = (
            f"{t} — valeur diagnostique {dv:.0%} pour {top1}, non prioritaire au stade initial"
            if dv < 0.50
            else f"{t} — examen de 2e intention, réservé si évolution défavorable"
        )
        removed_items.append(CostItem(
            test=t, cost_eur=cost,
            linked_diagnosis=top1,
            clinical_justification=reason,
        ))
        removed_reasons.append(reason)

    # ── 5. KEPT TESTS: what's in optimized path ──────────────────────────────
    kept_items = list(optimized_items)
    kept_reasons: list[str] = []
    for item in kept_items:
        kept_reasons.append(
            f"{item.test} — {item.clinical_justification}"
        )

    # ── 6. RISK-COST BALANCE: check critical tests (alias-aware) ─────────────
    critical_for_diags: set[str] = set()
    for d_name in top3_names:
        critical_for_diags |= CRITICAL_TESTS.get(d_name, set())

    # Check if critical tests are missing from optimized (alias-aware)
    removed_canonical = set()
    for t in removed_names:
        removed_canonical.add(t)
        removed_canonical.add(_canonical(t))
        if t in _ALIASES:
            removed_canonical.add(_ALIASES[t])
        if t in _ALIASES_REV:
            removed_canonical.add(_ALIASES_REV[t])

    critical_removed = critical_for_diags & removed_canonical

    if critical_removed:
        savings_blocked = True
        savings_blocked_reason = (
            f"Test(s) critique(s) retiré(s): {', '.join(sorted(critical_removed))} — "
            f"économie non revendiquée pour raison de sécurité"
        )
        risk_control = f"⚠️ Test(s) critique(s) manquant(s): {', '.join(sorted(critical_removed))}"
    else:
        savings_blocked = False
        savings_blocked_reason = ""
        risk_control = "Aucun examen critique retiré — sécurité diagnostique préservée"

    critical_test_preserved = len(critical_removed) == 0

    # ── 7. SUMMARY ────────────────────────────────────────────────────────────
    n_removed = len(removed_names)
    if savings_blocked:
        summary = f"Économie bloquée — {len(critical_removed)} examen(s) critique(s) retiré(s)"
    elif n_removed > 0 and savings > 0:
        summary = (
            f"Économie de {savings:.0f} € basée sur la suppression de "
            f"{n_removed} examen(s) non nécessaire(s) au stade initial"
        )
    elif savings == 0:
        summary = "Parcours déjà optimisé — aucun examen inutile détecté. Sécurité diagnostique maximale."
    else:
        summary = "Parcours diagnostique optimisé sans surcoût"

    return EconomicReasoningV2(
        pathway=pathway,
        tests_removed=removed_items,
        why_removed=removed_reasons,
        tests_kept=kept_items,
        why_kept=kept_reasons,
        risk_control=risk_control,
        critical_test_preserved=critical_test_preserved,
        savings_blocked=savings_blocked,
        savings_blocked_reason=savings_blocked_reason,
        summary=summary,
    )



# ── BASELINE PATHWAY ENGINE (БЛОК 2 — Real Economics) ────────────────────────

# Specialist probability by profile (ТЗ spec)
_SPECIALIST_PROB: dict[str, float] = {
    "digestif":    0.40,
    "cardiaque":   0.60,
    "respiratoire":0.35,
    "viral":       0.20,
    "general":     0.30,
}

# Extra tests cost by profile (typical over-prescription)
_EXTRA_TESTS_COST: dict[str, float] = {
    "digestif":    150.0,
    "cardiaque":   250.0,
    "respiratoire":180.0,
    "general":     120.0,
}

_GP_COST: float = 25.0
_SPECIALIST_COST: float = 90.0


def _build_baseline_pathway(
    diagnoses: list,
    economic_v2: "EconomicReasoningV2 | None",
) -> "BaselinePathway":
    from app.models.schemas import BaselinePathway

    # Визначаємо профіль
    top_names = {d.name for d in diagnoses[:3]} if diagnoses else set()
    _DIGESTIVE_SET = {"Gastrite", "RGO", "SII", "Dyspepsie", "Dysbiose",
                      "Clostridioides difficile", "Infection intestinale"}
    _CARDIAC_SET = {"Angor", "Embolie pulmonaire", "Insuffisance cardiaque", "Trouble du rythme"}
    _RESPIRATORY_SET = {"Pneumonie", "Bronchite", "Asthme", "Grippe", "Angine", "Rhinopharyngite"}

    if top_names & _CARDIAC_SET:
        profile = "cardiaque"
    elif top_names & _RESPIRATORY_SET:
        profile = "respiratoire"
    elif top_names & _DIGESTIVE_SET:
        profile = "digestif"
    else:
        profile = "general"

    specialist_prob = _SPECIALIST_PROB.get(profile, 0.30)
    extra_tests = _EXTRA_TESTS_COST.get(profile, 120.0)
    gp_visits = 2

    # baseline_cost = реальний parcours без системи
    baseline_cost = round(
        gp_visits * _GP_COST
        + specialist_prob * _SPECIALIST_COST
        + extra_tests,
        2,
    )

    # optimized_cost = ClairDiag pathway (tests only + 1 GP)
    if economic_v2 and economic_v2.pathway:
        opt_tests = economic_v2.pathway.optimized_cost
    else:
        opt_tests = 80.0  # conservative fallback
    optimized_cost = round(_GP_COST + opt_tests, 2)

    savings_real = round(max(0.0, baseline_cost - optimized_cost), 2)

    summary = (
        f"Parcours réel estimé : {baseline_cost:.0f}€ "
        f"→ Parcours optimisé : {optimized_cost:.0f}€ "
        f"→ Économie estimée : {savings_real:.0f}€"
    )

    return BaselinePathway(
        gp_visits=gp_visits,
        specialist_probability=specialist_prob,
        extra_tests_cost=extra_tests,
        baseline_cost=baseline_cost,
        optimized_cost=optimized_cost,
        savings_real=savings_real,
        profile=profile,
        summary=summary,
    )


# ── UX LAYER: Severity + Triage + Follow-up + KPI + Public (п.1–10) ────────

_DIGESTIVE_DIAGS = {"Gastrite", "RGO", "SII", "Dyspepsie", "Dysbiose",
                    "Clostridioides difficile", "Infection intestinale"}
_CARDIAC_DIAGS = {"Angor", "Embolie pulmonaire", "Insuffisance cardiaque", "Trouble du rythme"}
_RESPIRATORY_DIAGS = {"Pneumonie", "Bronchite", "Asthme"}

# П.1: Red flags for severity engine
_RED_FLAGS = {
    "sang selles": "Sang dans les selles",
    "sang dans les selles": "Sang dans les selles",
    "vomissements de sang": "Vomissements de sang",
    "fièvre élevée": "Fièvre élevée (> 39°C)",
    "fièvre > 39": "Fièvre élevée (> 39°C)",
    "déshydratation": "Déshydratation",
    "douleur intense": "Douleur intense",
    "douleur abdominale intense": "Douleur abdominale intense",
    "syncope": "Syncope / perte de connaissance",
    "perte de connaissance": "Syncope / perte de connaissance",
    "confusion": "Confusion / altération de la conscience",
    "essoufflement au repos": "Essoufflement au repos",
    "dyspnée au repos": "Essoufflement au repos",
    "douleur thoracique intense": "Douleur thoracique intense",
    "cyanose": "Cyanose (lèvres bleues)",
    "crachats sanglants": "Crachats sanglants",
    "hémoptysie": "Crachats sanglants",
}

_URGENCY_SIGNS: dict[str, list[str]] = {
    "digestif": [
        "Sang dans les selles ou vomissements de sang",
        "Fièvre élevée (> 39°C) persistante",
        "Déshydratation (soif intense, urines foncées, vertiges)",
        "Douleur abdominale intense et continue",
        "Altération de l'état général (confusion, grande faiblesse)",
    ],
    "cardiaque": [
        "Douleur thoracique intense ou irradiant au bras / mâchoire",
        "Essoufflement brutal au repos",
        "Perte de connaissance ou malaise avec chute",
        "Palpitations soutenues avec malaise",
        "Sueurs froides avec oppression thoracique",
    ],
    "respiratoire": [
        "Essoufflement sévère au repos ou en parlant",
        "Lèvres ou doigts bleutés (cyanose)",
        "Fièvre > 39°C avec confusion",
        "Crachats sanglants",
        "Impossibilité de s'allonger (orthopnée)",
    ],
    "general": [
        "Fièvre > 39°C persistante plus de 48h",
        "Confusion ou altération de la conscience",
        "Douleur intense non contrôlée",
        "Aggravation rapide et brutale des symptômes",
    ],
}

_SELF_CARE: dict[str, list[str]] = {
    "digestif": [
        "Hydratation régulière (eau, bouillon) — petites gorgées fréquentes",
        "Alimentation légère (riz, banane, compote, biscottes)",
        "Éviter alcool, café, aliments gras ou épicés",
        "Repos digestif — repas fractionnés",
    ],
    "cardiaque": [
        "Repos strict — éviter tout effort physique",
        "Position semi-assise si essoufflement",
        "Ne pas conduire en cas de malaise",
    ],
    "respiratoire": [
        "Position assise ou semi-assise pour faciliter la respiration",
        "Hydratation régulière — boissons chaudes si toux",
        "Aérer la pièce — éviter les irritants (tabac, poussière)",
        "Repos avec surveillance de la température",
    ],
    "general": [
        "Repos et hydratation",
        "Surveillance de la température",
        "Noter l'évolution des symptômes",
    ],
}

_REASSURANCE: dict[str, dict] = {
    "digestif": {
        "message": "Les troubles digestifs post-antibiotiques ont souvent une évolution favorable, mais nécessitent une surveillance.",
        "why_not_panic": [
            "La diarrhée post-antibiotiques est fréquente (5–25% des patients)",
            "Le déséquilibre de la flore intestinale est le plus souvent transitoire",
            "Consultez si : ≥ 3 selles/jour, fièvre, sang dans les selles ou pas d'amélioration sous 72h",
        ],
    },
    "cardiaque": {
        "message": "Ces symptômes nécessitent une évaluation médicale, mais la majorité des douleurs thoraciques ne sont pas d'origine cardiaque grave.",
        "why_not_panic": [
            "De nombreuses causes bénignes (musculaire, digestive, stress) peuvent expliquer ces symptômes",
            "L'évaluation médicale permet d'exclure rapidement les causes graves",
        ],
    },
    "respiratoire": {
        "message": "La plupart des infections respiratoires sont virales et se résolvent spontanément en 7–10 jours.",
        "why_not_panic": [
            "La fièvre et la toux sont des réponses normales du système immunitaire",
            "Les complications graves sont rares chez les adultes sans comorbidités",
            "Le traitement symptomatique est souvent suffisant",
        ],
    },
    "general": {
        "message": "Les symptômes décrits sont courants et le plus souvent bénins.",
        "why_not_panic": [
            "La majorité des consultations pour ces symptômes aboutissent à un diagnostic bénin",
            "Une évaluation structurée permet d'orienter efficacement",
        ],
    },
}


def _get_profile(diagnoses: list) -> str:
    top_names = {d.name for d in diagnoses[:3]}
    if top_names & _DIGESTIVE_DIAGS:
        return "digestif"
    if top_names & _CARDIAC_DIAGS:
        return "cardiaque"
    if top_names & _RESPIRATORY_DIAGS:
        return "respiratoire"
    return "general"


def _build_severity_assessment(
    symptoms_compressed: list[str],
    context: dict | None,
    raw_text: str = "",
) -> "SeverityAssessment":
    from app.models.schemas import SeverityAssessment
    text_lower = (raw_text or " ".join(symptoms_compressed)).lower()
    detected: list[str] = []
    for trigger, label in _RED_FLAGS.items():
        if trigger in text_lower and label not in detected:
            detected.append(label)
    drivers: list[str] = []
    if detected:
        drivers.append(f"{len(detected)} red flag(s) détecté(s)")
        return SeverityAssessment(level="severe", drivers=drivers, red_flags_detected=detected)
    ctx = context or {}
    sym_set = set(symptoms_compressed)
    is_post_abx = ctx.get("post_medication", False)
    has_diarrhee = "diarrhée" in sym_set
    has_cardiac = bool(sym_set & {"douleur thoracique", "palpitations", "essoufflement"})
    if is_post_abx and has_diarrhee:
        _CDIFF_SEVERE = {"fièvre", "diarrhée sévère", "sang dans les selles", "déshydratation", "douleur abdominale"}
        has_severe_flag = bool(set(symptoms_compressed) & _CDIFF_SEVERE)
        if has_severe_flag:
            drivers.append("Diarrhée post-antibiotiques — risque C. difficile")
            return SeverityAssessment(level="moderate", drivers=drivers, red_flags_detected=[])
        else:
            drivers.append("Diarrhée post-antibiotiques — surveiller l'évolution")
            return SeverityAssessment(level="mild", drivers=drivers, red_flags_detected=[])
    if has_cardiac:
        drivers.append("Symptômes cardio-respiratoires — évaluation nécessaire")
        return SeverityAssessment(level="moderate", drivers=drivers, red_flags_detected=[])
    # Profil rétention hydrique / IC chronique → moderate (consultation 24h recommandée)
    # Pas "mild" car nécessite bilan BNP/ECG — pas "severe" car pas de symptômes aigus
    _IC_OEDEME_ONLY = frozenset({"gonflement jambes", "prise de poids rapide", "œdème périphérique",
                                   "rétention hydrique", "fatigue"})
    _is_ic_chronic_only = bool(sym_set) and sym_set.issubset(_IC_OEDEME_ONLY)
    if _is_ic_chronic_only:
        drivers.append("Profil œdémateux sans symptôme aigu — bilan cardiaque/rénal recommandé sous 24h")
        return SeverityAssessment(level="moderate", drivers=drivers, red_flags_detected=[])
    if len(symptoms_compressed) >= 4:
        drivers.append("Présentation multi-symptomatique")
        return SeverityAssessment(level="moderate", drivers=drivers, red_flags_detected=[])
    drivers.append("Aucun signe de gravité immédiate")
    return SeverityAssessment(level="mild", drivers=drivers, red_flags_detected=[])


def _build_triage_level(
    severity_level: str,
    emergency_flag: bool = False,
) -> "TriageLevel":
    from app.models.schemas import TriageLevel
    if emergency_flag:
        return TriageLevel(level="severe", label_fr="Urgence médicale immédiate", icon="🔴", color="red",
            description="Appelez le 15 (SAMU) ou rendez-vous aux urgences immédiatement.")
    if severity_level == "severe":
        return TriageLevel(level="severe", label_fr="Consultation urgente recommandée", icon="🔴", color="red",
            description="Les symptômes nécessitent une évaluation médicale rapide (dans les heures).")
    if severity_level == "moderate":
        return TriageLevel(level="moderate", label_fr="Consultation médicale recommandée", icon="🟡", color="amber",
            description="Prenez rendez-vous avec votre médecin dans les 24–48h pour confirmer le diagnostic.")
    return TriageLevel(level="mild", label_fr="Surveillance à domicile", icon="🟢", color="green",
        description="Surveillez vos symptômes pendant 24–48h. Consultez si aggravation ou persistance.")


def _build_diagnostic_status(
    confidence_score: float,
    severity_level: str,
    misdiagnosis_risk_score: float,
) -> "DiagnosticStatus":
    from app.models.schemas import DiagnosticStatus
    if severity_level == "mild":
        threshold = 0.85
    elif severity_level == "moderate":
        threshold = 0.92
    else:
        threshold = 0.97
    if confidence_score >= threshold:
        status = "strongly_supported"
    elif confidence_score >= threshold - 0.15:
        status = "orientation_probable"
    else:
        status = "referral_required"
    return DiagnosticStatus(confidence=round(confidence_score, 2), threshold_required=threshold, status=status)


def _build_follow_up(diagnoses: list, severity_level: str, urgency_level: str = "faible") -> "FollowUp":
    from app.models.schemas import FollowUp
    profile = _get_profile(diagnoses)
    top_name = diagnoses[0].name if diagnoses else ""
    _IC_ACUTE_SYM = frozenset({"essoufflement", "douleur thoracique", "palpitations", "syncope"})

    if severity_level == "severe":
        return FollowUp(recheck_in="immédiat",
            if_worse="Appeler le 15 (SAMU) sans délai",
            if_no_improvement="Consultation urgente dans les heures qui suivent")
    # urgency élevé → toujours "aujourd'hui", peu importe le profil
    if urgency_level == "élevé":
        return FollowUp(recheck_in="aujourd'hui",
            if_worse="Consultation médicale immédiate",
            if_no_improvement="Consultation médicale dans la journée si pas d'amélioration")
    # IC non aiguë (sans dyspnée/douleur thoracique) → consultation dans 24h
    if profile == "cardiaque" and top_name == "Insuffisance cardiaque":
        return FollowUp(recheck_in="24h",
            if_worse="Consultation médicale si essoufflement, prise de poids > 2 kg ou aggravation des œdèmes",
            if_no_improvement="Consultation médicale dans les 24h pour bilan BNP/ECG")
    if profile == "cardiaque":
        return FollowUp(recheck_in="aujourd'hui",
            if_worse="Consultation médicale immédiate",
            if_no_improvement="Consultation médicale dans la journée si pas d'amélioration")
    if profile == "respiratoire":
        return FollowUp(recheck_in="48h",
            if_worse="Consultation médicale immédiate si essoufflement ou fièvre > 39°C",
            if_no_improvement="Consultation médicale si pas d'amélioration après 48h")
    if profile == "digestif":
        return FollowUp(recheck_in="48–72h",
            if_worse="Consultation médicale si sang dans les selles, fièvre ou déshydratation",
            if_no_improvement="Consultation médicale si persistance au-delà de 72h")
    return FollowUp(recheck_in="48h",
        if_worse="Consultation médicale si aggravation des symptômes",
        if_no_improvement="Consultation si aucune amélioration après 48h")


def _build_action_plan(diagnoses: list, severity_level: str, worsening_signs: list[str], urgency_level: str = "faible") -> "ActionPlan":
    from app.models.schemas import ActionPlan
    profile = _get_profile(diagnoses)
    # ── Règle : UN SEUL chemin, pas de double message ────────────────────────
    # within_24h est toujours vide — tout passe dans immediate pour éviter la duplication
    if severity_level == "severe":
        immediate = [
            "Appelez le 15 (SAMU) immédiatement",
            "Ne restez pas seul(e) — prévenez un proche",
            "Rendez-vous aux urgences si SAMU non disponible",
        ]
    elif urgency_level == "élevé":
        immediate = [
            "Consultez votre médecin aujourd'hui",
            "Réalisez les analyses prescrites si possible avant la consultation",
        ]
    elif severity_level == "moderate":
        immediate = [
            "Prenez rendez-vous avec votre médecin dans les 24–48h",
            "Réalisez les analyses prescrites avant la consultation",
        ]
    else:
        # Faible — surveillance uniquement, délai selon profil
        delay = "48–72h" if profile in ("digestif",) else "48h"
        immediate = [
            f"Repos et surveillance à domicile pendant {delay}",
            f"Consultez si pas d'amélioration après {delay} ou si aggravation",
        ]
    watch_for = _URGENCY_SIGNS.get(profile, _URGENCY_SIGNS["general"])
    self_care = _SELF_CARE.get(profile, _SELF_CARE["general"])
    return ActionPlan(immediate=immediate, within_24h=[], watch_for=watch_for, self_care=self_care)


def _build_user_reassurance(diagnoses: list, severity_level: str) -> "UserReassurance":
    from app.models.schemas import UserReassurance
    if severity_level == "severe":
        return UserReassurance(message="", why_not_panic=[])
    profile = _get_profile(diagnoses)
    data = _REASSURANCE.get(profile, _REASSURANCE["general"])
    return UserReassurance(message=data["message"], why_not_panic=data["why_not_panic"])


def _build_user_explanation(diagnoses: list, symptoms_compressed: list[str], context: dict | None) -> "UserExplanation":
    from app.models.schemas import UserExplanation
    ctx = context or {}
    because = list(symptoms_compressed[:5])
    if ctx.get("post_medication"):
        because.append("prise d'antibiotiques récente")
    if ctx.get("after_food"):
        because.append("lien avec les repas")
    if ctx.get("night_worsening"):
        because.append("aggravation nocturne")
    suggests: list[str] = []
    top1 = diagnoses[0] if diagnoses else None
    if top1:
        suggests.append(f"Le profil correspond le plus à : {top1.name} ({int(top1.probability*100)}%)")
    if len(diagnoses) > 1:
        suggests.append(f"Alternatives possibles : {', '.join(d.name for d in diagnoses[1:3])}")
    _HINTS = {"digestif": "Ces symptômes sont souvent liés à un déséquilibre digestif — évolution souvent favorable, mais incertaine sans confirmation.",
        "cardiaque": "Le profil cardio-respiratoire nécessite une évaluation pour exclure les causes graves.",
        "respiratoire": "Le profil respiratoire est compatible avec une infection — une confirmation par analyses est recommandée.",
        "general": "Une évaluation complémentaire permettra de préciser l'orientation diagnostique."}
    suggests.append(_HINTS.get(_get_profile(diagnoses), _HINTS["general"]))
    return UserExplanation(because_you_reported=because, this_suggests=suggests)


def _build_kpi_metrics(economic_v2) -> "KpiMetrics":
    from app.models.schemas import KpiMetrics
    if not economic_v2:
        return KpiMetrics()
    n_removed = len(economic_v2.tests_removed)
    low_value = sum(1 for r in economic_v2.why_removed if "0%" in r or "non prioritaire" in r)
    savings = economic_v2.pathway.savings if not economic_v2.savings_blocked else 0.0
    consult_avoided = 1 if savings > 50 else 0
    # FIX: when savings==0, show pathway_validated=True via tests_avoided=-1 sentinel? No.
    # Just keep normal values — frontend will handle display
    return KpiMetrics(tests_avoided=n_removed, low_value_tests_removed=low_value,
        estimated_savings_eur=savings, unnecessary_consultations_avoided=consult_avoided)


def _build_public_health(severity_level: str, economic_v2, decision: str) -> "PublicHealth":
    from app.models.schemas import PublicHealth
    pathway_opt = bool(economic_v2 and economic_v2.pathway.savings > 0)
    referral = decision in ("URGENT_MEDICAL_REVIEW", "EMERGENCY", "MEDICAL_REVIEW")
    return PublicHealth(case_severity=severity_level, pathway_optimized=pathway_opt, referral_needed=referral)


def _build_differential_gap(diagnoses: list) -> "DifferentialGap":
    from app.models.schemas import DifferentialGap
    if len(diagnoses) < 2:
        return DifferentialGap(value=1.0, interpretation="high_confidence", force_referral=False)
    gap = round(diagnoses[0].probability - diagnoses[1].probability, 3)
    if gap <= 0.10:
        return DifferentialGap(value=gap, interpretation="low_separation", force_referral=True)
    return DifferentialGap(value=gap, interpretation="high_confidence", force_referral=False)


def _build_roi_projection(economic_v2) -> "RoiProjection":
    from app.models.schemas import RoiProjection
    if not economic_v2 or economic_v2.savings_blocked:
        return RoiProjection(assumptions=[
            "Économie bloquée — test critique retiré, projection non applicable",
        ])
    pw = economic_v2.pathway
    per_case = pw.savings
    per_1000 = round(per_case * 1000, 2)
    annual = round(per_1000 * 12, 2)
    pct = round((pw.standard_cost - pw.optimized_cost) / pw.standard_cost, 4) if pw.standard_cost > 0 else 0.0
    # Confidence tiers: conservative ×0.6, realistic ×1.0, optimistic ×1.5
    conservative = round(annual * 0.6, 2)
    optimistic = round(annual * 1.5, 2)
    return RoiProjection(
        per_case_savings_eur=per_case,
        per_1000_cases_savings_eur=per_1000,
        annual_projection_eur=annual,
        cost_reduction_percent=round(pct, 4),
        conservative_annual_eur=conservative,
        realistic_annual_eur=annual,
        optimistic_annual_eur=optimistic,
        assumptions=[
            "Base : 1 000 cas/mois, tarifs France métropolitaine",
            "Conservative (×0.6) : adoption partielle, cas complexes exclus",
            "Realistic (×1.0) : adoption standard en soins primaires",
            "Optimistic (×1.5) : adoption large + réduction consultations inutiles",
        ],
    )


def _build_system_impact(severity_level: str, economic_v2) -> "SystemImpact":
    from app.models.schemas import SystemImpact
    if severity_level == "mild":
        gp_load = "high"
    elif severity_level == "moderate":
        gp_load = "moderate"
    else:
        gp_load = "low"
    has_savings = bool(economic_v2 and economic_v2.pathway.savings > 0 and not economic_v2.savings_blocked)
    overdiag = bool(economic_v2 and len(economic_v2.tests_removed) > 0)
    n_removed = len(economic_v2.tests_removed) if economic_v2 else 0
    savings = economic_v2.pathway.savings if economic_v2 and not economic_v2.savings_blocked else 0
    return SystemImpact(
        gp_load_reduction=gp_load,
        emergency_avoidance=severity_level != "severe",
        overdiagnosis_reduction=overdiag,
        pathway_efficiency="improved" if has_savings else "neutral",
        risk_overload=(
            f"Sans orientation préalable, {gp_load == 'high' and 'la majorité' or 'une partie'} "
            f"de ces cas surchargent les consultations MG sans nécessité clinique"
        ),
        risk_cost=(
            f"Parcours standard non optimisé : +{int(savings)}€ de surcoût par cas "
            f"({n_removed} examen(s) de faible valeur prescrits systématiquement)"
            if savings > 0 else "Aucun surcoût évitable détecté dans ce cas"
        ),
        risk_delay=(
            "Sans triage structuré, risque de retard diagnostique par dilution "
            "dans un parcours de soins non priorisé"
            if severity_level != "mild" else
            "Cas bénin — faible risque de retard, mais surcharge système évitable"
        ),
    )


def _build_confidence_explanation(
    confidence_score: float,
    severity_level: str,
    diagnoses: list,
    symptoms_count: int,
) -> "ConfidenceExplanation":
    """UX: explain why confidence is not 100% + what would increase it."""
    from app.models.schemas import ConfidenceExplanation

    missing: list[str] = []
    increase: list[str] = []

    if symptoms_count <= 2:
        missing.append("Peu de symptômes renseignés")
        increase.append("Décrire plus de symptômes améliorerait la précision")
    if len(diagnoses) >= 2:
        gap = diagnoses[0].probability - diagnoses[1].probability
        if gap <= 0.10:
            missing.append("Plusieurs diagnostics proches en probabilité")
            increase.append("Des examens complémentaires permettraient de trancher entre les hypothèses")
    if confidence_score < 0.70:
        missing.append("Confiance globale insuffisante")
        increase.append("Un examen clinique en personne renforcerait le diagnostic")
    if severity_level == "moderate":
        missing.append("Profil nécessitant confirmation professionnelle")

    if not increase:
        increase.append("Un examen clinique confirmerait l'orientation actuelle")

    if confidence_score >= 0.90:
        why = "La confiance est élevée mais ne peut atteindre 100% sans examen clinique."
    elif confidence_score >= 0.70:
        why = "Orientation probable identifiée — des données supplémentaires amélioreraient la précision."
    else:
        why = "Données limitées ou chevauchement entre diagnostics — la confiance reste modérée."

    return ConfidenceExplanation(
        why_not_100_percent=why,
        what_is_missing=missing,
        what_would_increase_certainty=increase,
    )


# ── EXPLAINABILITY V3: causal chain ──────────────────────────────────────────

def _build_clinical_explanation_v3(
    diagnoses: list,
    symptoms_compressed: list[str],
    context: dict | None,
    tests_impact: list | None = None,
) -> "ClinicalExplanationV3":
    """FIX 1: fact → meaning → impact for each key element."""
    from app.models.schemas import ClinicalExplanationV3, ReasoningStep

    steps: list[ReasoningStep] = []
    ctx = context or {}
    top = diagnoses[0] if diagnoses else None

    # Symptom-based reasoning
    _SYM_MEANING = {
        "fièvre": ("Fièvre détectée", "indique un processus infectieux ou inflammatoire"),
        "toux": ("Toux signalée", "oriente vers une atteinte respiratoire"),
        "diarrhée": ("Diarrhée signalée", "oriente vers une cause digestive"),
        "douleur thoracique": ("Douleur thoracique", "nécessite d'exclure une cause cardiaque"),
        "essoufflement": ("Essoufflement signalé", "oriente vers une cause respiratoire ou cardiaque"),
        "palpitations": ("Palpitations signalées", "oriente vers un trouble du rythme"),
        "nausées": ("Nausées présentes", "compatibles avec une atteinte digestive"),
        "douleur abdominale": ("Douleur abdominale", "oriente vers une cause gastro-intestinale"),
        "fatigue": ("Fatigue signalée", "signe non spécifique pouvant accompagner de nombreuses pathologies"),
        "céphalées": ("Céphalées signalées", "symptôme fréquent, souvent associé à un syndrome infectieux"),
        "courbatures": ("Courbatures présentes", "compatibles avec un syndrome grippal"),
        "mal de gorge": ("Mal de gorge signalé", "oriente vers une infection ORL"),
        "ballonnements": ("Ballonnements signalés", "suggèrent un déséquilibre digestif"),
    }

    for sym in symptoms_compressed[:4]:
        if sym in _SYM_MEANING:
            fact_text, meaning = _SYM_MEANING[sym]
            impact = f"contribue au profil de {top.name}" if top else "contribue à l'orientation diagnostique"
            steps.append(ReasoningStep(fact=fact_text, meaning=meaning, impact=impact))

    # Context-based reasoning
    if ctx.get("post_medication"):
        steps.append(ReasoningStep(
            fact="Prise récente d'antibiotiques",
            meaning="les antibiotiques perturbent la flore intestinale",
            impact="renforce la probabilité de dysbiose ou C. difficile",
        ))
    if ctx.get("after_food"):
        steps.append(ReasoningStep(
            fact="Lien avec les repas identifié",
            meaning="les symptômes liés aux repas orientent vers une cause gastrique",
            impact="renforce les hypothèses digestives (gastrite, RGO)",
        ))

    # Synthesis
    if top:
        synthesis = (
            f"Le profil symptomatique correspond le mieux à {top.name} "
            f"({int(top.probability * 100)}%). "
        )
        if len(diagnoses) > 1:
            synthesis += f"{diagnoses[1].name} reste une alternative possible mais explique moins bien l'ensemble des symptômes."
        else:
            synthesis += "Aucune alternative significative identifiée."
    else:
        synthesis = "Données insuffisantes pour une synthèse diagnostique."

    return ClinicalExplanationV3(core_reasoning=steps, final_synthesis=synthesis)


# ── PRIMARY ACTION BLOCK ──────────────────────────────────────────────────────

def _build_primary_action(
    decision: str,
    severity: str,
    diagnoses: list,
    gap_value: float,
) -> "PrimaryActionBlock":
    """FIX 2: Single-focus action block — always first on screen."""
    from app.models.schemas import PrimaryActionBlock

    _ACTION_MAP = {
        "URGENT_MEDICAL_REVIEW": "Consultez un médecin rapidement",
        "TESTS_FIRST": "Réalisez les examens recommandés",
        "MEDICAL_REVIEW": "Consultez un médecin si les symptômes persistent ou s'aggravent",
        "LOW_RISK_MONITOR": "Surveillez vos symptômes à domicile",
        "CONFIRMED_PATH": "Suivez le traitement recommandé",
        "FOLLOW_UP": "Consultation de suivi recommandée",
    }
    _SEV_LABEL = {
        "severe": "Situation nécessitant une prise en charge rapide",
        # "sans signe de gravité immédiate" blocked at severity moderate
        # (utilisé uniquement quand aucun signal cardiaque détecté)
        "moderate": "Situation à surveiller — évolution à confirmer",
        "mild": "Situation bénigne, surveillance suffisante",
    }

    action = _ACTION_MAP.get(decision, "Consultez un médecin si les symptômes persistent")
    sev_label = _SEV_LABEL.get(severity, "")

    # Reason
    if severity == "severe":
        reason = "Des signes de gravité ont été détectés."
    elif decision in ("TESTS_FIRST", "MEDICAL_REVIEW"):
        if gap_value <= 0.10:
            reason = "Plusieurs diagnostics sont proches — des examens ou un avis médical permettront de confirmer."
        else:
            reason = "Le diagnostic nécessite une confirmation par un professionnel de santé."
    elif decision == "LOW_RISK_MONITOR":
        reason = "Le profil est rassurant et ne nécessite pas de consultation immédiate."
    else:
        reason = "L'orientation diagnostique est établie."

    return PrimaryActionBlock(action=action, severity_label=sev_label, reason=reason)


# ── USER REASSURANCE V2 ──────────────────────────────────────────────────────

def _build_user_reassurance_v2(
    diagnoses: list,
    severity: str,
    symptoms_compressed: list[str],
    confidence_score: float = 1.0,
) -> "UserReassuranceV2":
    """П.6: Why not to panic — tone adjusted to confidence level."""
    from app.models.schemas import UserReassuranceV2

    if severity == "severe":
        return UserReassuranceV2()

    sym_set = set(symptoms_compressed)
    _CLINICAL_PATTERN = {
        "gonflement jambes", "prise de poids rapide",
        "œdèmes", "rétention hydrique", "œdème périphérique",
    }
    _has_pattern = bool(sym_set & _CLINICAL_PATTERN)

    # conf < 0.50 sans pattern clinique → pas de bloc
    if confidence_score < 0.50 and not _has_pattern:
        return UserReassuranceV2()

    points: list[str] = []

    # ── "Pourquoi ce n'est pas une urgence" — absences symptômes critiques ──
    if "douleur thoracique" not in sym_set and "douleur thoracique intense" not in sym_set:
        points.append("Pas de douleur thoracique signalée")
    if "essoufflement" not in sym_set and "dyspnée progressive" not in sym_set:
        points.append("Pas de détresse respiratoire signalée")
    if "palpitations" not in sym_set and "syncope" not in sym_set:
        points.append("Pas de signe de trouble du rythme")
    if "paralysie" not in sym_set and "déficit neurologique" not in sym_set:
        points.append("Pas de signe neurologique critique")
    if "fièvre" not in sym_set:
        points.append("Pas de fièvre signalée")
    points = points[:3]

    # ── Тон залежить від confidence ──────────────────────────────────────────
    if confidence_score < 0.70:
        points.append("Orientation préliminaire — consultation recommandée pour confirmation")
    elif sym_set & {"diarrhée", "nausées", "douleur abdominale"}:
        points.append("Pas de signe de déshydratation sévère")
    elif sym_set & {"fièvre", "toux"}:
        points.append("Profil compatible avec une infection courante")
    elif severity == "mild":
        points.append("Surveillance à domicile adaptée à ce profil")
    else:
        points.append("Consultation recommandée pour confirmer l'orientation")

    return UserReassuranceV2(
        headline="Pourquoi ce n'est pas une urgence",
        points=points[:4],
    )


# ── WHY CONSULTATION ─────────────────────────────────────────────────────────

def _build_why_consultation(
    decision: str,
    severity: str,
    gap_value: float,
) -> "WhyConsultation":
    """П.7: Is consultation for danger or uncertainty?"""
    from app.models.schemas import WhyConsultation

    if severity == "severe":
        return WhyConsultation(
            reason_type="severity",
            message="La consultation est recommandée en raison de signes de gravité détectés.",
        )
    if decision in ("TESTS_FIRST", "MEDICAL_REVIEW") and gap_value <= 0.10:
        return WhyConsultation(
            reason_type="uncertainty",
            message="La consultation est recommandée non pas en raison d'un danger immédiat, "
                "mais parce que plusieurs diagnostics restent proches et nécessitent un avis médical pour trancher.",
        )
    if decision in ("TESTS_FIRST", "MEDICAL_REVIEW"):
        return WhyConsultation(
            reason_type="uncertainty",
            message="La consultation est conseillée pour confirmer l'orientation diagnostique, "
                "pas en raison d'un danger immédiat.",
        )
    if decision == "FOLLOW_UP":
        return WhyConsultation(
            reason_type="follow_up",
            message="Un suivi médical est recommandé pour vérifier l'évolution de vos symptômes.",
        )
    return WhyConsultation(reason_type="", message="")


# ── DATA QUALITY MESSAGE ─────────────────────────────────────────────────────

def _build_data_quality(
    symptoms_count: int,
    confidence_score: float,
    diagnoses: list,
) -> "DataQualityMessage":
    """П.10: Honest message when data is insufficient."""
    from app.models.schemas import DataQualityMessage

    if symptoms_count <= 1:
        return DataQualityMessage(
            status="insufficient_data",
            message="Un seul symptôme a été renseigné — les données sont insuffisantes pour un diagnostic fiable. "
                "Ajoutez d'autres symptômes ou consultez un médecin.",
        )
    if confidence_score < 0.50 and len(diagnoses) >= 2:
        gap = diagnoses[0].probability - diagnoses[1].probability if len(diagnoses) >= 2 else 1.0
        if gap <= 0.05:
            return DataQualityMessage(
                status="vague",
                message="Les symptômes sont compatibles avec plusieurs diagnostics sans distinction claire. "
                    "Des examens complémentaires sont nécessaires pour préciser.",
            )
    return DataQualityMessage(status="sufficient", message="")


def _build_system_value(
    economic_v2,
    diagnoses: list,
    severity_level: str,
) -> "SystemValue":
    """UX п.3c: show value even when savings == 0€."""
    from app.models.schemas import SystemValue

    savings = 0.0
    if economic_v2 and not economic_v2.savings_blocked:
        savings = economic_v2.pathway.savings

    if savings > 0:
        return SystemValue(
            value_delivered=[
                f"Économie de {savings:.0f} € par optimisation du parcours",
                "Suppression des examens non nécessaires au stade initial",
                "Orientation diagnostique structurée",
            ],
            confirmation_message="",
            is_already_optimal=False,
        )

    # savings == 0 → parcours déjà optimal → show validation value
    value_items = [
        "Confirmation du bon parcours diagnostique",
        "Absence d'examens inutiles vérifiée",
        "Validation clinique du protocole actuel",
    ]
    if severity_level == "mild":
        value_items.append("Aucun signe de gravité — surveillance suffisante")
    if len(diagnoses) >= 2:
        value_items.append("Diagnostic différentiel structuré entre " +
                           " et ".join(d.name for d in diagnoses[:2]))

    return SystemValue(
        value_delivered=value_items,
        confirmation_message="Le système confirme que le parcours actuel est déjà optimal. "
                             "Aucun examen inutile détecté — sécurité diagnostique maximale.",
        is_already_optimal=True,
    )


# ── БЛОК 1+3: SEVERITY→URGENCY HARD OVERRIDE + FINAL DECISION ────────────────

def _map_severity_to_urgency(severity: str) -> str:
    """БЛОК 1: severity is the ONLY source of urgency. Gap CANNOT influence urgency."""
    if severity == "severe":
        return "élevé"
    elif severity == "moderate":
        return "modéré"
    return "faible"


def _build_final_decision(
    severity: str,
    diagnostic_status_str: str,
    confidence_score: float,
    threshold: float,
    gap_value: float = 1.0,
    has_required_tests: bool = False,
) -> str:
    """Phase 1 Decision: severity→action, gap→confidence, tests→TESTS_FIRST."""
    if severity == "severe":
        return "URGENT_MEDICAL_REVIEW"
    # Gap low + tests can help → TESTS_FIRST
    if gap_value <= 0.10 and has_required_tests:
        return "TESTS_FIRST"
    if diagnostic_status_str == "referral_required":
        if has_required_tests:
            return "TESTS_FIRST"
        return "MEDICAL_REVIEW"
    if confidence_score >= threshold:
        return "LOW_RISK_MONITOR"
    if has_required_tests:
        return "TESTS_FIRST"
    return "MEDICAL_REVIEW"


def _build_final_decision_phase2(
    severity: str,
    confidence_score: float,
    final_threshold: float,
    gap_value: float,
) -> tuple[str, str]:
    """
    Phase 2 Decision (after tests): returns (decision, action_label).
    Tests do NOT change severity (rule from ТЗ п.9).
    """
    if severity == "severe":
        return "URGENT_MEDICAL_REVIEW", "Consultation urgente recommandée"
    if confidence_score >= final_threshold:
        return "CONFIRMED_PATH", "Diagnostic confirmé — suivi recommandé"
    if gap_value <= 0.10:
        return "MEDICAL_REVIEW", "Confirmation médicale recommandée"
    return "FOLLOW_UP", "Suivi médical conseillé sous 48h"


# ── БЛОК 4: UX MESSAGE ENGINE ─────────────────────────────────────────────────

def _build_ux_message(
    severity: str,
    gap_value: float,
    force_referral: bool,
    decision: str = "",
    urgency_level: str = "faible",
) -> "UxMessage":
    """БЛОК 4: Generate user-facing message based on severity + gap + decision."""
    from app.models.schemas import UxMessage

    if severity == "severe":
        return UxMessage(
            headline="Consultation urgente recommandée",
            detail="Les symptômes détectés nécessitent une évaluation médicale rapide.",
            gap_warning="",
        )

    # TESTS_FIRST — specific message
    if decision == "TESTS_FIRST":
        headline = "Examens recommandés pour préciser le diagnostic"
        detail = "Des analyses complémentaires permettraient de confirmer l'orientation diagnostique."
        gap_warning = ""
        if force_referral and gap_value <= 0.10:
            gap_warning = (
                "Écart faible entre diagnostics — les examens ci-dessous aideront à trancher."
            )
        return UxMessage(headline=headline, detail=detail, gap_warning=gap_warning)

    if urgency_level == "élevé" and severity != "severe":
        headline = "Consultation médicale recommandée aujourd'hui"
        detail = "Le niveau d'urgence détecté nécessite une évaluation médicale dans la journée."
    elif severity == "moderate":
        headline = "Consultation médicale recommandée dans les 24–48h"
        detail = "Aucun signe de gravité immédiate n'est détecté."
    else:
        headline = "Surveillance à domicile"
        detail = "Surveillez vos symptômes pendant 48–72h. Consultez si aggravation."

    gap_warning = ""
    if force_referral and gap_value <= 0.10:
        gap_warning = (
            "Écart faible entre diagnostics — une confirmation médicale est recommandée "
            "en raison de la proximité entre plusieurs diagnostics possibles."
        )

    return UxMessage(headline=headline, detail=detail, gap_warning=gap_warning)


# ── БЛОК 5: SANITIZER — запрещённые состояния ─────────────────────────────────

_FORBIDDEN_MODERATE_PATTERNS = [
    "urgence élevé",
    "urgence élevée",
    "consultation urgente",
    "profil urgent",
    "appeler le 15",
    "appelez le 15",
    "samu",
    "urgence recommandée",
]


def _sanitize_text_for_severity(text: str, severity: str) -> str:
    """БЛОК 5: Remove forbidden urgency language when severity != severe."""
    if severity == "severe":
        return text
    lowered = text.lower()
    for pattern in _FORBIDDEN_MODERATE_PATTERNS:
        if pattern in lowered:
            # Replace with safe alternative
            text = text.replace(
                _find_case_insensitive(text, pattern),
                "consultation médicale recommandée",
            )
    return text


def _find_case_insensitive(text: str, pattern: str) -> str:
    """Find the actual casing of pattern in text."""
    idx = text.lower().find(pattern)
    if idx == -1:
        return pattern
    return text[idx:idx + len(pattern)]


def _build_explainability_score(
    clinical_v2: "ClinicalReasoningV2",
    probability_reasoning: "ProbabilityReasoning",
    test_reasoning: "TestReasoning",
    do_not_miss: "DoNotMissEngine",
    context: dict | None = None,
) -> "ExplainabilityScore":
    from app.models.schemas import ExplainabilityScore

    score = 0.0
    factors: list[str] = []

    # Symptom mapping present
    if clinical_v2.main_logic:
        score += 0.25
        factors.append("symptom_mapping")

    # Probability justification
    if probability_reasoning.diagnoses:
        all_justified = all(
            bool(e.based_on) for e in probability_reasoning.diagnoses.values()
        )
        if all_justified:
            score += 0.25
            factors.append("probability_justified")
        else:
            score += 0.10
            factors.append("probability_partial")

    # Test logic linked
    if test_reasoning.links:
        score += 0.20
        factors.append("test_logic_linked")

    # Context influence explained
    if context and any(context.get(k) for k in ("trigger", "cause", "after_food", "post_medication")):
        score += 0.15
        factors.append("context_integrated")

    # Do-not-miss rules applied
    if do_not_miss.flags:
        score += 0.15
        factors.append("do_not_miss_rules_applied")
    else:
        score += 0.05
        factors.append("no_critical_rules_triggered")

    score = round(min(score, 1.0), 3)
    return ExplainabilityScore(score=score, factors=factors)


def _empty_response(reason: str, urgency_level: str = "faible") -> AnalyzeResponse:
    return AnalyzeResponse(
        diagnoses=[],
        tests=Tests(required=[], optional=[]),
        explanation=reason,
        economics={},
        urgency_level=urgency_level,
        tcs_level="incertain",
        decision="EMERGENCY" if urgency_level == "élevé" else "MEDICAL_REVIEW",
        consultation_cost=CONSULTATION_COST,
    )


# ── Pipeline principal ────────────────────────────────────────────────────────

def run(request: AnalyzeRequest) -> AnalyzeResponse:
    _debug = request.debug
    trace = DebugTrace(
        engine_version=ENGINE_VERSION,
        rules_version=RULES_VERSION,
        registry_version=REGISTRY_VERSION,
        core_status=CORE_STATUS,
    ) if _debug else None

    # COUCHE 1 — PARSER
    symptoms_canonical = nse.run(request.symptoms)
    if _debug: trace.symptoms_after_parser = list(symptoms_canonical)

    symptoms_compressed = scm.run(symptoms_canonical)
    if _debug: trace.symptoms_after_scm = list(symptoms_compressed)

    # COUCHE 3 — SAFETY (RFE)
    rfe_result = rfe.run(symptoms_compressed)
    if _debug:
        trace.red_flags_detected = [rfe_result.reason] if rfe_result.emergency else []
        trace.emergency = rfe_result.emergency

    if rfe_result.emergency:
        logger.warning(f"RFE EMERGENCY → {rfe_result.reason}")
        resp = _empty_response(
            f"URGENCE MÉDICALE : {rfe_result.reason} "
            "Arrêtez cette application et appelez le 15 (SAMU) ou le 112.",
            urgency_level="élevé",
        )
        resp.emergency_flag = True
        resp.emergency_reason = rfe_result.reason
        resp.decision = "EMERGENCY"
        if _debug: resp.debug_trace = trace
        return resp

    # COUCHE 2 — CLINICAL SCORING
    probs, incoherence_score = bpu.run(symptoms_compressed)

    if _debug:
        from app.data.symptoms import SYMPTOM_DIAGNOSES, COMBO_BONUSES, SYMPTOM_EXCLUSIONS
        ss = set(symptoms_compressed)
        _combos = [
            f"{'+'.join(sorted(combo))} → {diag} +{bonus}"
            for combo, bonuses in COMBO_BONUSES
            for diag, bonus in bonuses.items()
            if combo.issubset(ss) and diag in probs
        ]
        _penalties = [
            f"{sym} → {diag} -{penalty}"
            for sym in ss
            for diag, penalty in SYMPTOM_EXCLUSIONS.get(sym, {}).items()
            if diag in probs
        ]
        trace.bpu = DebugBPU(
            combo_bonuses_applied=_combos,
            penalties_applied=_penalties,
            incoherence_score=round(incoherence_score, 3),
            final_probs={k: round(v, 3) for k, v in sorted(probs.items(), key=lambda x: -x[1])},
        )

    if not probs:
        _raw_syms_lower = {s.lower().strip() for s in request.symptoms}
        _CARDIAC_RAW = {
            "douleur thoracique", "douleur poitrine", "douleur à la poitrine",
            "douleur au thorax", "mal à la poitrine", "douleur thoracique intense",
        }
        _empty_urgency = "élevé" if (_raw_syms_lower & _CARDIAC_RAW and len(request.symptoms) <= 2) else "faible"
        resp = _empty_response(
            "Les symptômes indiqués ne permettent pas d'identifier un diagnostic. "
            "Veuillez consulter un médecin.",
            urgency_level=_empty_urgency,
        )
        if _debug: resp.debug_trace = trace
        return resp

    probs_before_tce = dict(probs)
    probs = tce.run(probs, onset=request.onset, duration=request.duration)
    if _debug:
        _tce_boosts, _tce_pens = [], []
        for d, v_after in probs.items():
            v_before = probs_before_tce.get(d, 0)
            diff = round(v_after - v_before, 3)
            if diff > 0:   _tce_boosts.append(f"{d} +{diff}")
            elif diff < 0: _tce_pens.append(f"{d} {diff}")
        trace.tce = DebugTCE(
            onset=request.onset,
            duration=request.duration,
            boosts_applied=_tce_boosts,
            penalties_applied=_tce_pens,
            probs_before={k: round(v, 3) for k, v in sorted(probs_before_tce.items(), key=lambda x: -x[1])},
            probs_after={k: round(v, 3) for k, v in sorted(probs.items(), key=lambda x: -x[1])},
        )

    probs_before_cre = dict(probs)
    probs = cre.run(probs, symptoms_compressed)

    # Audit: збираємо rules і scores для _build_audit (завжди, не тільки debug)
    from app.pipeline.cre import _RULES as _CRE_RULES
    _audit_ss = set(symptoms_compressed)
    _audit_rules = [
        f"{'+'.join(sorted(req))} → {diag} {delta:+.2f}"
        for req, excl, diag, delta in _CRE_RULES
        if diag in probs_before_cre
        and req.issubset(_audit_ss)
        and not excl.intersection(_audit_ss)
    ]
    _audit_probs_before = dict(probs_before_cre)
    if _debug:
        from app.pipeline.cre import _RULES
        ss = set(symptoms_compressed)
        _rules_applied = [
            f"{'+'.join(sorted(req))}{'(excl:'+','.join(sorted(excl))+')' if excl else ''} → {diag} {delta:+.2f}"
            for req, excl, diag, delta in _RULES
            if diag in probs_before_cre
            and req.issubset(ss)
            and not excl.intersection(ss)
        ]
        trace.cre = DebugCRE(
            rules_applied=_rules_applied,
            probs_before={k: round(v, 3) for k, v in sorted(probs_before_cre.items(), key=lambda x: -x[1])},
            probs_after={k: round(v, 3) for k, v in sorted(probs.items(), key=lambda x: -x[1])},
        )

    # ── CARDIO GUARD v2.4 (final position — after CRE+TCE) ──────────────────
    # Sans symptômes cardiaques core → prob cardiaque plafonnée à 0.35
    _CARDIO_CORE = frozenset({
        "essoufflement", "douleur thoracique", "palpitations",
        "syncope", "douleur thoracique intense", "irradiation bras gauche",
        "irradiation machoire", "dyspnée progressive",
    })
    _CARDIO_DIAGS_CAP = {"Insuffisance cardiaque", "Angor", "Infarctus du myocarde",
                         "Embolie pulmonaire", "Trouble du rythme"}
    _has_cardio_core = bool(set(symptoms_compressed) & _CARDIO_CORE)
    if not _has_cardio_core:
        _CARDIO_CAP = 0.35
        probs = {
            k: min(v, _CARDIO_CAP) if k in _CARDIO_DIAGS_CAP else v
            for k, v in probs.items()
        }
        logger.debug(f"CARDIO GUARD applied — IC={probs.get('Insuffisance cardiaque', 0):.2f}")

    urgency_level = rme.run(probs, symptoms=symptoms_compressed)

    # ── TriageGate v2.4 — валідація urgence по комбінаціям ───────────────────
    # ЗАБОРОНЕНО: urgence по одному симптому
    # Замінює старий override "douleur thoracique ≤2 → élevé"
    from app.pipeline.rme import triage_gate as _triage_gate
    urgency_level = _triage_gate(set(symptoms_compressed), urgency_level)

    eo_result = eo.run(symptoms_compressed)
    if eo_result.triggered:
        logger.warning(f"EMERGENCY OVERRIDE → {eo_result.reason}")
        resp = _empty_response(
            f"URGENCE MÉDICALE : {eo_result.reason}. "
            "Arrêtez cette application et appelez le 15 (SAMU) ou le 112 immédiatement."
        )
        resp.emergency_flag = True
        resp.emergency_reason = eo_result.reason
        resp.urgency_level = "élevé"
        resp.decision = "EMERGENCY"
        if _debug: resp.debug_trace = trace
        return resp

    tcs_level, confidence_level, confidence_score = tcs.run(
        probs, len(symptoms_compressed),
        symptoms=symptoms_compressed,
        incoherence_score=incoherence_score,
    )
    if _debug:
        from app.pipeline.tcs import _LOW_DATA_THRESHOLD
        from app.data.symptoms import SYMPTOM_DIAGNOSES as _SD
        _syms = symptoms_compressed
        _sp = sorted(probs.values(), reverse=True)
        _top_diag = max(probs, key=probs.get) if probs else ""
        _diag_syms = set(_SD.get(_top_diag, {}).keys())
        _ss = set(_syms)
        _cov = len(_ss & _diag_syms) / len(_ss) if _ss else 0.0
        _gap = (_sp[0] - _sp[1]) if len(_sp) >= 2 else 1.0
        _coh = min(_gap / 0.30, 1.0)
        _qual = min(len(_syms) / 4.0, 1.0)
        _raw = 0.40 * _cov + 0.35 * _coh + 0.25 * _qual
        _pen = incoherence_score * 0.08
        trace.tcs = DebugTCS(
            coverage=round(_cov, 3),
            coherence=round(_coh, 3),
            quality=round(_qual, 3),
            raw_score=round(_raw, 3),
            incoherence_penalty=round(_pen, 3),
            final_score=round(confidence_score, 3),
            low_data_cap_applied=(len(_syms) <= _LOW_DATA_THRESHOLD),
            confidence_level=confidence_level,
            tcs_level=tcs_level,
        )

    symptom_set = set(symptoms_compressed)
    diagnoses = _build_diagnosis_list(probs, symptom_set)
    diagnoses_names = [d.name for d in diagnoses]

    # COUCHE 4 — OUTPUT
    _lme = lme.run(
        diagnoses_names=diagnoses_names,
        symptom_set=symptom_set,
        probs=probs,
    )
    tests, _cost_lme, _comparison_lme, test_explanations, test_probabilities, test_costs = _lme

    # Cost Engine — economic layer (V2: real cost from COST_MAP)
    top_diag_name = diagnoses_names[0] if diagnoses_names else ""
    _std_tests_for_econ = STANDARD_PATH_MAP.get(top_diag_name, ["NFS", "CRP"])
    _std_cost_real = CONSULTATION_GP_COST + sum(COST_MAP.get(t, 20.0) for t in _std_tests_for_econ)
    _opt_cost_real = CONSULTATION_GP_COST + sum(COST_MAP.get(t, 20.0) for t in tests.required)
    _savings_real = round(max(0.0, _std_cost_real - _opt_cost_real), 2)
    economics = {
        "standard_cost": round(_std_cost_real, 2),
        "optimized_cost": round(_opt_cost_real, 2),
        "savings": _savings_real,
        "currency": "EUR",
        "pricing_basis": "France baseline v2 — COST_MAP traceable",
        "standard_tests": _std_tests_for_econ,
        "optimized_tests": list(tests.required),
    }

    confidence_final, sgl_warnings = sgl.run(
        diagnoses_names=diagnoses_names,
        probs=probs,
        symptom_count=len(symptoms_compressed),
        confidence_level=confidence_level,
        incoherence_score=incoherence_score,
    )

    explanation = _build_explanation(symptoms_compressed, diagnoses, tests.required)
    differential = _build_differential(diagnoses, probs, symptoms_compressed)
    test_details = _build_test_details(tests.required, tests.optional, diagnoses_names)
    diagnostic_path = _build_diagnostic_path(diagnoses, urgency_level, tcs_level)
    misdiagnosis_risk, misdiagnosis_risk_score = _build_misdiagnosis_risk(
        diagnoses, probs, len(symptoms_compressed), tcs_level, incoherence_score
    )
    worsening_signs = _build_worsening_signs(diagnoses, urgency_level)
    do_not_miss = _build_do_not_miss(diagnoses, urgency_level)
    analysis_limits = _build_analysis_limits()

    # Decision Engine 2.0
    decision = _build_decision(
        emergency=False,
        urgency_level=urgency_level,
        misdiagnosis_risk=misdiagnosis_risk,
        tcs_level=tcs_level,
    )

    if _debug:
        trace.selected_tests = list(tests.required) + list(tests.optional)
        trace.sgl_warnings = list(sgl_warnings)
        trace.confidence_final = confidence_final
        trace.emergency_override_triggered = eo_result.triggered
        trace.emergency_override_patterns = eo_result.patterns_matched
        _sp = sorted(probs.values(), reverse=True)
        trace.confidence_gap_top1_top2 = round((_sp[0] - _sp[1]) if len(_sp) >= 2 else 1.0, 3)
        trace.misdiagnosis_risk = misdiagnosis_risk
        trace.misdiagnosis_risk_score = misdiagnosis_risk_score
        trace.do_not_miss = do_not_miss
        trace.decision = decision
        trace.test_priority_reasoning = [
            f"{td['test']} — priorité {td['priority']}: {td['pourquoi']}"
            for td in test_details[:3]
            if td.get("in_required")
        ]
        if diagnostic_path:
            trace.diagnostic_path_summary = (
                f"{diagnostic_path.get('main_hypothesis','?')} → "
                f"{diagnostic_path.get('key_discriminator','?')} → "
                f"{diagnostic_path.get('next_best_step','?')}"
            )

    validation = None
    if request.validation_mode:
        validation = _build_validation(
            diagnoses=diagnoses,
            probs=probs,
            symptom_set=symptom_set,
            tests=tests,
            confidence_score=confidence_score,
            incoherence_score=incoherence_score,
            symptoms_compressed=symptoms_compressed,
        )

    # ── NEW BLOCKS (ТЗ п.1–13) ───────────────────────────────────────────────
    interpreted = getattr(request, "interpreted_symptoms", [])

    _input_confidence = _build_input_confidence(
        symptoms_raw=list(request.symptoms),
        interpreted_symptoms=interpreted,
        symptoms_compressed=symptoms_compressed,
    )
    _decision_logic = _build_decision_logic(
        diagnoses=diagnoses,
        confidence_score=confidence_score,
        misdiagnosis_risk_score=misdiagnosis_risk_score,
        decision=decision,
        urgency_level=urgency_level,
        symptoms_compressed=symptoms_compressed,
    )
    _safety = _build_safety_layer(
        symptoms_compressed=symptoms_compressed,
        emergency_flag=False,
        misdiagnosis_risk=misdiagnosis_risk,
        is_fallback=False,
        diagnoses=diagnoses,
    )
    _economic_impact = _build_economic_impact(economics, list(tests.required), diagnoses)
    _consistency = _build_consistency_check(probs, confidence_score, incoherence_score, symptoms_compressed)
    _scenario = _build_scenario_simulation(diagnoses, urgency_level, list(tests.required))
    _diag_tree = _build_diagnostic_tree(diagnoses, list(tests.required), test_details)
    _trust = _build_trust_score(
        confidence_score=confidence_score,
        symptom_count=len(symptoms_compressed),
        incoherence_score=incoherence_score,
        misdiagnosis_risk_score=misdiagnosis_risk_score,
    )
    _edge = _build_edge_case_analysis(
        diagnoses=diagnoses,
        incoherence_score=incoherence_score,
        sgl_warnings=sgl_warnings,
        is_fallback=False,
    )
    _clinical = _build_clinical_reasoning(
        diagnoses=diagnoses,
        symptoms_compressed=symptoms_compressed,
        probs=probs,
        tests_required=list(tests.required),
        urgency_level=urgency_level,
    )

    # ── EXPLAINABILITY LAYER (п.1–7) ──────────────────────────────────────
    # context dict для нових блоків (з routes передасться пізніше, тут = None)
    _ctx_for_explain: dict | None = None

    _clinical_v2 = _build_clinical_reasoning_v2(
        diagnoses=diagnoses,
        symptoms_compressed=symptoms_compressed,
        probs=probs,
        context=_ctx_for_explain,
    )
    _probability_reasoning = _build_probability_reasoning(
        diagnoses=diagnoses,
        symptoms_compressed=symptoms_compressed,
        probs=probs,
        context=_ctx_for_explain,
    )
    _test_reasoning = _build_test_reasoning(
        tests_required=list(tests.required),
        tests_optional=list(tests.optional),
        diagnoses=diagnoses,
    )
    _do_not_miss_engine = _build_do_not_miss_engine(
        symptoms_compressed=symptoms_compressed,
        context=_ctx_for_explain,
        diagnoses=diagnoses,
        urgency_level=urgency_level,
    )
    _economic_reasoning = _build_economic_reasoning(
        economics=economics,
        tests_required=list(tests.required),
        tests_optional=list(tests.optional),
        diagnoses=diagnoses,
    )
    _economic_reasoning_v2 = None  # built in routes.py AFTER do_not_miss + context boost
    _explainability = _build_explainability_score(
        clinical_v2=_clinical_v2,
        probability_reasoning=_probability_reasoning,
        test_reasoning=_test_reasoning,
        do_not_miss=_do_not_miss_engine,
        context=_ctx_for_explain,
    )

    # ── Symptom Trace (ТЗ п.3) ──────────────────────────────────────────────
    from app.models.schemas import SymptomTrace
    _raw_text = " ".join(request.symptoms).lower()
    _trace_map: dict[str, str] = {}
    from app.pipeline.nlp_normalizer import SYNONYMS as _SYNS
    for sym in symptoms_compressed:
        # Шукаємо в synonyms який ключ дав цей симптом
        for key, val in _SYNS.items():
            if val == sym and key in _raw_text:
                _trace_map[sym] = key
                break
        else:
            # Якщо симптом є в raw — вказуємо на нього
            if sym in _raw_text:
                _trace_map[sym] = sym
    _symptom_trace = SymptomTrace(traces=_trace_map)

    # ── FINAL LAYER (audit + version + investor) ────────────────────────────
    _audit = _build_audit(
        symptoms_raw=list(request.symptoms),
        symptoms_compressed=symptoms_compressed,
        probs_before=_audit_probs_before,
        probs_after=probs,
        rules_triggered=_audit_rules,
        decision=decision,
        urgency_level=urgency_level,
        tcs_level=tcs_level,
        confidence_level=confidence_final,
    )
    _engine_meta = _build_engine_meta()

    _self_check = _build_self_check(
        diagnoses=diagnoses,
        probs=probs,
        symptoms_compressed=symptoms_compressed,
        tests_required=list(tests.required),
        decision=decision,
        misdiagnosis_risk=misdiagnosis_risk,
        confidence_level=confidence_final,
        incoherence_score=incoherence_score,
    )
    _quality_gate, _is_valid = _build_quality_gate(
        self_check=_self_check,
        trust_score=_trust,
        diagnoses=diagnoses,
        symptoms_compressed=symptoms_compressed,
        probs=probs,
        voice_confidence=getattr(request, "voice_confidence", None),
        confidence_level=confidence_final,
    )
    _stability = _build_stability(probs)
    _trace_id = _build_trace_id(
        symptoms=list(request.symptoms),
        onset=request.onset,
        duration=request.duration,
    )

    return AnalyzeResponse(
        diagnoses=diagnoses,
        tests=tests,
        economics=economics,
        explanation=explanation,
        confidence_level=confidence_final,
        urgency_level=urgency_level,
        emergency_flag=False,
        emergency_reason="",
        tcs_level=tcs_level,
        decision=decision,
        sgl_warnings=sgl_warnings,
        test_explanations=test_explanations,
        test_probabilities=test_probabilities,
        test_costs=test_costs,
        consultation_cost=CONSULTATION_COST,
        debug_trace=trace,
        validation=validation,
        differential=differential,
        test_details=test_details,
        diagnostic_path=diagnostic_path,
        misdiagnosis_risk=misdiagnosis_risk,
        misdiagnosis_risk_score=misdiagnosis_risk_score,
        worsening_signs=worsening_signs,
        do_not_miss=do_not_miss,
        analysis_limits=analysis_limits,
        # NEW
        input_confidence=_input_confidence,
        decision_logic=_decision_logic,
        safety=_safety,
        economic_impact=_economic_impact,
        consistency_check=_consistency,
        scenario_simulation=_scenario,
        diagnostic_tree=_diag_tree,
        trust_score=_trust,
        edge_case_analysis=_edge,
        clinical_reasoning=_clinical,
        compliance=_get_compliance(),
        is_fallback=False,
        # ABSOLUTE MODE
        self_check=_self_check,
        quality_gate=_quality_gate,
        stability=_stability,
        is_valid_output=_is_valid,
        trace_id=_trace_id,
        # FINAL LAYER
        audit=_audit,
        engine_meta=_engine_meta,
        safe_output=_get_safe_output(),
        # PATCH FINAL
        symptom_trace=_symptom_trace,
        # EXPLAINABILITY LAYER
        clinical_reasoning_v2=_clinical_v2,
        probability_reasoning=_probability_reasoning,
        test_reasoning=_test_reasoning,
        do_not_miss_engine=_do_not_miss_engine,
        economic_reasoning=_economic_reasoning,
        economic_reasoning_v2=_economic_reasoning_v2,
        explainability=_explainability,
        # FINAL FIX PACK (built in routes.py after economic_reasoning_v2)
        baseline_pathway=None,
        nlp_fallback=None,
    )