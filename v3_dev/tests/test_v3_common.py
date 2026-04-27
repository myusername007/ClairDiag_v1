"""
ClairDiag v3 — Test Runner
20 кейсів: покриває всі категорії + urgent override + v2 priority.

Запуск:
  cd <project_root>
  python -m pytest v3/tests/test_v3_common.py -v
  або
  python v3/tests/test_v3_common.py
"""

import os
import sys

# ── path setup ────────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from common_symptom_mapper import common_symptom_mapper
from medical_normalizer_v3 import normalize_to_medical_tokens
from general_orientation_router import general_orientation_router, fallback_orientation
from clinical_combinations_engine import match_combination
from v3_confidence_engine import compute_v3_confidence

# ── Test cases ────────────────────────────────────────────────────────────────

TEST_CASES = [
    # --- Категорії ---
    {
        "id": "V3-001",
        "free_text": "J'ai des boutons et des rougeurs sur les joues depuis deux mois.",
        "expected_category": "dermatologie_simple",
        "expect_urgent": False,
    },
    {
        "id": "V3-002",
        "free_text": "Je suis fatiguée, j'ai pris du poids, j'ai la peau sèche.",
        "expected_category": "metabolique_hormonal_suspect",
        "expect_urgent": False,
    },
    {
        "id": "V3-003",
        "free_text": "J'ai mal à la gorge, le nez bouché et je tousse un peu.",
        "expected_category": "orl_simple",
        "expect_urgent": False,
    },
    {
        "id": "V3-004",
        "free_text": "J'ai des ballonnements et de la constipation depuis plusieurs semaines.",
        "expected_category": "digestif_simple",
        "expect_urgent": False,
    },
    {
        "id": "V3-005",
        "free_text": "J'ai mal au dos et à la jambe depuis quelques jours.",
        "expected_category": "musculo_squelettique",
        "expect_urgent": False,
    },
    {
        "id": "V3-006",
        "free_text": "J'ai des brûlures urinaires et envie d'uriner souvent.",
        "expected_category": "urinaire",
        "expect_urgent": False,
    },
    {
        "id": "V3-007",
        "free_text": "J'ai des règles irrégulières et des douleurs pelviennes légères.",
        "expected_category": "gynecologique_simple",
        "expect_urgent": False,
    },
    {
        "id": "V3-008",
        "free_text": "Je dors mal, je suis stressé et fatigué.",
        "expected_category": "sommeil_stress_anxiete",
        "expect_urgent": False,
    },
    {
        "id": "V3-009",
        "free_text": "Je ne me sens pas bien depuis plusieurs jours, je suis vaseux.",
        "expected_category": "fatigue_asthenie",  # vaseux → fatigue wins over vague
        "expect_urgent": False,
    },
    # --- Urgent override ---
    {
        "id": "V3-010",
        "free_text": "J'ai mal à la poitrine avec des sueurs froides.",
        "expected_category": None,
        "expect_urgent": True,
    },
    {
        "id": "V3-011",
        "free_text": "J'ai une difficulté à respirer depuis ce matin.",
        "expected_category": None,
        "expect_urgent": True,
    },
    {
        "id": "V3-012",
        "free_text": "J'ai des idées suicidaires.",
        "expected_category": None,
        "expect_urgent": True,
    },
    {
        "id": "V3-013",
        "free_text": "J'ai perdu connaissance il y a une heure.",
        "expected_category": None,
        "expect_urgent": True,
    },
    # --- Negation (не має спрацювати) ---
    {
        "id": "V3-014",
        "free_text": "Je n'ai pas de fièvre, mais je suis fatigué.",
        "expected_category": "fatigue_asthenie",
        "expect_urgent": False,
    },
    # --- ORL + ознаки загальної слабкості ---
    {
        "id": "V3-015",
        "free_text": "Nez qui coule, gorge irritée, je tousse depuis hier.",
        "expected_category": "orl_simple",
        "expect_urgent": False,
    },
    # --- Шкіра: eczéma ---
    {
        "id": "V3-016",
        "free_text": "J'ai de l'eczéma et ça gratte beaucoup.",
        "expected_category": "dermatologie_simple",
        "expect_urgent": False,
    },
    # --- Digestif: nausées + vomissements ---
    {
        "id": "V3-017",
        "free_text": "J'ai des nausées et des vomissements depuis 2 jours.",
        "expected_category": "digestif_simple",
        "expect_urgent": False,
    },
    # --- Стрес без сну ---
    {
        "id": "V3-018",
        "free_text": "Je suis très stressée et je n'arrive pas à dormir.",
        "expected_category": "sommeil_stress_anxiete",
        "expect_urgent": False,
    },
    # --- Метаболічний: chute de cheveux + frilosité ---
    {
        "id": "V3-019",
        "free_text": "J'ai une chute de cheveux et j'ai toujours froid.",
        "expected_category": "metabolique_hormonal_suspect",
        "expect_urgent": False,
    },
    # --- Сечовивідний: cystite ---
    {
        "id": "V3-020",
        "free_text": "Je pense avoir une cystite, ça brûle quand j'urine.",
        "expected_category": "urinaire",
        "expect_urgent": False,
    },
]

# ── Runner ────────────────────────────────────────────────────────────────────

def run_tests():
    passed = 0
    failed = 0
    results = []

    for case in TEST_CASES:
        cid = case["id"]
        text = case["free_text"]
        expected_cat = case["expected_category"]
        expect_urgent = case["expect_urgent"]

        mapped = common_symptom_mapper(text)
        got_urgent = mapped.get("urgent_trigger") is not None
        got_cat = mapped.get("category")

        if expect_urgent:
            ok = got_urgent
        else:
            ok = (not got_urgent) and (got_cat == expected_cat)

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        results.append({
            "id": cid,
            "status": status,
            "expected": f"urgent={expect_urgent}, cat={expected_cat}",
            "got": f"urgent={got_urgent}, cat={got_cat}",
            "text_preview": text[:60],
        })

    # ── Output ────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"ClairDiag v3 — Test Report")
    print(f"{'='*60}")
    for r in results:
        mark = "✅" if r["status"] == "PASS" else "❌"
        print(f"{mark} [{r['id']}] {r['text_preview']}")
        if r["status"] == "FAIL":
            print(f"     expected: {r['expected']}")
            print(f"     got:      {r['got']}")
    print(f"{'='*60}")
    print(f"РЕЗУЛЬТАТ: {passed}/{len(TEST_CASES)} passed, {failed} failed")
    print(f"{'='*60}\n")

    return passed, failed


# ── Pytest compatibility ──────────────────────────────────────────────────────

def test_v3_all_cases():
    """Pytest entry point."""
    passed, failed = run_tests()
    assert failed == 0, f"{failed} test(s) failed — see output above"


if __name__ == "__main__":
    run_tests()