"""
ClairDiag v2 — Task #008: Blind Adversarial Validation Runner

Перевіряє 4 осі:
  1. safety_behavior       — safety floor спрацьовує при правильних тригерах
  2. danger_exclusion      — небезпечні стани в TOP-N
  3. test_selection_adequacy — потрібні тести присутні
  4. output_coherence      — confidence і v2_status адекватні

Використання:
  python run_tests_v2_blind_adversarial.py
  python run_tests_v2_blind_adversarial.py --verbose
"""

import json
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from medical_probability_engine import run_probability_engine
from test_recommendation_engine import run_recommendation_engine

# ──────────────────────────────────────────────
# PIPELINE
# ──────────────────────────────────────────────

def run_pipeline(v1_input: dict) -> dict:
    v1_output = {
        "symptoms_normalized": v1_input.get("symptoms_normalized", []),
        "red_flags":           v1_input.get("red_flags", []),
        "final_action_v1":     v1_input.get("final_action_v1", "consult_doctor"),
    }
    etape1 = run_probability_engine(
        v1_output       = v1_output,
        conditions_path = os.path.join(SCRIPT_DIR, "conditions_master.json"),
        weights_path    = os.path.join(SCRIPT_DIR, "condition_weights.json"),
    )
    return run_recommendation_engine(
        etape1_output     = etape1,
        v1_output         = v1_output,
        conditions_path   = os.path.join(SCRIPT_DIR, "conditions_master.json"),
        tests_path        = os.path.join(SCRIPT_DIR, "tests_master.json"),
        differential_path = os.path.join(SCRIPT_DIR, "differential_rules.json"),
    )

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

TIER_ICON = {"PASS": "✅", "PARTIAL": "⚠️ ", "FAIL_CRITICAL": "❌"}
CONFIDENCE_RANK = {"faible": 1, "modéré": 2, "élevé": 3}


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


def get_test_keys(result: dict) -> list:
    """Список ключів recommended_tests."""
    return [t.get("test", "") for t in result.get("recommended_tests", [])]

# ──────────────────────────────────────────────
# AXIS 1: SAFETY
# ──────────────────────────────────────────────

def check_safety(case: dict, result: dict) -> dict:
    exp = case["expected"]["safety_behavior"]
    must_trigger = exp.get("must_trigger_safety_floor", False)

    sf = result.get("safety_floor", {})
    triggered = sf.get("triggered", False) if isinstance(sf, dict) else False

    issues = []
    if must_trigger and not triggered:
        issues.append("safety_floor NOT triggered (expected: True)")

    return {"pass": not issues, "reason": "; ".join(issues) or "OK", "triggered": triggered}

# ──────────────────────────────────────────────
# AXIS 2: DANGER EXCLUSION + TOP-N
# ──────────────────────────────────────────────

def check_danger(case: dict, result: dict) -> dict:
    exp = case["expected"]["danger_exclusion"]
    dangerous  = exp.get("dangerous_conditions", [])
    top_n_req  = exp.get("must_be_in_top_n", 3)
    forbidden_primary = exp.get("must_not_be_primary", [])

    top_n = get_top_n(result, top_n_req)
    top_h = result.get("top_hypothesis", "") or ""

    issues = []

    # Перевірка TOP-N (substring matching для гнучкості)
    if dangerous:
        found = any(
            any(d.lower() in c.lower() or c.lower() in d.lower() for c in top_n)
            for d in dangerous
        )
        if not found:
            issues.append(f"none of {dangerous} in TOP-{top_n_req}: {top_n}")

    # Перевірка forbidden primary
    for fp in forbidden_primary:
        if fp.lower() in top_h.lower() or top_h.lower() in fp.lower():
            issues.append(f"top_hypothesis='{top_h}' matches forbidden '{fp}'")

    return {
        "pass": not issues,
        "reason": "; ".join(issues) or "OK",
        "top_n": top_n,
        "top_hypothesis": top_h,
    }

# ──────────────────────────────────────────────
# AXIS 3: TEST SELECTION
# ──────────────────────────────────────────────

def check_tests(case: dict, result: dict) -> dict:
    exp = case["expected"]["test_selection_adequacy"]
    must_include = exp.get("must_include_category", [])

    test_keys = get_test_keys(result)
    test_str  = " ".join(test_keys).lower()

    issues = []

    if must_include and test_keys:
        found = any(cat.lower() in test_str for cat in must_include)
        if not found:
            issues.append(f"none of {must_include} found in tests: {test_keys}")
    elif must_include and not test_keys:
        # Якщо тестів немає зовсім — перевіряємо через safety floor
        sf = result.get("safety_floor", {})
        triggered = sf.get("triggered", False) if isinstance(sf, dict) else False
        v2_status = result.get("v2_status", "")
        if v2_status in ("no_input", "no_match", "tied_scores"):
            pass  # tied_scores → insufficient_data pipeline → тестів не буде, це OK
        elif not triggered:
            issues.append(f"no recommended_tests and safety_floor not triggered; expected: {must_include}")

    return {
        "pass": not issues,
        "reason": "; ".join(issues) or "OK",
        "tests": test_keys,
    }

# ──────────────────────────────────────────────
# AXIS 4: COHERENCE
# ──────────────────────────────────────────────

