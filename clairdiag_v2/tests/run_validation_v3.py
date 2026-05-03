"""
ClairDiag v3 — External Validation Runner v3.0.2

Запускає 50 external validation cases + 8 calibration cases.
Порівнює результат з expected без виклику v2 (isolated mapper test).

Маппінг категорій зовнішньої spec → наш формат:
  ORL_simple                    → orl_simple
  sommeil_stress_anxiete_non_urgent → sommeil_stress_anxiete
  general_vague_non_specifique  → general_vague

Запуск:
  cd clairdiag_v1
  python v3_dev/tests/run_validation_v3.py
"""

import os
import sys
import json

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from common_symptom_mapper import common_symptom_mapper
from v3_confidence_engine import compute_v3_confidence
from loader import COMMON_SYMPTOM_MAPPING

# ── Маппінг зовнішніх назв → наші ────────────────────────────────────────────

CATEGORY_NORMALIZE = {
    "ORL_simple":                        "orl_simple",
    "orl_simple":                        "orl_simple",
    "sommeil_stress_anxiete_non_urgent": "sommeil_stress_anxiete",
    "sommeil_stress_anxiete":            "sommeil_stress_anxiete",
    "general_vague_non_specifique":      "general_vague",
    "general_vague":                     "general_vague",
    "dermatologie_simple":               "dermatologie_simple",
    "digestif_simple":                   "digestif_simple",
    "fatigue_asthenie":                  "fatigue_asthenie",
    "musculo_squelettique":              "musculo_squelettique",
    "urinaire":                          "urinaire",
    "gynecologique_simple":              "gynecologique_simple",
    "metabolique_hormonal_suspect":      "metabolique_hormonal_suspect",
    "red_flag_detected":                 None,  # urgent
    "blocked_pediatric":                 None,  # urgent
}


def normalize_cat(cat: str) -> str:
    return CATEGORY_NORMALIZE.get(cat, cat)


def get_category_priority(category: str) -> int:
    for m in COMMON_SYMPTOM_MAPPING:
        if m["category"] == category:
            return m["priority"]
    return 0


# ── 50 validation cases (вбудовані) ──────────────────────────────────────────

