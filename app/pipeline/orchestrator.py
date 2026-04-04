# ── Pipeline orchestrator — CORE v2.3 ────────────────────────────────────────
# CORE_STATUS: LOCKED — не змінювати без повного regression suite

import logging

from app.pipeline import nse, scm, rfe, bpu, rme, tce, cre, tcs, lme, sgl
from app.pipeline import emergency_override as eo
from app.data.symptoms import DIAG_ARTICLE, URGENT_DIAGNOSES
from app.data.tests import TEST_EXPLANATIONS, CONSULTATION_COST
from app.models.schemas import (
    AnalyzeRequest, AnalyzeResponse, Diagnosis, Tests, Cost, Comparison,
    DebugTrace, DebugBPU, DebugCRE, DebugTCE, DebugTCS,
    ValidationResponse, ValidationDiagnosis,
)

logger = logging.getLogger("clairdiag.pipeline")

# ── CORE LOCK ─────────────────────────────────────────────────────────────────
ENGINE_VERSION: str = "v2.3"
RULES_VERSION: str = "v1.2"
REGISTRY_VERSION: str = "v1.0"
VALIDATION_BASELINE: str = "H15_G30_F40_S100"
CORE_STATUS: str = "LOCKED"
# ─────────────────────────────────────────────────────────────────────────────

_MAX_PROB: float = 0.90
PROBABILITY_THRESHOLD: float = 0.15


# ── Decision Engine 2.0 ───────────────────────────────────────────────────────

def _build_decision(
    emergency: bool,
    urgency_level: str,
    misdiagnosis_risk: str,
    tcs_level: str,
) -> str:
    """
    Повертає одне з 5 значень decision:
      EMERGENCY | URGENT_MEDICAL_REVIEW | TESTS_REQUIRED |
      MEDICAL_REVIEW | LOW_RISK_MONITOR
    """
    if emergency:
        return "EMERGENCY"
    if urgency_level == "élevé" and misdiagnosis_risk in ("modéré", "élevé"):
        return "URGENT_MEDICAL_REVIEW"
    if tcs_level in ("TCS_2",):
        return "TESTS_REQUIRED"
    if tcs_level in ("TCS_3", "TCS_4"):
        return "MEDICAL_REVIEW"
    return "LOW_RISK_MONITOR"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_diagnosis_list(probs: dict[str, float], symptom_set: set[str]) -> list[Diagnosis]:
    from app.data.symptoms import SYMPTOM_DIAGNOSES

    key_symptoms_map: dict[str, list[str]] = {name: [] for name in probs}
    for sym in symptom_set:
        for diag in SYMPTOM_DIAGNOSES.get(sym, {}):
            if diag in key_symptoms_map and sym not in key_symptoms_map[diag]:
                key_symptoms_map[diag].append(sym)

    _CLINICAL_PRIORITY: dict[str, int] = {
        "Embolie pulmonaire": 11, "Angor": 10, "Pneumonie": 9, "Angine": 7,
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
        next_step = "Consultation urgente ou appel du 15 selon l'évolution"
    elif tcs_level in ("TCS_1", "TCS_2"):
        next_step = "Consultation médicale rapide + examens complémentaires"
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
        "Embolie pulmonaire", "Angor", "Insuffisance cardiaque",
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
        "Gastrite":        ["Ulcère perforé", "Infarctus mésentérique"],
        "RGO":             ["Syndrome coronarien aigu"],
        "Trouble du rythme": ["Fibrillation ventriculaire", "Bloc auriculo-ventriculaire"],
        "Grippe":          ["Pneumonie", "Sepsis"],
        "Angine":          ["Abcès périamygdalien", "Épiglottite"],
        "Rhinopharyngite": ["Sinusite compliquée", "Méningite si raideur nuque"],
        "Insuffisance cardiaque": ["Embolie pulmonaire", "Syndrome coronarien aigu"],
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

    if gap >= 0.25:
        gap_note = f"Hypothèse principale nettement dominante (écart {gap:.0%})."
    elif gap >= 0.10:
        gap_note = f"Deux hypothèses proches (écart {gap:.0%}) — examens nécessaires pour trancher."
    else:
        gap_note = f"Profil ambiguë (écart {gap:.0%}) — diagnostic incertain sans bilan."

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


def _empty_response(reason: str, urgency_level: str = "faible") -> AnalyzeResponse:
    empty_comparison = Comparison(
        standard_tests=[], standard_cost=0,
        optimized_tests=[], optimized_cost=0,
        savings=0, savings_multiplier="—",
    )
    return AnalyzeResponse(
        diagnoses=[],
        tests=Tests(required=[], optional=[]),
        cost=Cost(required=0, optional=0, savings=0),
        explanation=reason,
        comparison=empty_comparison,
        urgency_level=urgency_level,
        tcs_level="incertain",  # backward compat — SF tests expect "incertain" for emergency/empty
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

    urgency_level = rme.run(probs, symptoms=symptoms_compressed)

    _raw_syms = {s.lower().strip() for s in request.symptoms}
    _CARDIAC_RAW = {
        "douleur thoracique", "douleur poitrine", "douleur à la poitrine",
        "douleur au thorax", "mal à la poitrine", "douleur thoracique intense",
    }
    if _raw_syms & _CARDIAC_RAW and len(request.symptoms) <= 2 and urgency_level == "faible":
        urgency_level = "élevé"

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
    tests, cost, comparison, test_explanations, test_probabilities, test_costs = lme.run(
        diagnoses_names=diagnoses_names,
        symptom_set=symptom_set,
        probs=probs,
    )

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

    return AnalyzeResponse(
        diagnoses=diagnoses,
        tests=tests,
        cost=cost,
        explanation=explanation,
        comparison=comparison,
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
    )