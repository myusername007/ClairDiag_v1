"""
ClairDiag v2 — Full Validation Pipeline
1. Maps cases_blind.json → symptoms_normalized
2. Runs v2 engine on all 110 cases
3. Generates cases_blind_mapped.json + clairdiag_outputs.json
"""

import json
import os
import sys
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from medical_probability_engine import run_probability_engine
from test_recommendation_engine import run_recommendation_engine
from context_flags import detect_context_flags
from economic_score_v2 import compute_economic_score

# ──────────────────────────────────────────────
# OUT OF SCOPE
# ──────────────────────────────────────────────

OUT_OF_SCOPE = {
    "ADV-057": "Pédiatrie (3 ans) — hors scope v2",
    "ADV-058": "Crise psychiatrique / idées suicidaires — hors scope v2",
    "ADV-060": "Soins palliatifs — orientation non diagnostique, hors scope v2",
    "BDL-11": "Dissection aortique suspectée — condition absente de conditions_master.json v2. Scanner thoracique urgent requis. Évaluation manuelle obligatoire.",
}

# ──────────────────────────────────────────────
# SYMPTOM MAPPING DICTIONARY
# ──────────────────────────────────────────────

SYMPTOM_MAP = [
    # Cardiaque
    ("douleur thoracique oppressive",       "douleur_thoracique_oppressive"),
    ("douleur thoracique pleurale",         "douleur_thoracique_pleurale"),
    ("douleur thoracique latérale",         "douleur_thoracique_pleurale"),
    ("douleur thoracique constrictive",     "douleur_thoracique_oppressive"),
    ("douleur rétrosternale",               "douleur_thoracique"),
    ("douleur thoracique",                  "douleur_thoracique"),
    ("douleur interscapulaire",             "douleur_thoracique"),
    ("douleur dorsale brutale",             "douleur_thoracique"),
    ("douleur dorsale",                     "douleur_thoracique"),
    ("serrement thoracique",                "douleur_thoracique_oppressive"),
    ("oppression thoracique",               "douleur_thoracique_oppressive"),
    ("barre thoracique",                    "douleur_thoracique_oppressive"),
    ("brûlure centrale thoracique",         "douleur_thoracique"),
    ("brûlure.*thoracique",                 "douleur_thoracique"),
    ("irradiation.*bras",                   "douleur_irradiante_bras"),
    ("irradiation abdominale",              "douleur_epigastrique"),
    ("irradie.*abdomen",                    "douleur_epigastrique"),
    ("sueurs froides",                      "sueur_froide"),
    ("transpiration froide",                "sueur_froide"),
    ("légère sueur",                        "sueur_froide"),
    ("sueur",                               "sueur_froide"),
    ("tachycardie",                         "tachycardie"),
    ("palpitations",                        "palpitations"),
    ("syncope",                             "syncope"),
    ("perte de connaissance",               "syncope"),
    ("s.est évanoui",                       "syncope"),
    ("hypotension",                         "hypotension"),
    ("TA 9[0-9]/",                          "hypotension"),
    ("marbrures",                           "hypotension"),
    ("œdème.*cheville",                     "oedeme_membre_inferieur"),
    ("œdèmes.*chevilles",                   "oedeme_membre_inferieur"),
    ("œdème.*membre",                       "oedeme_membre_inferieur"),
    ("œdèmes",                              "oedeme_membre_inferieur"),
    ("mollet.*douloureux",                  "oedeme_membre_inferieur"),
    ("mollet.*gonfl",                       "oedeme_membre_inferieur"),
    ("mollet.*chaleur",                     "oedeme_membre_inferieur"),
    ("gonflement.*mollet",                  "oedeme_membre_inferieur"),
    # Neurologique
    ("faiblesse.*unilatérale",              "faiblesse_unilaterale"),
    ("faiblesse.*main",                     "faiblesse_unilaterale"),
    ("faiblesse.*bras",                     "faiblesse_unilaterale"),
    ("faiblesse.*côté",                     "faiblesse_unilaterale"),
    ("hémiparésie",                         "faiblesse_unilaterale"),
    ("asymétrie faciale",                   "faiblesse_unilaterale"),
    ("sourire.*bizarre",                    "faiblesse_unilaterale"),
    ("faiblesse bilatérale.*jambes",        "faiblesse_unilaterale"),
    ("jambes.*ne tiennent",                 "faiblesse_unilaterale"),
    ("paresthésies ascendantes",            "faiblesse_unilaterale"),
    ("faiblesse générale",                  "fatigue_intense"),
    ("trouble.*parole",                     "trouble_parole"),
    ("trouble.*élocution",                  "trouble_parole"),
    ("difficulté.*mots",                    "trouble_parole"),
    ("aphasie",                             "trouble_parole"),
    ("bafouill",                            "trouble_parole"),
    ("parle.*lentement",                    "trouble_parole"),
    ("parole.*pâteuse",                     "trouble_parole"),
    ("trouble visuel",                      "trouble_vision_brutal"),
    ("amaurose",                            "trouble_vision_brutal"),
    ("scotome",                             "trouble_vision_brutal"),
    ("photophobie",                         "photophobie"),
    ("phonophobie",                         "phonophobie"),
    ("raideur.*nuque",                      "raideur_nuque"),
    ("raideur nuque",                       "raideur_nuque"),
    ("céphalée.*brutale",                   "cephalee_intense_brutale"),
    ("céphalée.*intense",                   "cephalee_intense"),
    ("céphalée.*sévère",                    "cephalee_intense"),
    ("céphalée.*progressive",               "cephalee_intense"),
    ("céphalée.*maximale",                  "cephalee_intense_brutale"),
    ("intensité maximale",                  "cephalee_intense_brutale"),
    ("céphalée",                            "cephalee_pulsatile"),
    ("engourdissement",                     "engourdissement_membre"),
    ("paresthésies",                        "engourdissement_membre"),
    ("confusion",                           "confusion"),
    ("somnolent",                           "fatigue_intense"),
    ("moins alerte",                        "fatigue_intense"),
    ("instabilité.*marche",                 "instabilite_marche"),
    ("vertige.*rotatoire",                  "vertige_positionnel"),
    ("vertige",                             "vertige_positionnel"),
    ("tête.*tourne",                        "vertige_positionnel"),
    # Respiratoire
    ("dyspnée brutale",                     "dyspnee_brutale"),
    ("essoufflement.*soudain",              "dyspnee_brutale"),
    ("dyspnée.*repos",                      "dyspnee"),
    ("dyspnée d.effort",                    "dyspnee_effort"),
    ("dyspnée.*effort",                     "dyspnee_effort"),
    ("dyspnée progressive",                 "dyspnee_effort"),
    ("dyspnée aggravée",                    "dyspnee_effort"),
    ("dyspnée",                             "dyspnee"),
    ("essoufflement",                       "dyspnee_effort"),
    ("manque.*souffle",                     "dyspnee_effort"),
    ("souffle.*moins",                      "dyspnee_effort"),
    ("sifflement",                          "sifflement_respiratoire"),
    ("toux productive",                     "toux_productive"),
    ("toux sèche",                          "toux_seche"),
    ("toux",                                "toux_seche"),
    ("hémoptysie",                          "hemoptysie"),
    ("hypoxie",                             "dyspnee"),
    ("SpO2.*9[0-8]",                        "dyspnee"),
    ("désaturation",                        "dyspnee"),
    ("orthopnée",                           "orthopnee"),
    ("dort.*oreillers",                     "orthopnee"),
    ("réveil dyspnéique",                   "orthopnee"),
    ("respiration rapide.*profonde",        "dyspnee"),
    # Infectieux/Général
    ("fièvre.*39",                          "fievre_elevee"),
    ("fièvre.*38\\.5",                      "fievre_elevee"),
    ("fièvre.*élevée",                      "fievre_elevee"),
    ("fièvre.*38",                          "fievre_moderee"),
    ("fièvre",                              "fievre_moderee"),
    ("fébricule",                           "fievre_legere"),
    ("température.*35",                     "alteration_etat_general_severe"),
    ("frissons intenses",                   "frissons_intenses"),
    ("frissons",                            "frissons"),
    ("altération.*état général.*sévère",    "alteration_etat_general_severe"),
    ("altération.*état général",            "alteration_etat_general"),
    ("malaise général",                     "malaise_general"),
    ("malaise",                             "malaise_general"),
    ("fatigue intense",                     "fatigue_intense"),
    ("fatigue massive",                     "fatigue_intense"),
    ("fatigue",                             "fatigue"),
    ("myalgies intenses",                   "myalgies_intenses"),
    ("myalgies",                            "myalgies_intenses"),
    ("courbatures",                         "myalgies_intenses"),
    ("pâleur",                              "fatigue_intense"),
    ("perte.*appétit",                      "perte_appetit"),
    ("anorexie",                            "perte_appetit"),
    ("mange moins",                         "perte_appetit"),
    ("mange peu",                           "perte_appetit"),
    ("perte.*poids",                        "perte_appetit"),
    ("amaigrissement",                      "perte_appetit"),
    # Digestif
    ("douleur épigastrique",                "douleur_epigastrique"),
    ("épigastralgie",                       "douleur_epigastrique"),
    ("douleur.*épigastrique",               "douleur_epigastrique"),
    ("douleur.*abdominale.*diffuse",        "douleur_abdominale"),
    ("douleur abdominale",                  "douleur_abdominale"),
    ("douleur.*fosse iliaque droite",       "douleur_fosse_iliaque_droite"),
    ("douleur.*FID",                        "douleur_fosse_iliaque_droite"),
    ("douleur.*hypogastre",                 "douleur_abdominale"),
    ("douleur.*ventre",                     "douleur_abdominale"),
    ("douleur.*abdomin",                    "douleur_abdominale"),
    ("nausées",                             "nausees"),
    ("nausée",                              "nausees"),
    ("vomissements",                        "vomissements"),
    ("vomit",                               "vomissements"),
    ("a vomi",                              "vomissements"),
    ("ballonnements",                       "ballonnements"),
    ("éructation",                          "eructation"),
    ("diarrhée",                            "diarrhee"),
    ("selles liquides",                     "diarrhee"),
    ("constipation",                        "constipation"),
    ("alternance.*transit",                 "alternance_transit"),
    ("alternance diarrhée",                 "alternance_transit"),
    ("inconfort.*épigastrique",             "douleur_epigastrique_legere"),
    ("brûlure.*épigastrique",               "brulure_epigastrique"),
    ("reflux",                              "regurgitation"),
    ("ascite",                              "douleur_abdominale"),
    ("défense abdominale",                  "defense_abdominale"),
    # Neuropsych
    ("anxiété",                             "anxiete_intense"),
    ("angoisse",                            "anxiete_intense"),
    ("panique",                             "anxiete_intense"),
    ("tremblement",                         "tremblement"),
    ("insomnie",                            "fatigue"),
    ("dort mal",                            "fatigue"),
    # ── Patches v2.1 ──
    ("oublie",                              "confusion"),
    ("plus lente",                          "confusion"),
    ("hematome",                            "confusion"),
    ("chute.*fois",                         "fatigue_intense"),
    ("baisse.*appetit",                     "perte_appetit"),
    ("mollet.*droit",                       "oedeme_membre_inferieur"),
    ("mollet.*gauche",                      "oedeme_membre_inferieur"),
    ("gonflement.*modere",                  "oedeme_membre_inferieur"),
    ("sensation.*etouffement",              "anxiete_intense"),
    ("coeur.*monte.*gorge",                 "palpitations"),
    ("boule.*gorge",                        "mal_gorge"),
    ("FC 1[0-9][0-9]",                      "tachycardie"),
    ("tete lourde",                         "cephalee_pulsatile"),
    ("anxieux",                             "anxiete_intense"),
    ("douleur diffuse",                     "douleur_abdominale"),
]