CASES = [
    # DERMATOLOGIE
    {"id": "V3-001", "text": "j'ai des boutons sur le visage depuis 3 jours, ça gratte un peu",
     "expected_cat": "dermatologie_simple", "expect_urgent": False},
    {"id": "V3-002", "text": "j'ai une plaque rouge qui démange sur le bras",
     "expected_cat": "dermatologie_simple", "expect_urgent": False},
    {"id": "V3-003", "text": "ma peau est très sèche cet hiver, surtout les mains",
     "expected_cat": "metabolique_hormonal_suspect", "expect_urgent": False},
    {"id": "V3-004", "text": "j'ai de l'urticaire qui est apparu après avoir mangé des fraises",
     "expected_cat": "dermatologie_simple", "expect_urgent": False},
    {"id": "V3-005", "text": "j'ai de l'eczéma sur les coudes qui revient",
     "expected_cat": "dermatologie_simple", "expect_urgent": False},
    # ORL
    {"id": "V3-006", "text": "j'ai le nez qui coule et un peu mal à la gorge depuis hier",
     "expected_cat": "orl_simple", "expect_urgent": False},
    {"id": "V3-007", "text": "je tousse un peu, c'est plutôt sec, depuis 3 jours",
     "expected_cat": "orl_simple", "expect_urgent": False},
    {"id": "V3-008", "text": "j'ai la voix cassée et un rhume",
     "expected_cat": "orl_simple", "expect_urgent": False},
    {"id": "V3-009", "text": "je crois que j'ai un rhume, nez bouché et un peu de fièvre à 37,8",
     "expected_cat": "orl_simple", "expect_urgent": False},
    # DIGESTIF
    {"id": "V3-010", "text": "j'ai le ventre gonflé et des gaz depuis quelques jours",
     "expected_cat": "digestif_simple", "expect_urgent": False},
    {"id": "V3-011", "text": "je suis constipé depuis 4 jours",
     "expected_cat": "digestif_simple", "expect_urgent": False},
    {"id": "V3-012", "text": "j'ai eu une gastro hier, diarrhée et nausées, ça commence à passer",
     "expected_cat": "digestif_simple", "expect_urgent": False},
    {"id": "V3-013", "text": "j'ai des aigreurs et des éructations après les repas",
     "expected_cat": "digestif_simple", "expect_urgent": False},
    # FATIGUE
    {"id": "V3-014", "text": "je suis fatigué tout le temps, même après une nuit de sommeil",
     "expected_cat": "fatigue_asthenie", "expect_urgent": False},
    {"id": "V3-015", "text": "je manque d'énergie depuis 2 mois",
     "expected_cat": "fatigue_asthenie", "expect_urgent": False},
    {"id": "V3-016", "text": "je suis épuisée, je n'arrive plus à faire ce que je faisais avant",
     "expected_cat": "fatigue_asthenie", "expect_urgent": False},
    {"id": "V3-017", "text": "je suis à plat depuis quelques semaines, pas la pêche",
     "expected_cat": "fatigue_asthenie", "expect_urgent": False},
    # MUSCULO
    {"id": "V3-018", "text": "j'ai mal au dos depuis que j'ai porté un meuble lourd hier",
     "expected_cat": "musculo_squelettique", "expect_urgent": False},
    {"id": "V3-019", "text": "ma nuque est complètement bloquée depuis ce matin",
     "expected_cat": "musculo_squelettique", "expect_urgent": False},
    {"id": "V3-020", "text": "j'ai mal au genou quand je monte les escaliers",
     "expected_cat": "musculo_squelettique", "expect_urgent": False},
    {"id": "V3-021", "text": "j'ai des courbatures partout après le sport",
     "expected_cat": "musculo_squelettique", "expect_urgent": False},
    # URINAIRE
    {"id": "V3-022", "text": "ça brûle quand je fais pipi et j'ai envie tout le temps",
     "expected_cat": "urinaire", "expect_urgent": False},
    {"id": "V3-023", "text": "je crois que j'ai une cystite, ça pique en urinant",
     "expected_cat": "urinaire", "expect_urgent": False},
    {"id": "V3-024", "text": "mes urines sont troubles et sentent fort",
     "expected_cat": "urinaire", "expect_urgent": False},
    # GYNECO
    {"id": "V3-025", "text": "mes règles sont irrégulières depuis quelques mois",
     "expected_cat": "gynecologique_simple", "expect_urgent": False},
    {"id": "V3-026", "text": "j'ai mal au ventre pendant mes règles, comme d'habitude mais c'est pénible",
     "expected_cat": "gynecologique_simple", "expect_urgent": False},
    {"id": "V3-027", "text": "j'ai des pertes blanches habituelles, sans odeur ni démangeaisons",
     "expected_cat": "gynecologique_simple", "expect_urgent": False},
    # METABOLIQUE
    {"id": "V3-028", "text": "j'ai pris 6 kg en 4 mois sans changer mon alimentation, j'ai toujours froid et la peau très sèche",
     "expected_cat": "metabolique_hormonal_suspect", "expect_urgent": False},
    {"id": "V3-029", "text": "j'ai très soif tout le temps et j'urine beaucoup, je me lève la nuit pour ça",
     "expected_cat": "metabolique_hormonal_suspect", "expect_urgent": False},
    {"id": "V3-030", "text": "je perds mes cheveux et ma peau est sèche depuis quelques mois",
     "expected_cat": "metabolique_hormonal_suspect", "expect_urgent": False},
    {"id": "V3-031", "text": "j'ai chaud tout le temps, je transpire beaucoup, j'ai des palpitations et j'ai perdu 4 kg",
     "expected_cat": "metabolique_hormonal_suspect", "expect_urgent": False},
    # SOMMEIL / STRESS
    {"id": "V3-032", "text": "je n'arrive pas à dormir depuis 2 semaines, beaucoup de stress au travail",
     "expected_cat": "sommeil_stress_anxiete", "expect_urgent": False},
    {"id": "V3-033", "text": "je me sens stressé et tendu en ce moment",
     "expected_cat": "sommeil_stress_anxiete", "expect_urgent": False},
    {"id": "V3-034", "text": "j'ai des petites angoisses le soir, ça m'empêche parfois de m'endormir",
     "expected_cat": "sommeil_stress_anxiete", "expect_urgent": False},
    # GENERAL VAGUE
    {"id": "V3-035", "text": "je ne me sens pas bien, je sais pas pourquoi",
     "expected_cat": "general_vague", "expect_urgent": False},
    {"id": "V3-036", "text": "j'ai pas la forme depuis quelque temps",
     "expected_cat": "general_vague", "expect_urgent": False},
    {"id": "V3-037", "text": "j'ai un truc bizarre depuis hier mais je sais pas comment expliquer",
     "expected_cat": "general_vague", "expect_urgent": False},
    # RED FLAGS
    {"id": "V3-038", "text": "j'ai une douleur dans la poitrine qui serre depuis 30 minutes, je transpire",
     "expected_cat": None, "expect_urgent": True},
    {"id": "V3-039", "text": "j'ai des selles noires depuis 2 jours et je suis très fatigué",
     "expected_cat": None, "expect_urgent": True},
    {"id": "V3-040", "text": "ma bouche est tordue depuis ce matin et je n'arrive plus à parler correctement",
     "expected_cat": None, "expect_urgent": True},
    {"id": "V3-041", "text": "j'ai un essoufflement brutal et je n'arrive plus à respirer",
     "expected_cat": None, "expect_urgent": True},
    {"id": "V3-042", "text": "j'ai mal au ventre brutal et intense depuis 2 heures, mon ventre est dur comme du bois",
     "expected_cat": None, "expect_urgent": True},
    {"id": "V3-043", "text": "j'ai des taches rouges sur les jambes qui ne partent pas quand j'appuie dessus, et de la fièvre",
     "expected_cat": None, "expect_urgent": True},
    {"id": "V3-044", "text": "j'ai des idées suicidaires, je ne sais plus quoi faire",
     "expected_cat": None, "expect_urgent": True},
    {"id": "V3-045", "text": "j'ai mal au ventre intense et j'ai un retard de règles",
     "expected_cat": None, "expect_urgent": True},
    {"id": "V3-046", "text": "ma fille de 10 ans a beaucoup de fièvre et de la raideur de la nuque",
     "expected_cat": None, "expect_urgent": True},
    # MULTI-CATEGORY
    {"id": "V3-047", "text": "je suis fatigué et j'ai mal au dos depuis 2 semaines",
     "expected_cat": "musculo_squelettique", "expect_urgent": False},
    {"id": "V3-048", "text": "j'ai des boutons et je suis épuisée",
     "expected_cat": "dermatologie_simple", "expect_urgent": False},
    {"id": "V3-049", "text": "j'ai mal à la gorge, je tousse, et j'ai très chaud avec des courbatures",
     "expected_cat": "orl_simple", "expect_urgent": False},
    {"id": "V3-050", "text": "j'ai pris du poids, je suis stressée, et je dors mal",
     "expected_cat": "metabolique_hormonal_suspect", "expect_urgent": False},
]

