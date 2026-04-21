"""
ClairDiag v2 — Reasoning Test Runner (Étape 2)

Використання:
  python run_tests_v2_reasoning.py
  python run_tests_v2_reasoning.py --verbose
  python run_tests_v2_reasoning.py --group urgent_parallel
"""

import json
import argparse
import os
import sys

from medical_probability_engine import run_probability_engine
from test_recommendation_engine import run_recommendation_engine


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

def evaluate_test(test: dict, base_dir: str) -> dict:
    expected  = test["expected"]
    failures  = []
    v1_output = test["input"]

    conditions_path   = os.path.join(base_dir, "conditions_master.json")
    weights_path      = os.path.join(base_dir, "condition_weights.json")
    tests_path        = os.path.join(base_dir, "tests_master.json")
    differential_path = os.path.join(base_dir, "differential_rules.json")

    etape1 = run_probability_engine(
        v1_output       = v1_output,
        conditions_path = conditions_path,
        weights_path    = weights_path,
    )

    result = run_recommendation_engine(
        etape1_output     = etape1,
        v1_output         = v1_output,
        conditions_path   = conditions_path,
        tests_path        = tests_path,
        differential_path = differential_path,
    )

    # ── top_hypothesis ──
    expected_top = expected.get("top_hypothesis")
    actual_top   = result.get("top_hypothesis")
    if expected_top != actual_top:
        failures.append(f"top_hypothesis: attendu '{expected_top}', obtenu '{actual_top}'")

    # ── exclude_priority + TOP-N ──
    must_top_n = expected.get("must_be_in_top_n", 3)
    top_n = get_top_n(result, must_top_n)
    for exc in expected.get("expected_exclude_includes", []):
        if exc not in top_n:
            failures.append(
                f"danger '{exc}' absent du TOP-{must_top_n} "
                f"(top_n actuel: {top_n})"
            )

    # ── first_test ──
    expected_first_test = expected.get("expected_first_test")
    actual_tests        = result.get("recommended_tests", [])
    actual_first_test   = actual_tests[0]["test"] if actual_tests else None
    if expected_first_test != actual_first_test:
        failures.append(
            f"first_test: attendu '{expected_first_test}', obtenu '{actual_first_test}'"
        )

    # ── logic_mode ──
    expected_logic = expected.get("expected_logic_mode")
    actual_logic   = result.get("next_step_logic")
    if expected_logic and actual_logic != expected_logic:
        failures.append(f"logic_mode: attendu '{expected_logic}', obtenu '{actual_logic}'")

    # ── orientation (contains check) ──
    expected_orient = expected.get("expected_orientation_includes", "")
    actual_orient   = result.get("medical_orientation_v2", "")
    if expected_orient and expected_orient not in actual_orient:
        failures.append(
            f"orientation: attendu contient '{expected_orient}', obtenu '{actual_orient}'"
        )

    return {
        "id":          test["id"],
        "group":       test["group"],
        "description": test["description"],
        "passed":      len(failures) == 0,
        "failures":    failures,
        "result":      result,
    }

# ──────────────────────────────────────────────
# RUNNER
# ──────────────────────────────────────────────

def run_all_tests(
    tests_path:   str,
    base_dir:     str,
    group_filter: str  = None,
    verbose:      bool = False,
) -> None:

    tests = load_tests(tests_path)
    if group_filter:
        tests = [t for t in tests if t["group"] == group_filter]

    total  = len(tests)
    passed = 0
    failed = 0
    results_by_group: dict = {}

    for test in tests:
        result = evaluate_test(test, base_dir)
        group  = result["group"]
        if group not in results_by_group:
            results_by_group[group] = []
        results_by_group[group].append(result)
        if result["passed"]:
            passed += 1
        else:
            failed += 1

    print("=" * 60)
    print("  ClairDiag v2 — Reasoning Test Report (Étape 2)")
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
                res = r["result"]
                tests_list = [t["test"] for t in res.get("recommended_tests", [])]
                print(
                    f"         top={res.get('top_hypothesis')} "
                    f"logic={res.get('next_step_logic')} "
                    f"orient={res.get('medical_orientation_v2')}"
                )
                print(f"         tests={tests_list}")
                print(f"         exclude={res.get('exclude_priority')}")
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
    parser = argparse.ArgumentParser(description="ClairDiag v2 Reasoning Test Runner")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--group", type=str, default=None,
        help="exclude_danger_first|confirm_top_first|urgent_parallel|low_confidence_differential|edge_cases"
    )
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))

    run_all_tests(
        tests_path   = os.path.join(base_dir, "tests_v2_reasoning.json"),
        base_dir     = base_dir,
        group_filter = args.group,
        verbose      = args.verbose,
    )