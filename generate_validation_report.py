#!/usr/bin/env python3
"""
generate_validation_report.py
Генерує звіт після будь-якого пакету тестів.

Використання:
  python generate_validation_report.py --results tests/results/stress_100_results.json
  python generate_validation_report.py --results tests/results/gold_30_results.json --output reports/
"""

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def load_results(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # Підтримуємо обидва формати: список або {"results": [...]}
    if isinstance(data, list):
        return data
    return data.get("results", data.get("cases", []))


def analyze(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "PASS")
    failed = sum(1 for r in results if r.get("status") == "FAIL")
    critical = sum(1 for r in results if r.get("critical", False) or r.get("status") == "CRITICAL")

    # По зонах (якщо є поле zone/category)
    by_zone: dict[str, dict] = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0})
    for r in results:
        zone = r.get("zone") or r.get("category") or r.get("type") or "unknown"
        by_zone[zone]["total"] += 1
        if r.get("status") == "PASS":
            by_zone[zone]["pass"] += 1
        else:
            by_zone[zone]["fail"] += 1

    # По severity
    by_severity: dict[str, dict] = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0})
    for r in results:
        sev = r.get("severity") or r.get("urgency") or "unknown"
        by_severity[sev]["total"] += 1
        if r.get("status") == "PASS":
            by_severity[sev]["pass"] += 1
        else:
            by_severity[sev]["fail"] += 1

    # Top fail reasons
    fail_reasons: list[str] = []
    for r in results:
        if r.get("status") != "PASS":
            reason = r.get("fail_reason") or r.get("reason") or r.get("note") or ""
            if reason:
                fail_reasons.append(reason)
    top_fail_reasons = Counter(fail_reasons).most_common(5)

    # Top unstable diagnoses (діагнози що часто зустрічаються у fail)
    unstable_diag: list[str] = []
    for r in results:
        if r.get("status") != "PASS":
            diag = r.get("expected") or r.get("top1") or ""
            if diag:
                unstable_diag.append(diag)
    top_unstable_diagnoses = Counter(unstable_diag).most_common(5)

    # Top unstable tests (тести що часто у fail)
    unstable_tests: list[str] = []
    for r in results:
        if r.get("status") != "PASS":
            tests = r.get("required_tests") or r.get("tests") or []
            unstable_tests.extend(tests if isinstance(tests, list) else [tests])
    top_unstable_tests = Counter(unstable_tests).most_common(5)

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "critical": critical,
        "pass_rate": f"{round(passed / total * 100, 1)}%" if total else "0%",
        "by_zone": dict(by_zone),
        "by_severity": dict(by_severity),
        "top_fail_reasons": top_fail_reasons,
        "top_unstable_diagnoses": top_unstable_diagnoses,
        "top_unstable_tests": top_unstable_tests,
        "failed_cases": [
            {
                "id": r.get("id") or r.get("case_id") or "?",
                "symptoms": r.get("symptoms") or [],
                "expected": r.get("expected") or "",
                "got": r.get("got") or r.get("top1") or "",
                "reason": r.get("fail_reason") or r.get("reason") or "",
            }
            for r in results
            if r.get("status") != "PASS"
        ][:20],  # максимум 20
    }


def render_text(stats: dict, source_file: str, pack_name: str) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "=" * 60,
        f"CLAIRDIAG — VALIDATION REPORT",
        f"Pack   : {pack_name}",
        f"Source : {source_file}",
        f"Date   : {ts}",
        "=" * 60,
        "",
        "── SUMMARY ──────────────────────────────────────────────",
        f"  Total   : {stats['total']}",
        f"  PASS    : {stats['passed']}  ({stats['pass_rate']})",
        f"  FAIL    : {stats['failed']}",
        f"  CRITICAL: {stats['critical']}",
        "",
    ]

    if stats["by_zone"]:
        lines.append("── BY ZONE ──────────────────────────────────────────────")
        for zone, z in sorted(stats["by_zone"].items()):
            rate = round(z["pass"] / z["total"] * 100) if z["total"] else 0
            lines.append(f"  {zone:<20} {z['pass']}/{z['total']} ({rate}%)")
        lines.append("")

    if stats["by_severity"]:
        lines.append("── BY SEVERITY ──────────────────────────────────────────")
        for sev, s in sorted(stats["by_severity"].items()):
            rate = round(s["pass"] / s["total"] * 100) if s["total"] else 0
            lines.append(f"  {sev:<20} {s['pass']}/{s['total']} ({rate}%)")
        lines.append("")

    if stats["top_fail_reasons"]:
        lines.append("── TOP FAIL REASONS ─────────────────────────────────────")
        for reason, count in stats["top_fail_reasons"]:
            lines.append(f"  ({count}x) {reason}")
        lines.append("")

    if stats["top_unstable_diagnoses"]:
        lines.append("── TOP UNSTABLE DIAGNOSES ───────────────────────────────")
        for diag, count in stats["top_unstable_diagnoses"]:
            lines.append(f"  ({count}x) {diag}")
        lines.append("")

    if stats["top_unstable_tests"]:
        lines.append("── TOP UNSTABLE TESTS ───────────────────────────────────")
        for test, count in stats["top_unstable_tests"]:
            lines.append(f"  ({count}x) {test}")
        lines.append("")

    if stats["failed_cases"]:
        lines.append("── FAILED CASES (max 20) ────────────────────────────────")
        for fc in stats["failed_cases"]:
            lines.append(f"  [{fc['id']}] expected={fc['expected']} got={fc['got']}")
            if fc.get("reason"):
                lines.append(f"    reason: {fc['reason']}")
            if fc.get("symptoms"):
                lines.append(f"    symptoms: {', '.join(fc['symptoms'][:5])}")
        lines.append("")

    verdict = "✅ ALL PASS" if stats["failed"] == 0 else f"❌ {stats['failed']} FAILURES"
    if stats["critical"] > 0:
        verdict += f" | 🚨 {stats['critical']} CRITICAL"
    lines += ["=" * 60, f"  VERDICT: {verdict}", "=" * 60]

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="ClairDiag Validation Report Generator")
    parser.add_argument("--results", required=True, help="Path to results JSON file")
    parser.add_argument("--output", default=".", help="Output directory for report")
    parser.add_argument("--pack", default=None, help="Pack name (auto-detected if not set)")
    parser.add_argument("--json", action="store_true", help="Also save JSON report")
    args = parser.parse_args()

    results = load_results(args.results)
    stats = analyze(results)

    pack_name = args.pack or Path(args.results).stem
    report_text = render_text(stats, args.results, pack_name)

    print(report_text)

    # Save text report
    os.makedirs(args.output, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    report_path = os.path.join(args.output, f"report_{pack_name}_{ts}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\nReport saved: {report_path}")

    if args.json:
        json_path = os.path.join(args.output, f"report_{pack_name}_{ts}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"pack": pack_name, "stats": stats}, f, ensure_ascii=False, indent=2)
        print(f"JSON saved: {json_path}")

    # Exit code: 0 if all pass, 1 if failures, 2 if critical
    if stats["critical"] > 0:
        raise SystemExit(2)
    if stats["failed"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()