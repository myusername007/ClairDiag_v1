"""
ClairDiag v3 — Real World Stress Test v3.1.0
=============================================
Оновлено під новий common_symptom_mapper v3.1.0:
  - читає and_trigger для CTRL-16 (medical_urgent)
  - читає category="general_vague" замість None
  - CTRL-16/CTRL-17 тепер pass через and_trigger

Запуск:
  cd clairdiag_v1
  python v3_dev/tests/run_rw_stress_test_v3.py
"""

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from common_symptom_mapper import common_symptom_mapper, normalize_text
from and_triggers import check_mollet_gonflement
from v3_confidence_engine import compute_v3_confidence
from loader import COMMON_SYMPTOM_MAPPING, COMMON_CONDITIONS_CONFIG

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def get_category_priority(category: str) -> int:
    for m in COMMON_SYMPTOM_MAPPING:
        if m["category"] == category:
            return m["priority"]
    return 0


def get_urgency_from_config(category: str) -> str:
    if not category or category == "general_vague":
        return COMMON_CONDITIONS_CONFIG.get("general_vague", {}).get("urgency", "medical_consultation")
    return COMMON_CONDITIONS_CONFIG.get(category, {}).get("urgency", "unknown")


def run_case(text: str):
    mapped = common_symptom_mapper(text)
    got_urgent = mapped.get("urgent_trigger") is not None
    got_cat = mapped.get("category")  # тепер завжди є (мінімум general_vague)
    matched_symptoms = mapped.get("matched_symptoms", [])
    cat_priority = get_category_priority(got_cat) if got_cat else 0

    # CTRL-16: and_trigger → medical_urgent
    and_trigger = mapped.get("and_trigger")
    and_trigger_urgency = and_trigger.get("urgency") if and_trigger else None

    # CTRL-17: mollet+gonflement check
    norm_text = normalize_text(text)
    ctrl17 = check_mollet_gonflement(got_cat or "", matched_symptoms, norm_text)
    ctrl17_urgency = ctrl17.get("urgency_override") if ctrl17 else None

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
        and_trigger=and_trigger,
    )

    # Urgency priority: urgent > medical_urgent > ctrl17 > config
    if got_urgent:
        urgency = "urgent"
    elif and_trigger_urgency == "medical_urgent":
        urgency = "medical_urgent"
    elif ctrl17_urgency:
        urgency = ctrl17_urgency
    elif got_cat:
        urgency = get_urgency_from_config(got_cat)
    else:
        urgency = "unknown"

    return {
        "category": got_cat,
        "urgency": urgency,
        "urgent_trigger": mapped.get("urgent_trigger"),
        "and_trigger": and_trigger,
        "ctrl17": ctrl17,
        "confidence_level": confidence["level"],
        "confidence_score": confidence["score"],
        "matched_symptoms": matched_symptoms,
        "orientation_summary": confidence.get("orientation_summary", ""),
    }


CONTROL_CASES = [
    {"id": "CTRL-01", "input": "J'ai mal à la gorge et le nez bouché",
     "expected": {"category": "orl_simple", "urgency": "non_urgent", "min_confidence": "medium"}},
    {"id": "CTRL-02", "input": "Nez qui coule, éternuements et gorge irritée",
     "expected": {"category": "orl_simple", "urgency": "non_urgent", "min_confidence": "medium"}},
    {"id": "CTRL-03", "input": "J'ai des brûlures urinaires et j'urine souvent",
     "expected": {"category": "urinaire", "urgency": "medical_consultation", "min_confidence": "medium"}},
    {"id": "CTRL-04", "input": "Fatigue, prise de poids et peau sèche depuis 2 mois",
     "expected": {"category": "metabolique_hormonal_suspect", "urgency": "medical_consultation", "min_confidence": "medium"}},
    {"id": "CTRL-05", "input": "J'ai mal au ventre et de la diarrhée depuis 2 jours",
     "expected": {"category": "digestif_simple", "urgency": "medical_consultation", "min_confidence": "medium"}},
    {"id": "CTRL-06", "input": "J'ai mal au dos après le sport",
     "expected": {"category": "musculo_squelettique", "urgency": "non_urgent", "min_confidence": "low"}},
    {"id": "CTRL-07", "input": "Je dors mal et je suis stressé",
     "expected": {"category": "sommeil_stress_anxiete", "urgency": "non_urgent", "min_confidence": "medium"}},
    {"id": "CTRL-08", "input": "J'ai des boutons rouges sur le visage et ça gratte",
     "expected": {"category": "dermatologie_simple", "urgency": "non_urgent", "min_confidence": "medium"}},
    {"id": "CTRL-09", "input": "Je suis fatigué mais pas de fièvre",
     "expected": {"category": "fatigue_asthenie", "urgency": "medical_consultation", "min_confidence": "low"}},
    {"id": "CTRL-10", "input": "Je ne me sens pas bien depuis quelques jours",
     "expected": {"category": "general_vague", "urgency": "medical_consultation", "min_confidence": "low"}},
    {"id": "CTRL-11", "input": "J'ai mal à la poitrine avec des sueurs froides",
     "expected": {"category": "v2_override", "urgency": "urgent", "min_confidence": "high"}},
    {"id": "CTRL-12", "input": "J'ai du mal à respirer depuis ce matin",
     "expected": {"category": "v2_override", "urgency": "urgent", "min_confidence": "high"}},
    {"id": "CTRL-13", "input": "J'ai perdu connaissance il y a une heure",
     "expected": {"category": "v2_override", "urgency": "urgent", "min_confidence": "high"}},
    {"id": "CTRL-14", "input": "J'ai des idées suicidaires",
     "expected": {"category": "v2_override", "urgency": "urgent", "min_confidence": "high"}},
    {"id": "CTRL-15", "input": "Douleur ventre très forte et brutale",
     "expected": {"category": "v2_override", "urgency": "urgent", "min_confidence": "high"}},
    {"id": "CTRL-16", "input": "Brûlure urinaire + fièvre + mal au dos",
     "expected": {"category": "urinaire", "urgency": "medical_urgent", "min_confidence": "high"}},
    {"id": "CTRL-17", "input": "Douleur mollet avec gonflement",
     "expected": {"category": "musculo_squelettique", "urgency": "medical_consultation", "min_confidence": "medium"}},
    {"id": "CTRL-18", "input": "Perte de poids + fatigue + palpitations",
     "expected": {"category": "metabolique_hormonal_suspect", "urgency": "medical_consultation", "min_confidence": "medium"}},
    {"id": "CTRL-19", "input": "Nausées et vomissements depuis 2 jours",
     "expected": {"category": "digestif_simple", "urgency": "medical_consultation", "min_confidence": "medium"}},
    {"id": "CTRL-20", "input": "Règles en retard avec douleur bas ventre",
     "expected": {"category": "gynecologique_simple", "urgency": "medical_consultation", "min_confidence": "medium"}},
]