NEGATION_PREFIXES = ("pas de ", "sans ", "absence de ", "aucun ", "aucune ", "ni ", "non ")


def normalize_text(text: str) -> str:
    text = text.lower()
    for a, b in [('é','e'),('è','e'),('ê','e'),('ë','e'),('à','a'),('â','a'),
                 ('î','i'),('ï','i'),('ô','o'),('ù','u'),('û','u'),('ç','c'),
                 ('œ','oe'),('æ','ae')]:
        text = text.replace(a, b)
    return text


def map_symptom(symptom_text: str) -> Optional[str]:
    tl = symptom_text.lower()
    if any(tl.startswith(p) for p in NEGATION_PREFIXES):
        return None
    if " pas de " in tl or " sans " in tl or " pas " in tl[:12]:
        return None
    tn = normalize_text(symptom_text)
    for pattern, key in SYMPTOM_MAP:
        pn = normalize_text(pattern)
        try:
            if re.search(pn, tn):
                return key
        except re.error:
            if pn in tn:
                return key
    return None


def map_case_symptoms(case: dict) -> dict:
    case_id  = case["case_id"]
    symptoms = case.get("symptoms", [])

    if case_id in OUT_OF_SCOPE:
        return {
            "case_id":    case_id,
            "label":      case.get("label", ""),
            "source_text": {
                "symptoms":        symptoms,
                "patient_framing": case.get("patient_framing"),
                "context":         case.get("context", {}),
            },
            "mapping_result": {
                "symptoms_normalized": [],
                "mapping_confidence":  "out_of_scope",
                "unmapped_fragments":  [],
                "out_of_scope":        True,
                "out_of_scope_reason": OUT_OF_SCOPE[case_id],
            },
        }

    mapped, unmapped, seen = [], [], set()
    for sym in symptoms:
        key = map_symptom(sym)
        if key and key not in seen:
            mapped.append(key)
            seen.add(key)
        elif not key:
            unmapped.append(sym)

    total   = len(symptoms)
    n_ok    = len(mapped)
    if total == 0:          confidence = "low"
    elif n_ok == 0:         confidence = "low"
    elif n_ok/total >= 0.7: confidence = "high"
    elif n_ok/total >= 0.4: confidence = "medium"
    else:                   confidence = "low"

    return {
        "case_id":    case_id,
        "label":      case.get("label", ""),
        "source_text": {
            "symptoms":        symptoms,
            "patient_framing": case.get("patient_framing"),
            "context":         case.get("context", {}),
        },
        "mapping_result": {
            "symptoms_normalized": mapped,
            "mapping_confidence":  confidence,
            "unmapped_fragments":  unmapped,
        },
    }


