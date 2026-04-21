"""
ClairDiag v2 — Test Runner

Використання:
  python run_tests_v2.py
  python run_tests_v2.py --verbose
  python run_tests_v2.py --group digestif
"""

import json
import argparse
import os
import sys

from medical_probability_engine import run_probability_engine, load_conditions
from output_formatter_v2 import format_for_test


def get_top_n(result: dict, n: int = 3) -> list:
    """TOP-N = top_hypothesis + secondary_hypotheses + exclude_priority (дедупліковано)."""
    pool = []
    if result.get("top_hypothesis"):
        pool.append(result["top_hypothesis"])
    pool.extend(result.get("secondary_hypotheses", []))
    pool.extend(result.get("exclude_priority", []))
    seen, out = set(), []
    for item in pool:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out[:n]

# ──────────────────────────────────────────────
# CHARGEMENT
# ──────────────────────────────────────────────

def load_tests(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["tests"]

# ──────────────────────────────────────────────
# ÉVALUATION
# ──────────────────────────────────────────────

def evaluate_test(test: dict, conditions_path: str, weights_path: str) -> dict:
    expected = test["expected"]
    failures = []

    raw    = run_probability_engine(
        v1_output       = test["input"],
        conditions_path = conditions_path,
        weights_path    = weights_path,
    )
    result = format_for_test(raw)

    expected_top = expected.get("top_hypothesis")
    if expected_top and result["top"] != expected_top:
        failures.append(
            f"top_hypothesis: attendu '{expected_top}', obtenu '{result['top']}'"
        )

    for s in expected.get("secondary_hypotheses_includes", []):
        if s not in raw.get("secondary_hypotheses", []):
            failures.append(f"secondary manquant: '{s}' (obtenu: {raw.get('secondary_hypotheses')})")

    expected_conf = expected.get("confidence_level")
    if expected_conf and result["confidence"] != expected_conf:
        failures.append(
            f"confidence_level: attendu '{expected_conf}', obtenu '{result['confidence']}'"
        )

    must_top_n = expected.get("must_be_in_top_n", 3)
    top_n = get_top_n(raw, must_top_n)
    for e in expected.get("exclude_priority_includes", []):
        if e not in top_n:
            failures.append(
                f"danger '{e}' absent du TOP-{must_top_n} "
                f"(top_n actuel: {top_n})"
            )

    return {
        "id":          test["id"],
        "group":       test["group"],
        "description": test["description"],
        "passed":      len(failures) == 0,
        "failures":    failures,
        "raw_output":  raw,
    }

# ──────────────────────────────────────────────
# RUNNER
# ──────────────────────────────────────────────

def run_all_tests(
    tests_path: str,
    conditions_path: str,
    weights_path: str,
    group_filter: str = None,
    verbose: bool = False,
) -> None:
    tests = load_tests(tests_path)
    if group_filter:
        tests = [t for t in tests if t["group"] == group_filter]

    total  = len(tests)
    passed = 0
    failed = 0
    results_by_group = {}

    for test in tests:
        result = evaluate_test(test, conditions_path, weights_path)
        group  = result["group"]

        if group not in results_by_group:
            results_by_group[group] = []
        results_by_group[group].append(result)

        if result["passed"]:
            passed += 1
        else:
            failed += 1

    print("=" * 60)
    print("  ClairDiag v2 — Test Report")
    print("=" * 60)
    print()

    for group, group_results in results_by_group.items():
        group_pass = sum(1 for r in group_results if r["passed"])
        print(f"📁 {group.upper()} — {group_pass}/{len(group_results)} passed")
        print("-" * 50)

        for r in group_results:
            status = "✅ PASS" if r["passed"] else "❌ FAIL"
            print(f"  [{r['id']}] {status}  {r['description']}")

            if not r["passed"]:
                for f in r["failures"]:
                    print(f"         ⚠ {f}")

            if verbose:
                raw = r["raw_output"]
                print(
                    f"         top={raw.get('top_hypothesis')} "
                    f"conf={raw.get('confidence_level')} "
                    f"secondary={raw.get('secondary_hypotheses')} "
                    f"exclude={raw.get('exclude_priority')}"
                )
        print()

    print("=" * 60)
    pct = round(passed / total * 100) if total > 0 else 0
    print(f"  TOTAL: {passed}/{total} passed ({pct}%)")

    if failed == 0:
        print("  🏆 Tous les tests sont passés !")
    else:
        print(f"  🔴 {failed} test(s) en échec")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ClairDiag v2 Test Runner")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--group",   type=str, default=None,
                        help="digestif|cardiaque|neurologique|respiratoire|infectieux")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))

    run_all_tests(
        tests_path      = os.path.join(base_dir, "tests_v2_conditions.json"),
        conditions_path = os.path.join(base_dir, "conditions_master.json"),
        weights_path    = os.path.join(base_dir, "condition_weights.json"),
        group_filter    = args.group,
        verbose         = args.verbose,
    )