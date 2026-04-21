"""
ClairDiag v2 — Task #006 Real-World Validator

Валідує 4 осі на кожен кейс:
  1. safety_behavior       — safety floor спрацьовує правильно
  2. danger_exclusion      — небезпечні стани не зникають
  3. test_selection_adequacy — потрібні тести присутні, заборонені відсутні
  4. output_coherence      — confidence і secondary_hypotheses адекватні

Тири результату:
  PASS          = всі 4 осі OK
  PARTIAL       = 1-2 некритичні осі провалились
  FAIL_CRITICAL = safety_behavior або danger_exclusion FAIL на high/critical кейсі

Використання:
  python run_tests_v2_real_world.py
  python run_tests_v2_real_world.py --verbose
  python run_tests_v2_real_world.py --category elderly_atypical
"""

import json
import argparse
import os
import sys

from medical_probability_engine import run_probability_engine
from test_recommendation_engine import run_recommendation_engine

# ──────────────────────────────────────────────
# PIPELINE
# ──────────────────────────────────────────────

def run_pipeline(payload: dict, base_dir: str) -> dict:
    v1_output = {
        "symptoms_normalized": payload.get("symptoms_normalized", []),
        "red_flags":           payload.get("red_flags", []),
        "final_action_v1":     payload.get("final_action_v1", "consult_doctor"),
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
# РАНЖУВАННЯ
# ──────────────────────────────────────────────

CONFIDENCE_RANK = {"faible": 1, "modéré": 2, "élevé": 3}
CRITICAL_RISK   = {"high", "critical"}
CRITICAL_AXES   = {"safety_behavior", "danger_exclusion"}

# ──────────────────────────────────────────────
# ВІС 1: SAFETY BEHAVIOR
# ──────────────────────────────────────────────

def eval_safety_behavior(result: dict, expected: dict) -> tuple:
    exp          = expected.get("safety_behavior", {})
    should       = exp.get("should_trigger")
    if should is None:
        return True, "no expectation"

    triggered = result.get("safety_floor", {}).get("triggered", False)
    if bool(triggered) == bool(should):
        return True, f"triggered={triggered} (attendu {should})"
    return False, f"triggered={triggered} mais attendu {should}"

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
# ВІС 2: DANGER EXCLUSION + TOP-N
# ──────────────────────────────────────────────

def eval_danger_exclusion(result: dict, expected: dict) -> tuple:
    exp        = expected.get("danger_exclusion", {})
    must_any   = exp.get("must_include_any_of", [])
    must_top_n = exp.get("must_be_in_top_n", 3)
    if not must_any:
        return True, "no expectation"

    top_n = get_top_n(result, must_top_n)
    hit   = any(m in top_n for m in must_any)
    if hit:
        matched = [m for m in must_any if m in top_n]
        return True, f"danger in TOP-{must_top_n}: {matched}"
    return False, (
        f"aucun de {must_any} dans TOP-{must_top_n}: {top_n} "
        f"(full exclude: {result.get('exclude_priority', [])})"
    )

# ──────────────────────────────────────────────
# ВІС 3: TEST SELECTION
# ──────────────────────────────────────────────

def eval_test_selection(result: dict, expected: dict) -> tuple:
    exp           = expected.get("test_selection_adequacy", {})
    mandatory_any = exp.get("mandatory_any_of", [])
    forbidden     = exp.get("forbidden", [])

    actual_tests = {t["test"] for t in result.get("recommended_tests", [])}

    for bad in forbidden:
        if bad in actual_tests:
            return False, f"test interdit '{bad}' recommandé"

    if mandatory_any:
        hit = any(m in actual_tests for m in mandatory_any)
        if not hit:
            return False, f"aucun de {mandatory_any} recommandé (obtenus: {sorted(actual_tests)})"

    return True, f"tests adéquats: {sorted(actual_tests)}"

# ──────────────────────────────────────────────
# ВІС 4: OUTPUT COHERENCE
# ──────────────────────────────────────────────

def eval_output_coherence(result: dict, expected: dict) -> tuple:
    exp      = expected.get("output_coherence", {})
    min_conf = exp.get("min_confidence_level")
    min_sec  = exp.get("min_secondary_count", 0)

    if min_conf:
        actual_conf = result.get("confidence_level", "faible")
        if CONFIDENCE_RANK.get(actual_conf, 0) < CONFIDENCE_RANK.get(min_conf, 0):
            return False, f"confidence={actual_conf} < attendu min {min_conf}"

    actual_sec = len(result.get("secondary_hypotheses", []))
    if actual_sec < min_sec:
        return False, f"secondary_hypotheses count={actual_sec} < attendu {min_sec}"

    return True, f"confidence={result.get('confidence_level')} secondary={actual_sec}"

# ──────────────────────────────────────────────
# SCORING
# ──────────────────────────────────────────────

AXIS_FUNCS = [
    ("safety_behavior",        eval_safety_behavior),
    ("danger_exclusion",       eval_danger_exclusion),
    ("test_selection_adequacy", eval_test_selection),
    ("output_coherence",       eval_output_coherence),
]

def score_case(case: dict, result: dict) -> dict:
    axis_results = {}
    for name, fn in AXIS_FUNCS:
        try:
            passed, reason = fn(result, case["expected"])
        except Exception as e:
            passed, reason = False, f"evaluator crash: {e!r}"
        axis_results[name] = {"passed": passed, "reason": reason}

    failed          = [a for a, r in axis_results.items() if not r["passed"]]
    critical_failed = [a for a in failed if a in CRITICAL_AXES]
    risk            = case.get("case_risk_level", "low")

    if not failed:
        tier = "PASS"
    elif critical_failed and risk in CRITICAL_RISK:
        tier = "FAIL_CRITICAL"
    else:
        tier = "PARTIAL"

    return {
        "case_id":      case["case_id"],
        "label":        case["label"],
        "category":     case.get("category", "?"),
        "risk":         risk,
        "tier":         tier,
        "failed_axes":  failed,
        "axis_results": axis_results,
        "result":       result,
    }

# ──────────────────────────────────────────────
# RUNNER
# ──────────────────────────────────────────────

TIER_ICON = {"PASS": "✅", "PARTIAL": "⚠️ ", "FAIL_CRITICAL": "❌"}

def run(verbose: bool = False, category_filter: str = None) -> int:
    base_dir   = os.path.dirname(os.path.abspath(__file__))
    tests_path = os.path.join(base_dir, "tests_v2_real_world.json")

    with open(tests_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    if category_filter:
        cases = [c for c in cases if c.get("category") == category_filter]

    scored = []
    for case in cases:
        try:
            result = run_pipeline(case["input_payload"], base_dir)
        except Exception as e:
            result = {
                "top_hypothesis": None, "secondary_hypotheses": [],
                "exclude_priority": [], "recommended_tests": [],
                "confidence_level": "faible", "safety_floor": {"triggered": False},
                "__engine_error__": repr(e),
            }
        scored.append(score_case(case, result))

    # ── Відображення ──
    print("=" * 68)
    print("  ClairDiag v2 — Task #006 Real-World Validation")
    print("=" * 68)

    by_cat: dict = {}
    for r in scored:
        by_cat.setdefault(r["category"], []).append(r)

    for cat, rows in by_cat.items():
        n_pass = sum(1 for r in rows if r["tier"] == "PASS")
        print(f"\n── {cat}  ({n_pass}/{len(rows)} PASS) ──")
        for r in rows:
            icon = TIER_ICON[r["tier"]]
            print(f"  [{r['case_id']}] {icon} {r['tier']:<14} risk={r['risk']:<8} {r['label']}")
            if r["failed_axes"]:
                for ax in r["failed_axes"]:
                    reason = r["axis_results"][ax]["reason"]
                    print(f"         └─ {ax}: {reason}")
            if verbose:
                res = r["result"]
                sf  = res.get("safety_floor", {})
                print(
                    f"         top={res.get('top_hypothesis')} "
                    f"secondary={res.get('secondary_hypotheses')} "
                    f"exclude={res.get('exclude_priority')}"
                )
                print(
                    f"         tests={[t['test'] for t in res.get('recommended_tests', [])]} "
                    f"floor={sf.get('triggered')} conf={res.get('confidence_level')}"
                )

    # ── Зведення ──
    total        = len(scored)
    n_pass       = sum(1 for r in scored if r["tier"] == "PASS")
    n_partial    = sum(1 for r in scored if r["tier"] == "PARTIAL")
    n_fail_crit  = sum(1 for r in scored if r["tier"] == "FAIL_CRITICAL")

    print("\n" + "=" * 68)
    print("  GLOBAL SUMMARY")
    print("=" * 68)
    print(f"  Total cases      : {total}")
    print(f"  ✅ PASS           : {n_pass}")
    print(f"  ⚠️  PARTIAL        : {n_partial}")
    print(f"  ❌ FAIL_CRITICAL  : {n_fail_crit}")

    if n_fail_crit > 0:
        print("\n  Critical failures (MUST fix before pilot):")
        for r in scored:
            if r["tier"] == "FAIL_CRITICAL":
                print(f"    - [{r['case_id']}] {r['label']} → failed: {', '.join(r['failed_axes'])}")
        print()
        print("  ❌ Real-world validation NOT passed — critical failures present.")
        print("=" * 68)
        return 1

    if n_partial > 0:
        print("\n  ⚠️  Real-world validation PARTIAL — no critical failures.")
    else:
        print("\n  ✅ Real-world validation PASSED — all cases clean.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ClairDiag v2 Real-World Validator")
    parser.add_argument("--verbose",  action="store_true")
    parser.add_argument("--category", type=str, default=None,
                        help="mixed_multisystem|conflicting_signals|sparse_data|elderly_atypical|safety_vs_probability")
    args = parser.parse_args()
    sys.exit(run(verbose=args.verbose, category_filter=args.category))