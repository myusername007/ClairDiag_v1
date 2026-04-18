"""
ClairDiag v2 — Safety Floor Validator

Гоняє:
  1. Positive controls (12) — safety floor works as expected
  2. Negative controls (10) — safety floor does NOT trigger when it shouldn't

Використання:
  python run_tests_v2_stress.py
  python run_tests_v2_stress.py --verbose
  python run_tests_v2_stress.py --only positive
  python run_tests_v2_stress.py --only negative
"""

import json
import argparse
import os
import sys

from medical_probability_engine import run_probability_engine
from test_recommendation_engine import run_recommendation_engine

# ──────────────────────────────────────────────
# CHARGEMENT
# ──────────────────────────────────────────────

def load_tests(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ──────────────────────────────────────────────
# PIPELINE
# ──────────────────────────────────────────────

def run_pipeline(symptoms: list, final_action: str, base_dir: str) -> dict:
    v1_output = {
        "symptoms_normalized": symptoms,
        "red_flags":           [],
        "final_action_v1":     final_action,
    }
    etape1 = run_probability_engine(
        v1_output       = v1_output,
        conditions_path = os.path.join(base_dir, "conditions_master.json"),
        weights_path    = os.path.join(base_dir, "condition_weights.json"),
    )
    return run_recommendation_engine(
        etape1_output     = etape1,
        v1_output         = v1_output,
        conditions_path   = os.path.join(base_dir, "conditions_master.json"),
        tests_path        = os.path.join(base_dir, "tests_master.json"),
        differential_path = os.path.join(base_dir, "differential_rules.json"),
    )

# ──────────────────────────────────────────────
# ОЦІНКА POSITIVE
# ──────────────────────────────────────────────

CONFIDENCE_RANK = {"faible": 1, "modéré": 2, "élevé": 3}

def evaluate_positive(case: dict, base_dir: str) -> dict:
    result   = run_pipeline(case["symptoms_normalized"], case["final_action_v1"], base_dir)
    failures = []

    sf            = result.get("safety_floor", {})
    floor_triggered = sf.get("triggered", False)
    confidence    = result.get("confidence_level", "faible")
    min_conf      = case.get("expect_min_confidence", "modéré")

    if case["expect_safety_floor"] and not floor_triggered:
        failures.append("safety_floor НЕ спрацював (очікувався)")

    if CONFIDENCE_RANK.get(confidence, 0) < CONFIDENCE_RANK.get(min_conf, 2):
        failures.append(f"confidence: очікувано >= '{min_conf}', отримано '{confidence}'")

    return {
        "id":          case["id"],
        "label":       case["label"],
        "passed":      len(failures) == 0,
        "failures":    failures,
        "floor":       floor_triggered,
        "confidence":  confidence,
        "orientation": result.get("medical_orientation_v2"),
        "changes":     sf.get("changes", []),
    }

# ──────────────────────────────────────────────
# ОЦІНКА NEGATIVE
# ──────────────────────────────────────────────

def evaluate_negative(case: dict, base_dir: str) -> dict:
    result   = run_pipeline(case["symptoms_normalized"], case["final_action_v1"], base_dir)
    failures = []

    sf              = result.get("safety_floor", {})
    floor_triggered = sf.get("triggered", False)
    orientation     = result.get("medical_orientation_v2", "")

    if floor_triggered and not case["expect_safety_floor"]:
        matched = [f["matched_symptom"] for f in sf.get("matched_flags", [])]
        failures.append(f"safety_floor спрацював (НЕ очікувався) — matched: {matched}")

    # orientation не має бути urgent_emergency для benign кейсів
    if orientation == "urgent_emergency_workup":
        failures.append(f"orientation занадто висока: '{orientation}'")

    return {
        "id":          case["id"],
        "label":       case["label"],
        "passed":      len(failures) == 0,
        "failures":    failures,
        "floor":       floor_triggered,
        "confidence":  result.get("confidence_level"),
        "orientation": orientation,
        "notes":       case.get("notes", ""),
    }

# ──────────────────────────────────────────────
# RUNNER
# ──────────────────────────────────────────────

def run_suite(
    title:    str,
    cases:    list,
    mode:     str,
    base_dir: str,
    verbose:  bool = False,
) -> tuple:
    total  = len(cases)
    passed = 0

    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print()

    for case in cases:
        if mode == "positive":
            r = evaluate_positive(case, base_dir)
        else:
            r = evaluate_negative(case, base_dir)

        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        if r["passed"]:
            passed += 1

        print(f"  [{r['id']}] {status}  {r['label']}")

        if not r["passed"]:
            for f in r["failures"]:
                print(f"         ⚠ {f}")

        if verbose:
            print(
                f"         floor={r['floor']} "
                f"conf={r['confidence']} "
                f"orient={r['orientation']}"
            )
            if r.get("changes"):
                print(f"         changes={r['changes']}")

    print()
    return passed, total


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ClairDiag v2 Safety Floor Validator")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--only", type=str, default=None, choices=["positive", "negative"],
                        help="Запустити тільки positive або negative")
    args = parser.parse_args()

    base_dir   = os.path.dirname(os.path.abspath(__file__))
    tests_path = os.path.join(base_dir, "tests_v2_safety.json")
    data       = load_tests(tests_path)

    pos_passed = pos_total = 0
    neg_passed = neg_total = 0

    if args.only != "negative":
        pos_passed, pos_total = run_suite(
            title    = "Positive Controls — safety floor should trigger",
            cases    = data["positive_controls"],
            mode     = "positive",
            base_dir = base_dir,
            verbose  = args.verbose,
        )

    if args.only != "positive":
        neg_passed, neg_total = run_suite(
            title    = "Negative Controls — safety floor should NOT trigger",
            cases    = data["negative_controls"],
            mode     = "negative",
            base_dir = base_dir,
            verbose  = args.verbose,
        )

    grand_passed = pos_passed + neg_passed
    grand_total  = pos_total  + neg_total

    print("=" * 60)
    print("  ClairDiag v2 — Safety Floor Global Validation")
    print("=" * 60)
    if pos_total:
        print(f"  Positive controls : {pos_passed}/{pos_total}")
    if neg_total:
        print(f"  Negative controls : {neg_passed}/{neg_total}")
    print(f"  GRAND TOTAL       : {grand_passed}/{grand_total}")
    if grand_passed == grand_total:
        print("  ✅ Safety floor validé.")
    else:
        print("  ❌ Safety floor pas encore stable.")
    print("=" * 60)

    sys.exit(0 if grand_passed == grand_total else 1)