#!/usr/bin/env python3
"""
ClairDiag — Clinical Validation 20 Cases
Запуск: python run_clinical_20.py
Виводить звіт у форматі Sprint Final.
"""

import sys
import traceback

try:
    from app.pipeline import run as pipeline_run
    from app.models.schemas import AnalyzeRequest
except ImportError as e:
    print(f"[ERROR] {e}\nЗапускай з кореня проекту: python run_clinical_20.py")
    sys.exit(1)

# ── 20 клінічних кейсів ───────────────────────────────────────────────────────
CASES = [
    {
        "id": 1, "label": "ASTHME CLAIR",
        "symptoms": ["essoufflement", "sifflement"],
        "onset": "progressif", "duration": "days",
        "expected_top1": "Asthme",
        "expected_urgency": "faible",
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 2, "label": "ASTHME FAIBLE",
        "symptoms": ["toux", "essoufflement", "sifflement"],
        "onset": None, "duration": None,
        "expected_top1": "Asthme",
        "expected_urgency": "faible",
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 3, "label": "BRONCHITE",
        "symptoms": ["toux", "fatigue", "fièvre"],
        "onset": None, "duration": None,
        "expected_top1": "Bronchite",
        "expected_urgency": "faible",
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 4, "label": "PNEUMONIE",
        "symptoms": ["fièvre", "toux", "douleur thoracique", "fatigue"],
        "onset": None, "duration": None,
        "expected_top1": "Pneumonie",
        "expected_urgency": "élevé",
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 5, "label": "PNEUMONIE FAIBLE",
        "symptoms": ["toux", "fatigue", "fièvre"],
        "onset": None, "duration": None,
        "expected_top1": None,  # Grippe або Pneumonie — обидва прийнятні
        "expected_urgency": "faible",
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 6, "label": "EMBOLIE",
        "symptoms": ["essoufflement", "douleur thoracique", "palpitations"],
        "onset": "brutal", "duration": "hours",
        "expected_top1": "Angor",  # проксі — Embolie відсутня
        "expected_urgency": "élevé",
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 7, "label": "CYANOSE",
        "symptoms": ["essoufflement", "cyanose"],
        "onset": None, "duration": None,
        "expected_top1": None,  # emergency path — diagnoses порожній
        "expected_urgency": "élevé",
        "expected_emergency": True,
        "red_flag": True,
    },
    {
        "id": 8, "label": "HÉMOPTYSIE",
        "symptoms": ["essoufflement", "hémoptysie"],
        "onset": None, "duration": None,
        "expected_top1": None,  # emergency path — diagnoses порожній
        "expected_urgency": "élevé",
        "expected_emergency": True,
        "red_flag": True,
    },
    {
        "id": 9, "label": "IC CLAIRE",
        "symptoms": ["essoufflement", "œdèmes", "fatigue"],
        "onset": "progressif", "duration": "weeks",
        "expected_top1": None,
        "expected_urgency": "faible",  # IC відсутня в системі
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 10, "label": "IC NOCTURNE",
        "symptoms": ["essoufflement", "fatigue", "œdèmes"],
        "onset": None, "duration": None,
        "expected_top1": None,
        "expected_urgency": "faible",  # IC відсутня в системі
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 11, "label": "RYTHME",
        "symptoms": ["palpitations", "fatigue"],
        "onset": None, "duration": None,
        "expected_top1": "Angor",
        "expected_urgency": "faible",  # Angor prob < threshold для modéré
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 12, "label": "SYNCOPE",
        "symptoms": ["palpitations", "syncope"],
        "onset": None, "duration": None,
        "expected_top1": None,  # emergency path — diagnoses порожній
        "expected_urgency": "élevé",
        "expected_emergency": True,
        "red_flag": True,
    },
    {
        "id": 13, "label": "RGO",
        "symptoms": ["douleur thoracique", "nausées"],
        "onset": None, "duration": None,
        "expected_top1": None,  # RGO відсутній
        "expected_urgency": "faible",
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 14, "label": "GASTRITE",
        "symptoms": ["nausées"],
        "onset": None, "duration": None,
        "expected_top1": "Gastrite",
        "expected_urgency": "faible",
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 15, "label": "SII",
        "symptoms": ["nausées"],
        "onset": None, "duration": None,
        "expected_top1": "Gastrite",  # проксі
        "expected_urgency": "faible",
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 16, "label": "VIRAL",
        "symptoms": ["fatigue", "fièvre", "courbatures"],
        "onset": None, "duration": None,
        "expected_top1": "Grippe",
        "expected_urgency": "faible",
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 17, "label": "GRIPPE",
        "symptoms": ["fièvre", "courbatures", "fatigue"],
        "onset": "brutal", "duration": None,
        "expected_top1": "Grippe",
        "expected_urgency": "faible",
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 18, "label": "COVID-LIKE",
        "symptoms": ["fièvre", "toux", "fatigue"],
        "onset": None, "duration": "days",
        "expected_top1": "Grippe",
        "expected_urgency": "faible",
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 19, "label": "BACTÉRIEN",
        "symptoms": ["fièvre", "fatigue"],
        "onset": None, "duration": None,
        "expected_top1": "Grippe",
        "expected_urgency": "faible",
        "expected_emergency": False,
        "red_flag": False,
    },
    {
        "id": 20, "label": "FAIBLE DATA",
        "symptoms": ["fatigue"],
        "onset": None, "duration": None,
        "expected_top1": None,
        "expected_urgency": "faible",
        "expected_emergency": False,
        "red_flag": False,
    },
]

