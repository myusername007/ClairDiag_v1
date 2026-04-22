"""
ClairDiag v2 — Physician Export Validator (TASK FINAL / BLOCK 4)
Checks clairdiag_outputs.json for completeness and consistency.

Usage:
    python validate_physician_export.py [path_to_clairdiag_outputs.json]
"""

import json
import sys
import os
from datetime import datetime, timezone

# ──────────────────────────────────────────────────────────────────────────────
# REQUIRED FIELDS
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_TOP = ["case_id", "label", "input_summary", "mapping_confidence",
                "clairdiag_output", "scope_status"]

REQUIRED_INPUT_SUMMARY = ["symptoms", "patient_framing", "context"]

REQUIRED_CLAIRDIAG = [
    "top_hypothesis", "alternatives", "urgency", "danger_zone",
    "recommended_tests", "confidence", "reasoning_short",
    "economic_impact", "context_flags", "context_alerts", "disclaimer",
]

REQUIRED_CONFIDENCE   = ["level", "score"]
REQUIRED_REASONING    = ["why_top1", "why_not_top1", "urgency_justification"]
REQUIRED_ECONOMIC     = ["consultation_avoided", "tests_avoided",
                         "tests_added", "estimated_cost_range"]

# ──────────────────────────────────────────────────────────────────────────────
# VALIDATOR
# ──────────────────────────────────────────────────────────────────────────────

def validate(path: str) -> dict:
    # Load JSON
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"fatal": f"JSON parse error: {e}"}

    meta  = data.get("meta", {})
    cases = data.get("cases", [])

    results   = []
    passed    = 0
    failed    = 0
    seen_ids  = {}

    for i, case in enumerate(cases):
        case_id = case.get("case_id", f"<missing_id_{i}>")
        errors  = []

        # Check 2: duplicate case_id
        if case_id in seen_ids:
            errors.append(f"DUPLICATE case_id (first seen at index {seen_ids[case_id]})")
        else:
            seen_ids[case_id] = i

        # Check 4: required top-level fields
        for f in REQUIRED_TOP:
            if f not in case:
                errors.append(f"MISSING top field: {f}")

        # Check input_summary fields
        inp = case.get("input_summary", {})
        if isinstance(inp, dict):
            for f in REQUIRED_INPUT_SUMMARY:
                if f not in inp:
                    errors.append(f"MISSING input_summary.{f}")

        # Check scope_status values
        ss = case.get("scope_status")
        if ss not in ("in_scope", "out_of_scope"):
            errors.append(f"INVALID scope_status: {ss!r}")

        # clairdiag_output checks
        co = case.get("clairdiag_output")
        if co is None:
            # Only allowed if engine_error present
            if not case.get("engine_error"):
                errors.append("clairdiag_output is null without engine_error")
        elif isinstance(co, dict):
            # Check 5+6+7+8: required clairdiag fields
            for f in REQUIRED_CLAIRDIAG:
                if f not in co:
                    errors.append(f"MISSING clairdiag_output.{f}")

            # confidence subfields
            conf = co.get("confidence", {})
            if isinstance(conf, dict):
                for f in REQUIRED_CONFIDENCE:
                    if f not in conf:
                        errors.append(f"MISSING confidence.{f}")

            # reasoning_short subfields
            rs = co.get("reasoning_short", {})
            if isinstance(rs, dict):
                for f in REQUIRED_REASONING:
                    if f not in rs:
                        errors.append(f"MISSING reasoning_short.{f}")

            # economic_impact subfields
            ei = co.get("economic_impact", {})
            if isinstance(ei, dict):
                for f in REQUIRED_ECONOMIC:
                    if f not in ei:
                        errors.append(f"MISSING economic_impact.{f}")

            # context_flags must be list
            if not isinstance(co.get("context_flags"), list):
                errors.append("context_flags must be a list")
            if not isinstance(co.get("context_alerts"), list):
                errors.append("context_alerts must be a list")

        status = "PASS" if not errors else "FAIL"
        if status == "PASS":
            passed += 1
        else:
            failed += 1

        results.append({
            "case_id": case_id,
            "status":  status,
            "errors":  errors,
        })

    # Check 1: total count vs meta
    meta_total = meta.get("total_cases", len(cases))
    count_match = len(cases) == meta_total

    # Check 3: no missing case_ids (all unique)
    duplicate_ids = [r["case_id"] for r in results if "DUPLICATE" in " ".join(r["errors"])]

    return {
        "meta_declared":   meta_total,
        "actual_count":    len(cases),
        "count_match":     count_match,
        "total_checked":   len(cases),
        "passed":          passed,
        "failed":          failed,
        "duplicate_ids":   duplicate_ids,
        "failed_cases":    [r for r in results if r["status"] == "FAIL"],
        "version":         meta.get("version", "unknown"),
        "export_type":     meta.get("export_type", "unknown"),
        "generated_at":    meta.get("generated_at", "unknown"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "clairdiag_outputs.json"
    )

    if not os.path.exists(path):
        print(f"ERROR: file not found: {path}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print("  ClairDiag v2 — Physician Export Validator")
    print(f"{'='*60}")
    print(f"  File: {path}\n")

    r = validate(path)

    if "fatal" in r:
        print(f"  FATAL: {r['fatal']}")
        sys.exit(1)

    print(f"  Version       : {r['version']}")
    print(f"  Export type   : {r['export_type']}")
    print(f"  Generated at  : {r['generated_at']}")
    print(f"\n  Total checked : {r['total_checked']}")
    print(f"  Meta declared : {r['meta_declared']}")
    print(f"  Count match   : {'✅' if r['count_match'] else '❌'}")
    print(f"\n  ✅ PASS        : {r['passed']}")
    print(f"  ❌ FAIL        : {r['failed']}")

    if r["duplicate_ids"]:
        print(f"\n  ⚠️  Duplicate IDs: {r['duplicate_ids']}")

    if r["failed_cases"]:
        print(f"\n  Failed cases:")
        for fc in r["failed_cases"]:
            print(f"    [{fc['case_id']}]")
            for e in fc["errors"]:
                print(f"      — {e}")

    overall = r["failed"] == 0 and r["count_match"] and not r["duplicate_ids"]
    print(f"\n{'='*60}")
    print(f"  RESULT: {'✅ READY FOR PHYSICIAN PACKAGE' if overall else '❌ NOT READY — fix errors above'}")
    print(f"{'='*60}\n")

    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()