BLIND_CASES = [
    {"id": "RW-01", "input": "j'ai mal au ventre depuis 3 jours je sais pas pk ça part pas"},
    {"id": "RW-02", "input": "jsui crevé tt le temps pas d'energie"},
    {"id": "RW-03", "input": "nez bouché gorge qui pique je tousse un peu"},
    {"id": "RW-04", "input": "ça brûle quand je fais pipi et j'y vais tout le temps"},
    {"id": "RW-05", "input": "j'ai des boutons sur la joue et ça gratte de ouf"},
    {"id": "RW-06", "input": "jme sens bizarre depuis 2 semaines fatigué et froid"},
    {"id": "RW-07", "input": "mal au dos apres sport ça tire ds la jambe"},
    {"id": "RW-08", "input": "j'ai mal à la poitrine mais ça passe quand je me pose"},
    {"id": "RW-09", "input": "j'arrive pas a dormir jsui stressé"},
    {"id": "RW-10", "input": "ventre gonflé + gaz + pas allé a la selle depuis 4j"},
    {"id": "RW-11", "input": "envie de vomir depuis hier et mal au bide"},
    {"id": "RW-12", "input": "j'ai maigri sans raison et coeur qui bat vite"},
    {"id": "RW-13", "input": "ça gratte partout peau sèche jsp pourquoi"},
    {"id": "RW-14", "input": "règles en retard + mal bas ventre"},
    {"id": "RW-15", "input": "je tousse bcp et j'ai un peu de fièvre je crois"},
    {"id": "RW-16", "input": "fatigue + mal tete + jme sens pas bien"},
    {"id": "RW-17", "input": "j'ai mal au mollet et il est gonflé"},
    {"id": "RW-18", "input": "je respire mal depuis ce matin"},
    {"id": "RW-19", "input": "j'ai des pertes bizarres et douleurs bas ventre"},
    {"id": "RW-20", "input": "jsais pas ce que j'ai mais jme sens mal depuis qq jours"},
    {"id": "RW-21", "input": "mal gorge + nez qui coule + éternue"},
    {"id": "RW-22", "input": "j'ai pris du poids et jsui fatiguée tt le temps"},
    {"id": "RW-23", "input": "douleur ventre tres forte d'un coup"},
    {"id": "RW-24", "input": "brulure pipi + odeur bizarre urines"},
    {"id": "RW-25", "input": "je dors mal + stress + je rumine tout le temps"},
    {"id": "RW-26", "input": "boutons rouges + plaques + ça gratte bcp"},
    {"id": "RW-27", "input": "mal au genou apres sport ça bloque"},
    {"id": "RW-28", "input": "j'ai froid tout le temps + chute de cheveux"},
    {"id": "RW-29", "input": "je suis fatigué mais pas de fièvre"},
    {"id": "RW-30", "input": "j'ai chaud froid tremblements bizarre"},
]