# ──────────────────────────────────────────────
# V2 PIPELINE
# ──────────────────────────────────────────────

def infer_final_action(case: dict, mapped_symptoms: list) -> str:
    """Infer final_action_v1 from context + symptoms."""
    danger_symptoms = {
        "douleur_thoracique_oppressive", "douleur_thoracique", "syncope",
        "faiblesse_unilaterale", "trouble_parole", "dyspnee_brutale",
        "dyspnee", "alteration_etat_general_severe", "hypotension",
        "confusion", "cephalee_intense_brutale", "raideur_nuque",
    }
    urgent_symptoms = {
        "douleur_thoracique_pleurale", "dyspnee_effort", "oedeme_membre_inferieur",
        "tachycardie", "sueur_froide", "fievre_elevee", "frissons_intenses",
        "vomissements", "douleur_fosse_iliaque_droite",
    }
    syms = set(mapped_symptoms)
    if syms & danger_symptoms:
        return "consult_urgent"
    if syms & urgent_symptoms:
        return "consult_doctor"
    return "consult_doctor"


def run_v2_pipeline(symptoms_normalized: list, final_action: str) -> dict:
    v1_input = {
        "symptoms_normalized": symptoms_normalized,
        "red_flags":           [],
        "final_action_v1":     final_action,
    }
    etape1 = run_probability_engine(
        v1_output       = v1_input,
        conditions_path = os.path.join(BASE_DIR, "conditions_master.json"),
        weights_path    = os.path.join(BASE_DIR, "condition_weights.json"),
    )
    return run_recommendation_engine(
        etape1_output     = etape1,
        v1_output         = v1_input,
        conditions_path   = os.path.join(BASE_DIR, "conditions_master.json"),
        tests_path        = os.path.join(BASE_DIR, "tests_master.json"),
        differential_path = os.path.join(BASE_DIR, "differential_rules.json"),
    ), etape1


