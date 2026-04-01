 #!/usr/bin/env python3
"""
ClairDiag — Auto Test Runner
Использование: python run_tests.py [--file tests/golden_cases.json] [--verbose]

Проверяет:
  • top1 совпадает с expected_top1
  • urgency совпадает с expected_urgency (LOW/HIGH → faible/élevé)
  • confidence не завышен (cap 0.55 при ≤2 симптомах)
  • tcs_level не нарушен
  • emergency_flag совпадает с expected_emergency
"""

import sys
import json
import argparse
import traceback
from pathlib import Path

# ── Импорт pipeline (запускается из корня проекта) ────────────────────────────
try:
    from app.pipeline import run as pipeline_run
    from app.models.schemas import AnalyzeRequest
except ImportError as e:
    print(f"[ERROR] Не удалось импортировать pipeline: {e}")
    print("  Запускай из корня проекта: python run_tests.py")
    sys.exit(1)

# ── Маппинг urgency: golden → pipeline ───────────────────────────────────────
URGENCY_MAP = {
    "LOW":  "faible",
    "HIGH": "élevé",
}

# ── Допустимые значения TCS ───────────────────────────────────────────────────
VALID_TCS = {"fort", "besoin_tests", "incertain"}

# ── Confidence cap при ≤2 симптомах ──────────────────────────────────────────
CONFIDENCE_CAP_THRESHOLD = 2
CONFIDENCE_CAP_VALUE = 0.55

CONFIDENCE_RANK = {
    "faible": 0,
    "modéré": 1,
    "élevé":  2,
}

CONFIDENCE_NUMERIC = {
    "élevé":  0.85,
    "modéré": 0.65,
    "faible": 0.35,
}

# ── Цвета терминала ───────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def ok(msg: str) -> str:
    return f"{GREEN}OK{RESET}  {msg}"


def fail(msg: str) -> str:
    return f"{RED}FAIL{RESET} {msg}"


def warn(msg: str) -> str:
    return f"{YELLOW}WARN{RESET} {msg}"


# ── Запуск одного кейса ───────────────────────────────────────────────────────