def run_control(cases):
    passed = failed = 0
    danger_log = {"missed_danger": [], "wrong_category": [], "over_alarm": [], "under_alarm": []}

    for case in cases:
        cid = case["id"]
        text = case["input"]
        exp = case["expected"]
        result = run_case(text)
        issues = []

        exp_urgency = exp["urgency"]
        got_urgency = result["urgency"]
        got_cat = result["category"]
        exp_cat = exp["category"]
        got_conf = result["confidence_level"]
        min_conf = exp["min_confidence"]

        # Urgency check
        if exp_urgency == "urgent":
            if got_urgency != "urgent":
                issues.append(f"urgency: expected=urgent, got={got_urgency}")
                danger_log["missed_danger"].append({"id": cid, "input": text[:60], "got_urgency": got_urgency})
        elif exp_urgency == "medical_urgent":
            if got_urgency != "medical_urgent":
                issues.append(f"urgency: expected=medical_urgent, got={got_urgency}")
                danger_log["under_alarm"].append({"id": cid, "input": text[:60], "note": f"got={got_urgency}"})
        else:
            if got_urgency == "urgent":
                issues.append(f"urgency: over_alarm got=urgent, expected={exp_urgency}")
                danger_log["over_alarm"].append({"id": cid, "input": text[:60], "expected": exp_urgency})
            elif got_urgency != exp_urgency:
                issues.append(f"urgency: expected={exp_urgency}, got={got_urgency}")

        # Category check
        if exp_cat == "v2_override":
            if got_urgency != "urgent":
                issues.append(f"category: expected v2_override(urgent), got cat={got_cat}, urg={got_urgency}")
        else:
            if got_cat != exp_cat:
                issues.append(f"category: expected={exp_cat}, got={got_cat}")
                danger_log["wrong_category"].append({"id": cid, "input": text[:60], "expected": exp_cat, "got": got_cat})

        # Confidence check
        if CONFIDENCE_ORDER.get(got_conf, 0) < CONFIDENCE_ORDER.get(min_conf, 0):
            issues.append(f"confidence: expected>={min_conf}, got={got_conf}({result['confidence_score']})")

        if not issues:
            passed += 1
            print(f"  ✅ [{cid}] {text[:55]}")
        else:
            failed += 1
            print(f"  ❌ [{cid}] {text[:55]}")
            for iss in issues:
                print(f"       ⚠ {iss}")
            print(f"       → cat={result['category']} | urg={result['urgency']} | conf={result['confidence_level']}({result['confidence_score']})")
            if result.get("and_trigger"):
                print(f"       → and_trigger: {result['and_trigger']['and_trigger']}")
            if result.get("ctrl17"):
                print(f"       → ctrl17: {result['ctrl17']['and_trigger']}")

    return passed, failed, danger_log


def run_blind(cases):
    for case in cases:
        cid = case["id"]
        text = case["input"]
        result = run_case(text)
        urgent_flag = " 🚨 URGENT" if result["urgency"] == "urgent" else (
            " ⚠️ MEDICAL_URGENT" if result["urgency"] == "medical_urgent" else ""
        )
        syms = ", ".join(result["matched_symptoms"][:3]) if result["matched_symptoms"] else "—"
        print(f"  [{cid}] {text[:60]}")
        print(f"         cat={result['category']} | urg={result['urgency']} | conf={result['confidence_level']}({result['confidence_score']}){urgent_flag}")
        print(f"         matched: {syms}")
        print(f"         summary: {result['orientation_summary'][:80]}")
        if result.get("and_trigger"):
            print(f"         and_trigger: {result['and_trigger']['and_trigger']}")
        print()


def print_danger_log(log):
    print("=" * 65)
    print("DANGER LOG")
    print("=" * 65)
    sections = [
        ("missed_danger",  "🔴 MISSED DANGER — urgent пропущено"),
        ("under_alarm",    "🟠 UNDER-ALARM — рівень занижено"),
        ("over_alarm",     "🟡 OVER-ALARM — зайвий urgent"),
        ("wrong_category", "🔵 WRONG CATEGORY"),
    ]
    any_found = False
    for key, label in sections:
        items = log.get(key, [])
        if items:
            any_found = True
            print(f"\n{label}:")
            for item in items:
                print(f"  [{item['id']}] {item.get('input', '')[:60]}")
                if "note" in item:
                    print(f"         note: {item['note']}")
                if "expected" in item and "got" in item:
                    print(f"         expected={item['expected']}, got={item['got']}")
                if "got_urgency" in item:
                    print(f"         got_urgency={item['got_urgency']}")
    if not any_found:
        print("\n✅ Жодних небезпечних помилок не виявлено")


if __name__ == "__main__":
    print(f"\n{'=' * 65}")
    print("ClairDiag v3 — Real World Stress Test v3.1.0")
    print(f"{'=' * 65}")

    print(f"\n{'─' * 65}")
    print("CONTROL (20 кейсів з expected)")
    print(f"{'─' * 65}")
    cp, cf, danger_log = run_control(CONTROL_CASES)
    print(f"\n  CONTROL: {cp}/20 passed, {cf} failed")

    print(f"\n{'─' * 65}")
    print("BLIND (30 кейсів — для ручного review)")
    print(f"{'─' * 65}\n")
    run_blind(BLIND_CASES)

    print_danger_log(danger_log)

    print(f"\n{'=' * 65}")
    print(f"ЗАГАЛЬНИЙ РЕЗУЛЬТАТ CONTROL: {cp}/20")
    print(f"{'=' * 65}\n")