# ── Calibration cases ─────────────────────────────────────────────────────────

CALIBRATION_CASES = [
    {
        "id": "CAL-01",
        "text": "J'ai mal à la gorge et le nez bouché",
        "expected_cat": "orl_simple",
        "expect_urgent": False,
        "expect_confidence_min": 5,
        "expect_confidence_level": "medium",
        "expect_danger_hidden": True,
    },
    {
        "id": "CAL-02",
        "text": "J'ai mal à la gorge et le nez bouché depuis 10 jours, pas d'amélioration",
        "expected_cat": "orl_simple",
        "expect_urgent": False,
        "expect_danger_hidden": False,
    },
    {
        "id": "CAL-03",
        "text": "Rhume avec nez qui coule, mal de gorge et toux légère depuis 2 jours",
        "expected_cat": "orl_simple",
        "expect_urgent": False,
        "expect_confidence_min": 7,
        "expect_confidence_level": "high",
    },
    {
        "id": "CAL-04",
        "text": "J'ai des boutons sur le visage",
        "expected_cat": "dermatologie_simple",
        "expect_urgent": False,
        "expect_no_reasons_field": True,
    },
    {
        "id": "CAL-05",
        "text": "J'ai des brûlures quand j'urine et j'y vais tout le temps",
        "expected_cat": "urinaire",
        "expect_urgent": False,
        "expect_confidence_min": 6,
        "expect_confidence_level": "medium",
    },
    {
        "id": "CAL-06",
        "text": "Je suis fatigué tout le temps depuis 3 semaines",
        "expected_cat": "fatigue_asthenie",
        "expect_urgent": False,
        "expect_danger_hidden": False,
    },
    {
        "id": "CAL-07",
        "text": "J'ai un rhume",
        "expected_cat": "orl_simple",
        "expect_urgent": False,
        "expect_confidence_min": 5,
        "expect_confidence_level": "medium",
    },
    {
        "id": "CAL-08",
        "text": "Je ne me sens pas bien, j'ai un truc bizarre",
        "expected_cat": "general_vague",
        "expect_urgent": False,
        "expect_confidence_level": "low",
    },
]


# ── Runner ────────────────────────────────────────────────────────────────────

def run_standard(cases):
    passed = failed = partial = 0
    fails = []

    for case in cases:
        text = case["text"]
        expected_cat = normalize_cat(case.get("expected_cat", ""))
        expect_urgent = case.get("expect_urgent", False)

        mapped = common_symptom_mapper(text)
        got_urgent = mapped.get("urgent_trigger") is not None
        got_cat = mapped.get("category")

        if expect_urgent:
            ok = got_urgent
        else:
            ok = (not got_urgent) and (got_cat == expected_cat)

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
            fails.append({
                "id": case["id"],
                "text": text[:60],
                "expected": f"urgent={expect_urgent}, cat={expected_cat}",
                "got": f"urgent={got_urgent}, cat={got_cat}",
            })

    return passed, failed, fails