def check_coherence(case: dict, result: dict) -> dict:
    exp = case["expected"]["output_coherence"]
    allowed_conf   = exp.get("confidence_must_be", [])
    allowed_status = exp.get("v2_status_must_be", [])

    # Normalize до list
    if isinstance(allowed_status, str):
        allowed_status = [allowed_status]

    confidence = result.get("confidence_level", "")
    v2_status  = result.get("v2_status", "")

    issues = []

    if allowed_conf and confidence not in allowed_conf:
        issues.append(f"confidence='{confidence}' not in {allowed_conf}")

    if allowed_status and v2_status not in allowed_status:
        issues.append(f"v2_status='{v2_status}' not in {allowed_status}")

    return {
        "pass": not issues,
        "reason": "; ".join(issues) or "OK",
        "confidence": confidence,
        "v2_status": v2_status,
    }

# ──────────────────────────────────────────────
# SCORING
# ──────────────────────────────────────────────

def score_case(case: dict, result: dict) -> dict:
    axes = {
        "safety":    check_safety(case, result),
        "danger":    check_danger(case, result),
        "tests":     check_tests(case, result),
        "coherence": check_coherence(case, result),
    }
    failed = [ax for ax, r in axes.items() if not r["pass"]]
    must_trigger = case["expected"]["safety_behavior"].get("must_trigger_safety_floor", False)

    if ("safety" in failed and must_trigger) or "danger" in failed:
        tier = "FAIL_CRITICAL"
    elif failed:
        tier = "PARTIAL"
    else:
        tier = "PASS"

    return {
        "case_id":      case["case_id"],
        "label":        case["label"],
        "category":     case["category"],
        "tier":         tier,
        "failed_axes":  failed,
        "axis_results": axes,
        "result":       result,
    }

# ──────────────────────────────────────────────
# RUNNER
# ──────────────────────────────────────────────

def run(verbose: bool = False) -> int:
    tests_path = os.path.join(SCRIPT_DIR, "tests_v2_blind_adversarial.json")
    with open(tests_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scored = []
    for case in data["cases"]:
        v1_input = {k: v for k, v in case["v1_input"].items() if k != "patient_belief"}
        try:
            result = run_pipeline(v1_input)
        except Exception as e:
            result = {
                "top_hypothesis": None, "secondary_hypotheses": [],
                "exclude_priority": [], "recommended_tests": [],
                "confidence_level": "faible", "v2_status": "engine_error",
                "safety_floor": {"triggered": False},
                "__error__": repr(e),
            }
        scored.append(score_case(case, result))

    print("=" * 72)
    print("  ClairDiag v2 — Task #008: Blind Adversarial Validation")
    print("=" * 72)

    by_cat: dict = {}
    for r in scored:
        by_cat.setdefault(r["category"], []).append(r)

    for cat, rows in by_cat.items():
        n_pass = sum(1 for r in rows if r["tier"] == "PASS")
        print(f"\n── {cat}  ({n_pass}/{len(rows)} PASS) ──")
        for r in rows:
            icon = TIER_ICON[r["tier"]]
            print(f"  [{r['case_id']}] {icon} {r['tier']:<14}  {r['label']}")
            if r["failed_axes"]:
                for ax in r["failed_axes"]:
                    print(f"         └─ ❗ {ax}: {r['axis_results'][ax]['reason']}")
            if verbose:
                res = r["result"]
                sf  = res.get("safety_floor", {})
                print(f"         top_hypothesis   = {res.get('top_hypothesis')}")
                print(f"         secondary        = {res.get('secondary_hypotheses')}")
                print(f"         exclude_priority = {res.get('exclude_priority')}")
                print(f"         TOP-3            = {get_top_n(res)}")
                print(f"         confidence       = {res.get('confidence_level')}")
                print(f"         v2_status        = {res.get('v2_status')}")
                print(f"         safety_floor     = {sf.get('triggered', False) if isinstance(sf, dict) else False}")
                tests = get_test_keys(res)
                if tests:
                    print(f"         tests            = {tests}")

    total       = len(scored)
    n_pass      = sum(1 for r in scored if r["tier"] == "PASS")
    n_partial   = sum(1 for r in scored if r["tier"] == "PARTIAL")
    n_fail_crit = sum(1 for r in scored if r["tier"] == "FAIL_CRITICAL")

    print("\n" + "=" * 72)
    print("  GLOBAL SUMMARY")
    print("=" * 72)
    print(f"  Total cases       : {total}")
    print(f"  ✅ PASS            : {n_pass}")
    print(f"  ⚠️  PARTIAL         : {n_partial}")
    print(f"  ❌ FAIL_CRITICAL   : {n_fail_crit}")

    if n_fail_crit > 0:
        print("\n  Critical failures (MUST fix before pilot):")
        for r in scored:
            if r["tier"] == "FAIL_CRITICAL":
                print(f"    - [{r['case_id']}] {r['label']}")
                for ax in r["failed_axes"]:
                    print(f"      └─ {ax}: {r['axis_results'][ax]['reason']}")
        print()
        print("  ❌ Blind Adversarial validation NOT passed.")
        print("=" * 72)
        return 1

    if n_partial > 0:
        print("\n  ⚠️  Blind Adversarial validation PARTIAL — no critical failures.")
    else:
        print("\n  ✅ Blind Adversarial validation PASSED — all cases clean.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ClairDiag v2 — Blind Adversarial Runner")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    sys.exit(run(verbose=args.verbose))