ORIENTATION_SHORT = {
    "urgent_emergency_workup":           "URGENCE — bilan immédiat requis",
    "urgent_medical_review_with_tests":  "Consultation urgente avec examens",
    "medical_review_with_targeted_tests":"Consultation médicale + examens ciblés",
    "supportive_followup":               "Suivi simple",
    "insufficient_data":                 "Données insuffisantes",
}

DANGER_LEVELS = {"critical", "high"}


URGENCY_SHORT = {
    "urgent_emergency_workup":            "URGENCE IMMÉDIATE",
    "urgent_medical_review_with_tests":   "Consultation urgente",
    "medical_review_with_targeted_tests": "Consultation + examens",
    "supportive_followup":                "Suivi simple",
    "insufficient_data":                  "Données insuffisantes",
}


def _build_physician_summary(
    case_id: str,
    label: str,
    top: str | None,
    secondary: list,
    orient: str,
    tests: list,
    why_top1: list,
    confidence: str,
    mr: dict,
) -> dict:
    """STEP 3 — simplified physician-first view."""
    urgency_short = URGENCY_SHORT.get(orient, orient)
    key_reason    = why_top1[0] if why_top1 else "Orientation basée sur les symptômes"
    test_names    = [t.get("test", "") for t in tests if t.get("test")]

    notes_parts = []
    if confidence == "faible":
        notes_parts.append("Confidence faible — données insuffisantes pour discrimination claire")
    if mr.get("unmapped_fragments"):
        notes_parts.append(f"Symptômes non mappés: {', '.join(mr['unmapped_fragments'][:2])}")
    if secondary:
        notes_parts.append(f"Alternatives à considérer: {', '.join(secondary[:2])}")

    return {
        "case_id":        case_id,
        "label":          label,
        "main_hypothesis": top or "Indéterminé",
        "urgency":         urgency_short,
        "key_reason":      key_reason,
        "tests":           test_names,
        "notes":           " | ".join(notes_parts) if notes_parts else "Orientation claire",
    }


