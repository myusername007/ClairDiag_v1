# ── Cost Engine — Economic Layer ─────────────────────────────────────────────
# Джерело цін: TEST_CATALOG з app/data/tests.py — не дублювати.
# Функції: optimized_cost, standard_cost, savings

from app.data.tests import TEST_COSTS, CONSULTATION_COST

# Стандартні аналізи що завжди призначаються при невизначеності
_STANDARD_BASE_TESTS = ["CRP", "NFS"]

# Додаткові тести за профілем діагнозу
_PROFILE_TESTS: dict[str, list[str]] = {
    "Pneumonie":             ["Radiographie pulmonaire"],
    "Bronchite":             ["Radiographie pulmonaire"],
    "Grippe":                [],
    "Angor":                 ["ECG", "BNP"],
    "Insuffisance cardiaque":["ECG", "BNP"],
    "Embolie pulmonaire":    ["ECG", "D-dimères"],
    "Trouble du rythme":     ["ECG"],
}


def compute_optimized_cost(selected_tests: list[str]) -> int:
    tests_cost = sum(TEST_COSTS.get(t, 30) for t in selected_tests)
    return CONSULTATION_COST + tests_cost


def estimate_standard_cost(top_diag: str, urgency: str, tcs: str) -> int:
    base = 2 * CONSULTATION_COST
    base += sum(TEST_COSTS.get(t, 0) for t in _STANDARD_BASE_TESTS)

    for t in _PROFILE_TESTS.get(top_diag, []):
        base += TEST_COSTS.get(t, 0)

    # Невизначеність → консультація спеціаліста (60€ flat)
    if tcs in ("TCS_3", "TCS_4", "incertain"):
        base += 60

    return base


def compute_savings(
    top_diag: str,
    urgency: str,
    tcs: str,
    selected_tests: list[str],
) -> dict:
    optimized = compute_optimized_cost(selected_tests)
    standard = estimate_standard_cost(top_diag, urgency, tcs)
    savings = max(0, standard - optimized)
    return {
        "standard_cost": standard,
        "optimized_cost": optimized,
        "savings": savings,
    }