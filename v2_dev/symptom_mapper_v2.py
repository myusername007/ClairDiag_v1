"""
ClairDiag v2 — Symptom Mapper
Converts French clinical text from cases_blind.json → normalized v2 symptom keys.

RULES:
- Dictionary/rules based only — NO heavy NLP
- If uncertain → partial mapping
- If no match → empty list + flag
- Does NOT touch v2 core
"""

import json
import re
import os
import sys
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# DICTIONARY: French clinical text patterns → v2 normalized keys
# Ordered by specificity (longer patterns first to avoid partial matches)
# ──────────────────────────────────────────────────────────────────────────────

SYMPTOM_MAP = [
    # ── Cardiaque ──
    ("douleur thoracique oppressive",       "douleur_thoracique_oppressive"),
    ("douleur thoracique pleurale",         "douleur_thoracique_pleurale"),
    ("douleur thoracique latérale",         "douleur_thoracique_pleurale"),
    ("douleur thoracique constrictive",     "douleur_thoracique_oppressive"),
    ("douleur rétrosternale",               "douleur_thoracique"),
    ("douleur thoracique",                  "douleur_thoracique"),
    ("douleur interscapulaire",             "douleur_thoracique"),
    ("douleur dorsale",                     "douleur_thoracique"),
    ("serrement thoracique",                "douleur_thoracique_oppressive"),
    ("oppression thoracique",               "douleur_thoracique_oppressive"),
    ("brûlure centrale thoracique",         "douleur_thoracique"),
    ("irradiation.*bras",                   "douleur_irradiante_bras"),
    ("irradiation abdominale",              "douleur_epigastrique"),
    ("sueurs froides",                      "sueur_froide"),
    ("sueurs",                              "sueur_froide"),
    ("sueur",                               "sueur_froide"),
    ("tachycardie",                         "tachycardie"),
    ("palpitations",                        "palpitations"),
    ("syncope",                             "syncope"),
    ("perte de connaissance",               "syncope"),
    ("hypotension",                         "hypotension"),
    ("œdème.*cheville",                     "oedeme_membre_inferieur"),
    ("œdèmes.*chevilles",                   "oedeme_membre_inferieur"),
    ("œdème.*membre inférieur",             "oedeme_membre_inferieur"),
    ("œdèmes",                              "oedeme_membre_inferieur"),
    ("mollet.*douloureux",                  "oedeme_membre_inferieur"),
    ("mollet.*gonfl",                       "oedeme_membre_inferieur"),

    # ── Neurologique ──
    ("faiblesse.*unilatérale",              "faiblesse_unilaterale"),
    ("faiblesse.*main",                     "faiblesse_unilaterale"),
    ("faiblesse.*bras",                     "faiblesse_unilaterale"),
    ("faiblesse bilatérale.*jambes",        "faiblesse_unilaterale"),
    ("faiblesse générale",                  "fatigue_intense"),
    ("hémiparésie",                         "faiblesse_unilaterale"),
    ("trouble.*parole",                     "trouble_parole"),
    ("trouble.*élocution",                  "trouble_parole"),
    ("difficulté.*mots",                    "trouble_parole"),
    ("aphasie",                             "trouble_parole"),
    ("bafouill",                            "trouble_parole"),
    ("asymétrie faciale",                   "faiblesse_unilaterale"),
    ("trouble visuel",                      "trouble_vision_brutal"),
    ("amaurose",                            "trouble_vision_brutal"),
    ("scotome",                             "trouble_vision_brutal"),
    ("photophobie",                         "photophobie"),
    ("phonophobie",                         "phonophobie"),
    ("raideur nuque",                       "raideur_nuque"),
    ("raideur.*nuque",                      "raideur_nuque"),
    ("céphalée.*brutale",                   "cephalee_intense_brutale"),
    ("céphalée.*intense",                   "cephalee_intense"),
    ("céphalée.*sévère",                    "cephalee_intense"),
    ("céphalée.*progressive",               "cephalee_intense"),
    ("céphalée",                            "cephalee_pulsatile"),
    ("paresthésies",                        "engourdissement_membre"),
    ("engourdissement",                     "engourdissement_membre"),
    ("paresthésies ascendantes",            "engourdissement_membre"),
    ("confusion",                           "confusion"),
    ("somnolent",                           "fatigue_intense"),
    ("moins alerte",                        "fatigue_intense"),

    # ── Respiratoire ──
    ("dyspnée brutale",                     "dyspnee_brutale"),
    ("dyspnée.*repos",                      "dyspnee"),
    ("dyspnée d'effort",                    "dyspnee_effort"),
    ("dyspnée progressive",                 "dyspnee_effort"),
    ("dyspnée aggravée",                    "dyspnee_effort"),
    ("dyspnée",                             "dyspnee"),
    ("essoufflement",                       "dyspnee_effort"),
    ("souffle",                             "dyspnee_effort"),
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

    # ── Infectieux / Général ──
    ("fièvre.*élevée",                      "fievre_elevee"),
    ("fièvre.*38",                          "fievre_moderee"),
    ("fièvre.*39",                          "fievre_elevee"),
    ("fièvre",                              "fievre_moderee"),
    ("fébricule",                           "fievre_legere"),
    ("frissons",                            "frissons"),
    ("frissons intenses",                   "frissons_intenses"),
    ("altération.*état général.*sévère",    "alteration_etat_general_severe"),
    ("altération.*état général",            "alteration_etat_general"),
    ("altération générale",                 "alteration_etat_general_severe"),
    ("malaise général",                     "malaise_general"),
    ("malaise",                             "malaise_general"),
    ("fatigue intense",                     "fatigue_intense"),
    ("fatigue",                             "fatigue"),
    ("asthénie",                            "fatigue"),
    ("pâleur",                              "fatigue_intense"),
    ("myalgies",                            "myalgies_intenses"),
    ("courbatures",                         "myalgies_intenses"),
    ("perte.*appétit",                      "perte_appetit"),
    ("anorexie",                            "perte_appetit"),
    ("mange moins",                         "perte_appetit"),
    ("mange peu",                           "perte_appetit"),
    ("perte.*poids",                        "perte_appetit"),
    ("amaigrissement",                      "perte_appetit"),
    ("marbrures",                           "hypotension"),

    # ── Digestif ──
    ("douleur épigastrique",                "douleur_epigastrique"),
    ("douleur.*épigastrique",               "douleur_epigastrique"),
    ("douleur.*abdominale.*diffuse",        "douleur_abdominale"),
    ("douleur abdominale",                  "douleur_abdominale"),
    ("douleur.*fosse iliaque droite",       "douleur_fosse_iliaque_droite"),
    ("douleur.*FID",                        "douleur_fosse_iliaque_droite"),
    ("douleur.*hypogastre",                 "douleur_abdominale"),
    ("douleur.*ventre",                     "douleur_abdominale"),
    ("nausées",                             "nausees"),
    ("nausée",                              "nausees"),
    ("vomissements",                        "vomissements"),
    ("vomit",                               "vomissements"),
    ("ballonnements",                       "ballonnements"),
    ("éructation",                          "eructation"),
    ("éructations",                         "eructation"),
    ("diarrhée",                            "diarrhee"),
    ("selles liquides",                     "diarrhee"),
    ("constipation",                        "constipation"),
    ("alternance.*transit",                 "alternance_transit"),
    ("alternance diarrhée/constipation",    "alternance_transit"),
    ("transit.*normal",                     "constipation"),
    ("inconfort.*épigastrique",             "douleur_epigastrique_legere"),
    ("brûlure.*épigastrique",               "brulure_epigastrique"),
    ("reflux",                              "regurgitation"),
    ("sensation.*gorge",                    "mal_gorge"),
    ("ascite",                              "douleur_abdominale"),
    ("respiration rapide.*profonde",        "dyspnee"),

    # ── Neuropsych ──
    ("anxiété",                             "anxiete_intense"),
    ("angoisse",                            "anxiete_intense"),
    ("panique",                             "anxiete_intense"),
    ("vertige.*rotatoire",                  "vertige_positionnel"),
    ("vertige",                             "vertige_positionnel"),
    ("tête.*tourne",                        "vertige_positionnel"),
    ("instabilité.*marche",                 "instabilite_marche"),
    ("tremblement",                         "tremblement"),
    ("insomnie",                            "fatigue"),
    ("dort mal",                            "fatigue"),
    ("palpitation",                         "palpitations"),
]