def build_output_case(mapped: dict, result: dict, etape1: dict) -> dict:
    case_id    = mapped["case_id"]
    label      = mapped["label"]
    source     = mapped["source_text"]
    mr         = mapped["mapping_result"]

    # Out of scope
    if mr.get("out_of_scope"):
        _ctx_text = " ".join(source.get("context", {}).get("atcd", []) if isinstance(source.get("context"), dict) else [])
        _ctx = detect_context_flags(_ctx_text)
        return {
            "case_id": case_id,
            "label":   label,
            "scope_status": "out_of_scope",
            "input_summary": {
                "symptoms":         source["symptoms"],
                "patient_framing":  source["patient_framing"],
                "context":          str(source["context"]),
            },
            "clairdiag_output": {
                "top_hypothesis":    None,
                "alternatives":      [],
                "urgency":           "Hors périmètre ClairDiag v2",
                "danger_zone":       [],
                "recommended_tests": [],
                "confidence":        {"level": "faible", "score": 1},
                "reasoning_short":   {"why_top1": [], "why_not_top1": [], "urgency_justification": [mr["out_of_scope_reason"]]},
                "economic_impact":   {"consultation_avoided": False, "consultation_scenario": "urgent_direct", "tests_recommended_cost": 0, "baseline_cost": {"low": 0, "high": 0}, "economic_comparison": {"savings": {"low": 0, "high": 0}}, "confidence": "low"},
                "context_flags":     _ctx["context_flags"],
                "context_alerts":    _ctx["context_alerts"],
                "disclaimer":        "ClairDiag v2 — outil d'aide à la décision uniquement. Ne remplace pas l'avis d'un professionnel de santé.",
            },
            "mapping_confidence": "out_of_scope",
            "out_of_scope": True,
            "out_of_scope_reason": mr["out_of_scope_reason"],
            "physician_readable_summary": {
                "case_id":         case_id,
                "label":           label,
                "main_hypothesis": "Hors périmètre ClairDiag v2",
                "urgency":         "Hors périmètre",
                "key_reason":      mr["out_of_scope_reason"],
                "tests":           [],
                "notes":           "Évaluation manuelle obligatoire",
            },
        }

    top        = result.get("top_hypothesis")
    secondary  = result.get("secondary_hypotheses", [])
    exclude    = result.get("exclude_priority", [])
    confidence = result.get("confidence_level", "faible")
    orient     = result.get("medical_orientation_v2", "")
    sf         = result.get("safety_floor", {})
    tests      = result.get("recommended_tests", [])

    # Load conditions for danger_zone
    try:
        with open(os.path.join(BASE_DIR, "conditions_master.json")) as f:
            conds = json.load(f)["conditions"]
    except Exception:
        conds = {}

    all_pool = list({*(([top] if top else [])), *secondary, *exclude})
    danger_zone = [
        {
            "condition":    c,
            "danger_level": conds.get(c, {}).get("danger_level", "unknown"),
            "label_fr":     conds.get(c, {}).get("label_fr", c),
        }
        for c in all_pool
        if conds.get(c, {}).get("danger_level", "") in DANGER_LEVELS
    ]

    # Reasoning short
    rt_raw = etape1.get("reasoning_summary", [])
    why_top1 = [r for r in rt_raw if "safety floor" not in r and "red flags" not in r][:3]
    if not why_top1 and top:
        why_top1 = [f"symptômes compatibles avec {top}"]

    why_not = []
    if secondary:
        why_not.append(f"alternatives présentes: {', '.join(secondary)}")
    if confidence == "faible":
        why_not.append("score insuffisant pour discrimination claire")
    elif confidence == "modéré":
        why_not.append("différentiel possible — examens recommandés")
    if not why_not:
        why_not.append("hypothèse principale bien discriminée")

    urgency_just = [ORIENTATION_SHORT.get(orient, orient)]
    sf_changes = sf.get("changes", []) if isinstance(sf, dict) else []
    if sf.get("triggered"):
        urgency_just.append("safety floor activé")
    urgency_just.extend(sf_changes)

    # Economic — uses compute_economic_score (TASK #011)
    economic_impact = compute_economic_score(
        recommended_tests   = tests,
        orientation         = orient,
        top_hypothesis      = top,
        clinical_confidence = confidence,
        clinical_group      = result.get("clinical_group", "general"),
    )

    conf_score = {"faible":1,"modéré":2,"élevé":3}.get(confidence,1)

    return {
        "case_id": case_id,
        "label":   label,
        "input_summary": {
            "symptoms":        source["symptoms"],
            "patient_framing": source.get("patient_framing"),
            "context":         str(source.get("context", {})),
        },
        "mapping_confidence": mr["mapping_confidence"],
        "clairdiag_output": {
            "top_hypothesis":  top,
            "alternatives":    secondary,
            "urgency":         ORIENTATION_SHORT.get(orient, orient),
            "danger_zone":     danger_zone,
            "recommended_tests": [
                {"test": t.get("test"), "label_fr": t.get("label_fr",""), "priority": t.get("priority","")}
                for t in tests
            ],
            "confidence": {
                "level": confidence,
                "score": conf_score,
            },
            "reasoning_short": {
                "why_top1":             why_top1,
                "why_not_top1":         why_not,
                "urgency_justification":urgency_just,
            },
            "economic_impact": economic_impact,
            "disclaimer": (
                "ClairDiag v2 — outil d'aide à la décision uniquement. "
                "Ne remplace pas l'avis d'un professionnel de santé."
            ),
            "context_flags":  [],
            "context_alerts": [],
        },
        "scope_status": "in_scope",
        "physician_readable_summary": _build_physician_summary(
            case_id   = case_id,
            label     = label,
            top       = top,
            secondary = secondary,
            orient    = orient,
            tests     = tests,
            why_top1  = why_top1,
            confidence= confidence,
            mr        = mr,
        ),
    }


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    input_path   = os.path.join(BASE_DIR, "cases_blind.json")
    mapped_path  = os.path.join(BASE_DIR, "cases_blind_mapped.json")
    outputs_path = os.path.join(BASE_DIR, "clairdiag_outputs.json")

    with open(input_path, "r", encoding="utf-8") as f:
        blind_data = json.load(f)

    cases = blind_data["cases"]
    print(f"Processing {len(cases)} cases...")

    mapped_cases  = []
    output_cases  = []
    stats = {"high":0,"medium":0,"low":0,"out_of_scope":0,"engine_error":0}

    for i, case in enumerate(cases):
        case_id = case["case_id"]

        # Step 1: Map symptoms
        mapped = map_case_symptoms(case)
        mapped_cases.append(mapped)
        conf = mapped["mapping_result"]["mapping_confidence"]
        if conf in stats:
            stats[conf] += 1
        else:
            stats["low"] += 1

        # Step 2: Run v2 engine
        if mapped["mapping_result"].get("out_of_scope"):
            out = build_output_case(mapped, {}, {})
            output_cases.append(out)
            print(f"  [{case_id}] OUT_OF_SCOPE")
            continue

        syms   = mapped["mapping_result"]["symptoms_normalized"]
        action = infer_final_action(case, syms)

        try:
            result, etape1 = run_v2_pipeline(syms, action)
            out = build_output_case(mapped, result, etape1)
            # Inject context_flags from atcd
            _atcd = case.get("context", {}).get("atcd", [])
            _ctx_text = " ".join(_atcd) if isinstance(_atcd, list) else str(_atcd)
            _ctx = detect_context_flags(_ctx_text)
            out["clairdiag_output"]["context_flags"]  = _ctx["context_flags"]
            out["clairdiag_output"]["context_alerts"] = _ctx["context_alerts"]
            output_cases.append(out)
            top = out["clairdiag_output"]["top_hypothesis"] or "—"
            print(f"  [{case_id}] conf={conf:<8} top={top}")
        except Exception as e:
            stats["engine_error"] += 1
            output_cases.append({
                "case_id": case_id,
                "label":   case.get("label",""),
                "input_summary": {"symptoms": case.get("symptoms",[]), "patient_framing": None, "context": ""},
                "mapping_confidence": conf,
                "clairdiag_output": None,
                "engine_error": repr(e),
            })
            print(f"  [{case_id}] ERROR: {e}")

    # Save cases_blind_mapped.json
    mapped_output = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_cases":  len(mapped_cases),
            "mapping_stats": stats,
        },
        "cases": mapped_cases,
    }
    with open(mapped_path, "w", encoding="utf-8") as f:
        json.dump(mapped_output, f, ensure_ascii=False, indent=2)

    # Save clairdiag_outputs.json
    n_success = sum(1 for c in output_cases if c.get("clairdiag_output") is not None)
    n_oos     = sum(1 for c in output_cases if c.get("out_of_scope"))
    n_fail    = sum(1 for c in output_cases if c.get("engine_error"))

    final_output = {
        "meta": {
            "version":         "ClairDiag-v2.1",
            "export_type":     "physician_package",
            "generated_at":    datetime.now(timezone.utc).isoformat(),
            "total_cases":     len(output_cases),
            "success":         n_success,
            "out_of_scope":    n_oos,
            "engine_error":    n_fail,
            "failed_case_ids": [c["case_id"] for c in output_cases if c.get("engine_error")],
            "mapping_stats":   stats,
        },
        "cases": output_cases,
    }
    with open(outputs_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)

    # Summary
    print("\n" + "="*60)
    print("  ClairDiag v2 — Validation Pipeline Complete")
    print("="*60)
    print(f"  Total cases       : {len(cases)}")
    print(f"  ✅ Success         : {n_success}")
    print(f"  ⬜ Out of scope    : {n_oos}")
    print(f"  ❌ Engine errors   : {n_fail}")
    print(f"\n  Mapping quality:")
    print(f"    High             : {stats['high']}")
    print(f"    Medium           : {stats['medium']}")
    print(f"    Low              : {stats['low']}")
    print(f"\n  Output files:")
    print(f"    {mapped_path}")
    print(f"    {outputs_path}")
    print("="*60)


if __name__ == "__main__":
    main()