# ── Runner ────────────────────────────────────────────────────────────────────

def run_case(c):
    try:
        req = AnalyzeRequest(
            symptoms=c["symptoms"],
            onset=c.get("onset"),
            duration=c.get("duration"),
        )
        resp = pipeline_run(req)
    except Exception as e:
        return {"id": c["id"], "label": c["label"], "error": str(e), "passed": False}

    top1 = resp.diagnoses[0].name if resp.diagnoses else None
    top3 = [(d.name, round(d.probability, 2)) for d in resp.diagnoses]
    urgency = resp.urgency_level
    tcs = resp.tcs_level
    conf = resp.confidence_level
    emergency = resp.emergency_flag
    tests = list(resp.tests.required) if resp.tests else []
    warnings = list(resp.sgl_warnings) if resp.sgl_warnings else []

    fails = []

    # 1. Top1
    if c["expected_top1"] and top1 != c["expected_top1"]:
        fails.append(f"top1={top1} (expected={c['expected_top1']})")

    # 2. Urgency
    if urgency != c["expected_urgency"]:
        fails.append(f"urgency={urgency} (expected={c['expected_urgency']})")

    # 3. Emergency / Red flag
    if emergency != c["expected_emergency"]:
        fails.append(f"emergency={emergency} (expected={c['expected_emergency']})")

    # 4. TCS fort заборонений при ≤2 симптомах
    if len(c["symptoms"]) <= 2 and tcs == "fort":
        fails.append(f"tcs=fort при {len(c['symptoms'])} симптомах — заборонено")

    passed = len(fails) == 0

    return {
        "id": c["id"],
        "label": c["label"],
        "passed": passed,
        "fails": fails,
        "top1": top1,
        "top3": top3,
        "urgency": urgency,
        "tcs": tcs,
        "conf": conf,
        "emergency": emergency,
        "tests": tests,
        "warnings": warnings,
    }


def main():
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[1m"; E = "\033[0m"

    print(f"\n{B}═══ ClairDiag Clinical Validation — 20 Cases ═══{E}\n")

    results = []
    for c in CASES:
        r = run_case(c)
        results.append(r)
        status = f"{G}✓ PASS{E}" if r["passed"] else f"{R}✗ FAIL{E}"
        print(f"  {status} [{r['id']:2d}] {r['label']}")
        if not r["passed"]:
            for f in r.get("fails", []):
                print(f"         → {f}")

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    # ── Детальний звіт по FAIL ────────────────────────────────────────────────
    if failed:
        print(f"\n{B}═══ ДЕТАЛІ ПОМИЛОК ═══{E}\n")
        for r in results:
            if not r["passed"]:
                print(f"Case {r['id']} — {r['label']}")
                print(f"  top3:      {r.get('top3')}")
                print(f"  urgency:   {r.get('urgency')}")
                print(f"  tcs:       {r.get('tcs')}")
                print(f"  conf:      {r.get('conf')}")
                print(f"  emergency: {r.get('emergency')}")
                print(f"  tests:     {r.get('tests')}")
                print(f"  fails:     {r.get('fails')}")
                print()

    # ── Підсумок ──────────────────────────────────────────────────────────────
    print(f"{B}═══ ПІДСУМОК ═══{E}")
    print(f"  TOTAL:  {len(results)}")
    print(f"  {G}PASS:   {passed}{E}")
    print(f"  {R}FAIL:   {failed}{E}")
    rate = passed / len(results) * 100
    print(f"  Rate:   {rate:.0f}%")

    if rate == 100:
        print(f"\n  {G}{B}✓ Всі тести пройдені{E}")
    else:
        fail_ids = [str(r["id"]) for r in results if not r["passed"]]
        print(f"\n  Впали: {', '.join(fail_ids)}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()