# ──────────────────────────────────────────────────────────────────────────────
# OUT OF SCOPE cases
# ──────────────────────────────────────────────────────────────────────────────

OUT_OF_SCOPE = {
    "ADV-057": "Pédiatrie (3 ans) — hors scope v2",
    "ADV-058": "Crise psychiatrique / idées suicidaires — hors scope v2",
    "ADV-060": "Soins palliatifs — orientation non diagnostique, hors scope v2",
}

# ──────────────────────────────────────────────────────────────────────────────
# MAPPER
# ──────────────────────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Lowercase, remove accents for matching."""
    text = text.lower()
    replacements = {
        'é':'e','è':'e','ê':'e','ë':'e',
        'à':'a','â':'a','ä':'a',
        'î':'i','ï':'i',
        'ô':'o','ö':'o',
        'ù':'u','û':'u','ü':'u',
        'ç':'c','œ':'oe','æ':'ae',
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    return text


def map_symptom(symptom_text: str) -> Optional[str]:
    """Try to map one symptom string to a v2 key."""
    text_lower = symptom_text.lower()
    # Filtre negations — ne pas mapper les symptomes nieges
    negation_prefixes = ("pas de ", "sans ", "absence de ", "aucun ", "aucune ", "ni ")
    if any(text_lower.startswith(p) for p in negation_prefixes):
        return None
    if " pas de " in text_lower or " sans " in text_lower:
        return None
    text_norm = normalize_text(symptom_text)
    for pattern, key in SYMPTOM_MAP:
        pattern_norm = normalize_text(pattern)
        try:
            if re.search(pattern_norm, text_norm):
                return key
        except re.error:
            if pattern_norm in text_norm:
                return key
    return None


def map_case(case: dict) -> dict:
    case_id  = case["case_id"]
    symptoms = case.get("symptoms", [])

    # Out of scope
    if case_id in OUT_OF_SCOPE:
        return {
            "case_id":            case_id,
            "symptoms_normalized": [],
            "confidence_mapping": "out_of_scope",
            "out_of_scope":       True,
            "out_of_scope_reason": OUT_OF_SCOPE[case_id],
            "original_symptoms":  symptoms,
        }

    mapped     = []
    unmapped   = []
    seen       = set()

    for sym in symptoms:
        key = map_symptom(sym)
        if key and key not in seen:
            mapped.append(key)
            seen.add(key)
        elif not key:
            unmapped.append(sym)

    # Add red flag hints from context
    context = case.get("context", {})
    atcd    = context.get("atcd", [])

    # Confidence scoring
    total = len(symptoms)
    n_mapped = len(mapped)

    if total == 0:
        confidence = "low"
    elif n_mapped == 0:
        confidence = "low"
    elif n_mapped / total >= 0.75:
        confidence = "high"
    elif n_mapped / total >= 0.4:
        confidence = "medium"
    else:
        confidence = "low"

    result = {
        "case_id":             case_id,
        "symptoms_normalized": mapped,
        "confidence_mapping":  confidence,
        "original_symptoms":   symptoms,
    }
    if unmapped:
        result["unmapped_symptoms"] = unmapped

    return result


def run_mapper(input_path: str, output_path: str) -> dict:
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases   = data["cases"]
    results = [map_case(c) for c in cases]

    # Stats
    total       = len(results)
    high        = sum(1 for r in results if r["confidence_mapping"] == "high")
    medium      = sum(1 for r in results if r["confidence_mapping"] == "medium")
    low         = sum(1 for r in results if r["confidence_mapping"] == "low")
    oos         = sum(1 for r in results if r.get("out_of_scope"))
    problematic = [r["case_id"] for r in results if r["confidence_mapping"] in ("low",) and not r.get("out_of_scope")]

    output = {
        "meta": {
            "source":      input_path,
            "total_cases": total,
            "mapping_stats": {
                "high":        high,
                "medium":      medium,
                "low":         low,
                "out_of_scope": oos,
            },
            "problematic_cases": problematic,
        },
        "cases": results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output["meta"]


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_path  = os.path.join(base_dir, "cases_blind.json")
    output_path = os.path.join(base_dir, "cases_blind_mapped.json")

    if not os.path.exists(input_path):
        print(f"ERROR: {input_path} not found")
        sys.exit(1)

    meta = run_mapper(input_path, output_path)

    print("=" * 56)
    print("  ClairDiag v2 — Symptom Mapper")
    print("=" * 56)
    print(f"  Total cases     : {meta['total_cases']}")
    print(f"  ✅ High          : {meta['mapping_stats']['high']}")
    print(f"  🟡 Medium        : {meta['mapping_stats']['medium']}")
    print(f"  🔴 Low           : {meta['mapping_stats']['low']}")
    print(f"  ⬜ Out of scope  : {meta['mapping_stats']['out_of_scope']}")
    if meta["problematic_cases"]:
        print(f"\n  Problematic cases:")
        for c in meta["problematic_cases"]:
            print(f"    - {c}")
    print(f"\n  Output: {output_path}")
    print("=" * 56)