def run_case(case: dict, verbose: bool = False) -> dict:
    case_id   = case["id"]
    desc      = case.get("description", "")
    inp       = case["input"]
    exp_top1  = case.get("expected_top1")          # может быть null
    exp_urg   = case.get("expected_urgency", "LOW")
    exp_tcs   = case.get("expected_tcs", "incertain")
    exp_emerg = case.get("expected_emergency", False)

    results = []
    passed  = True

    try:
        request = AnalyzeRequest(
            symptoms=inp.get("symptoms", []),
            onset=inp.get("onset"),
            duration=inp.get("duration"),
        )
        resp = pipeline_run(request)
    except Exception as e:
        return {
            "id": case_id,
            "desc": desc,
            "passed": False,
            "results": [fail(f"EXCEPTION: {e}")],
            "trace": traceback.format_exc(),
        }

    sym_count = len(inp.get("symptoms", []))

    # ── Проверка 1: top1 ──────────────────────────────────────────────────────
    actual_top1 = resp.diagnoses[0].name if resp.diagnoses else None
    if exp_top1 is None:
        # Ожидаем пустой результат
        if actual_top1 is None:
            results.append(ok(f"top1=None (ожидалось None)"))
        else:
            results.append(warn(f"top1={actual_top1} (ожидалось None — возможно OK)"))
    else:
        if actual_top1 == exp_top1:
            results.append(ok(f"top1={actual_top1}"))
        else:
            results.append(fail(f"top1={actual_top1} (ожидалось: {exp_top1})"))
            passed = False

    # ── Проверка 2: urgency ───────────────────────────────────────────────────
    expected_urg_fr = URGENCY_MAP.get(exp_urg, exp_urg)
    actual_urg = resp.urgency_level
    if actual_urg == expected_urg_fr:
        results.append(ok(f"urgency={actual_urg}"))
    else:
        results.append(fail(f"urgency={actual_urg} (ожидалось: {expected_urg_fr})"))
        passed = False

    # ── Проверка 3: confidence не завышен (élevé при ≤2 симптомах = FAIL) ──────
    actual_conf_str = resp.confidence_level
    if sym_count <= CONFIDENCE_CAP_THRESHOLD:
        if CONFIDENCE_RANK.get(actual_conf_str, 0) >= CONFIDENCE_RANK["élevé"]:
            results.append(fail(
                f"confidence={actual_conf_str} ЗАВЫШЕН при симптомов={sym_count} "
                f"(макс допустимый: modéré)"
            ))
            passed = False
        else:
            results.append(ok(f"confidence={actual_conf_str} (≤{CONFIDENCE_CAP_THRESHOLD} симптомов, cap соблюдён)"))
    else:
        results.append(ok(f"confidence={actual_conf_str} (симптомов={sym_count})"))

    # ── Проверка 4: tcs_level ─────────────────────────────────────────────────
    actual_tcs = resp.tcs_level
    if actual_tcs not in VALID_TCS:
        results.append(fail(f"tcs={actual_tcs} — недопустимое значение"))
        passed = False
    elif actual_tcs == exp_tcs:
        results.append(ok(f"tcs={actual_tcs}"))
    else:
        # tcs — мягкая проверка: только fort→incertain это точно FAIL
        if exp_tcs == "fort" and actual_tcs != "fort":
            results.append(fail(f"tcs={actual_tcs} (ожидалось: {exp_tcs})"))
            passed = False
        elif exp_tcs == "incertain" and actual_tcs == "fort":
            results.append(fail(f"tcs={actual_tcs} (слишком высокий, ожидалось: {exp_tcs})"))
            passed = False
        else:
            results.append(warn(f"tcs={actual_tcs} (ожидалось: {exp_tcs}, допустимо)"))

    # ── Проверка 5: emergency_flag ────────────────────────────────────────────
    actual_emerg = resp.emergency_flag
    if actual_emerg == exp_emerg:
        results.append(ok(f"emergency={actual_emerg}"))
    else:
        results.append(fail(f"emergency={actual_emerg} (ожидалось: {exp_emerg})"))
        passed = False

    # ── Verbose: дополнительная информация ───────────────────────────────────
    if verbose:
        top3 = [(d.name, d.probability) for d in resp.diagnoses]
        results.append(f"      diagnoses={top3}")
        results.append(f"      sgl_warnings={resp.sgl_warnings}")
        if case.get("notes"):
            results.append(f"      notes: {case['notes']}")

    return {
        "id": case_id,
        "desc": desc,
        "passed": passed,
        "results": results,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ClairDiag Test Runner")
    parser.add_argument(
        "--file", default="tests/golden_cases.json",
        help="Путь к golden_cases.json"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Показывать детали по каждому кейсу"
    )
    parser.add_argument(
        "--filter", "-f", default=None,
        help="Фильтр по префиксу ID (HP/BC/SF)"
    )
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"[ERROR] Файл не найден: {path}")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("cases", [])
    if args.filter:
        cases = [c for c in cases if c["id"].startswith(args.filter)]

    total  = len(cases)
    passed = 0
    failed = 0
    warns  = 0

    print(f"\n{BOLD}═══ ClairDiag Test Runner ═══{RESET}")
    print(f"Файл:   {path}")
    print(f"Кейсов: {total}")
    if args.filter:
        print(f"Фильтр: {args.filter}")
    print()

    fail_ids = []

    for case in cases:
        result = run_case(case, verbose=args.verbose)
        status = f"{GREEN}✓ OK  {RESET}" if result["passed"] else f"{RED}✗ FAIL{RESET}"
        print(f"  {status} [{result['id']}] {result['desc']}")

        if not result["passed"]:
            failed += 1
            fail_ids.append(result["id"])
            for line in result["results"]:
                if "FAIL" in line or "EXCEPTION" in line:
                    print(f"         {line}")
        else:
            passed += 1
            if args.verbose:
                for line in result["results"]:
                    print(f"         {line}")

        if args.verbose and not result["passed"]:
            for line in result["results"]:
                print(f"         {line}")

        if "trace" in result:
            print(result["trace"])

    # ── Итог ─────────────────────────────────────────────────────────────────
    print()
    print(f"{BOLD}═══ ИТОГ ═══{RESET}")
    print(f"  Всего:   {total}")
    print(f"  {GREEN}Прошли:  {passed}{RESET}")
    print(f"  {RED}Упали:   {failed}{RESET}")

    if fail_ids:
        print(f"\n  Упавшие кейсы: {', '.join(fail_ids)}")

    pass_rate = (passed / total * 100) if total else 0
    print(f"\n  Pass rate: {pass_rate:.1f}%")

    if pass_rate == 100:
        print(f"\n  {GREEN}{BOLD}✓ Все тесты прошли{RESET}")
    elif pass_rate >= 80:
        print(f"\n  {YELLOW}{BOLD}⚠ Есть проблемы — требуется ревизия{RESET}")
    else:
        print(f"\n  {RED}{BOLD}✗ Критические ошибки — нужен откат или фикс{RESET}")

    print()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()