def run_calibration(cases):
    passed = failed = 0
    fails = []

    for case in cases:
        text = case["text"]
        expected_cat = normalize_cat(case.get("expected_cat", ""))
        expect_urgent = case.get("expect_urgent", False)

        mapped = common_symptom_mapper(text)
        got_urgent = mapped.get("urgent_trigger") is not None
        got_cat = mapped.get("category")
        matched_symptoms = mapped.get("matched_symptoms", [])
        cat_priority = get_category_priority(got_cat) if got_cat else 0

        confidence = compute_v3_confidence(
            category=got_cat,
            category_matches=mapped.get("category_matches", 0),
            all_hits=mapped.get("all_hits", []),
            combination_matched=False,
            temporal=mapped.get("temporal", "unknown"),
            patient_context=None,
            urgent_trigger=mapped.get("urgent_trigger"),
            matched_symptoms=matched_symptoms,
            category_priority=cat_priority,
        )

        issues = []

        # Перевірка категорії
        if expect_urgent:
            if not got_urgent:
                issues.append(f"expected urgent, got cat={got_cat}")
        else:
            if got_urgent or got_cat != expected_cat:
                issues.append(f"cat: expected={expected_cat}, got={got_cat}")

        # Перевірка confidence
        if "expect_confidence_min" in case:
            if confidence["score"] < case["expect_confidence_min"]:
                issues.append(
                    f"confidence score: expected≥{case['expect_confidence_min']}, "
                    f"got={confidence['score']}"
                )
        if "expect_confidence_level" in case:
            if confidence["level"] != case["expect_confidence_level"]:
                issues.append(
                    f"confidence level: expected={case['expect_confidence_level']}, "
                    f"got={confidence['level']}"
                )

        # Перевірка danger hidden (CAL-01, CAL-02)
        if "expect_danger_hidden" in case:
            # Для перевірки треба знати urgency — беремо з config
            from loader import COMMON_CONDITIONS_CONFIG, DANGER_EXPOSURE_THRESHOLDS
            from general_orientation_router import should_expose_danger
            from common_symptom_mapper import extract_duration_days
            dur = extract_duration_days(text.lower())
            cat = got_cat or "general_vague"
            cfg = COMMON_CONDITIONS_CONFIG.get(cat, {})
            urgency = cfg.get("urgency", "non_urgent")
            exposed = should_expose_danger(cat, urgency, dur, False)
            expected_exposed = not case["expect_danger_hidden"]
            if exposed != expected_exposed:
                issues.append(
                    f"danger exposure: expected={'visible' if expected_exposed else 'hidden'}, "
                    f"got={'visible' if exposed else 'hidden'}"
                )

        # Перевірка відсутності технічних reasons (CAL-04)
        if case.get("expect_no_reasons_field"):
            # reasons не повинно бути в confidence_detail — тепер є orientation_summary
            if "reasons" in confidence:
                issues.append("field 'reasons' should not be in patient output")

        if not issues:
            passed += 1
        else:
            failed += 1
            fails.append({
                "id": case["id"],
                "text": text[:60],
                "issues": issues,
                "confidence": confidence,
            })

    return passed, failed, fails


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{'='*65}")
    print("ClairDiag v3 — External Validation Report v3.0.2")
    print(f"{'='*65}")

    # Standard 50 cases
    p, f, fails = run_standard(CASES)
    print(f"\n📋 Standard cases: {p}/{len(CASES)} passed, {f} failed")
    if fails:
        print("\nFailed:")
        for fl in fails:
            print(f"  ❌ [{fl['id']}] {fl['text']}")
            print(f"       expected: {fl['expected']}")
            print(f"       got:      {fl['got']}")

    # Calibration 8 cases
    cp, cf, cfails = run_calibration(CALIBRATION_CASES)
    print(f"\n🎯 Calibration cases: {cp}/{len(CALIBRATION_CASES)} passed, {cf} failed")
    if cfails:
        print("\nFailed:")
        for fl in cfails:
            print(f"  ❌ [{fl['id']}] {fl['text']}")
            for issue in fl["issues"]:
                print(f"       issue: {issue}")
            print(f"       confidence: {fl['confidence']}")

    total_p = p + cp
    total = len(CASES) + len(CALIBRATION_CASES)
    print(f"\n{'='*65}")
    print(f"ЗАГАЛЬНИЙ РЕЗУЛЬТАТ: {total_p}/{total} passed")
    print(f"  Standard:    {p}/{len(CASES)}")
    print(f"  Calibration: {cp}/{len(CALIBRATION_CASES)}")
    print(f"{'='*65}\n")