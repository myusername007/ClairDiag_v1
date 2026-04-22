"""
ClairDiag v2 — Economic Score
Простий mapping test_key → cost_range без зовнішніх даних.

ПРАВИЛО: NO external data, NO algorithm change — тільки heuristic mapping.
"""

# ── Cost mapping (EUR, France 2024, bas/haut) ─────────────────────────────────
# Джерело: типові тарифи лабораторій Франції
TEST_COST_MAP: dict[str, tuple[int, int]] = {
    # Cardiaque
    "ecg":                      (25,  40),
    "troponine":                 (15,  30),
    "echocardiographie":         (80, 150),
    "bnp":                       (20,  35),
    "holter_ecg":                (60, 100),

    # Pulmonaire / EP
    "d_dimeres":                 (15,  25),
    "radio_thorax":              (25,  45),
    "scanner_thoracique":        (80, 150),
    "scintigraphie_pulmonaire":  (120, 200),

    # Neurologique
    "imagerie_cerebrale_urgente":(80, 150),
    "scanner_cerebral":          (80, 150),
    "irm_cerebrale":             (150, 300),

    # Biologique général
    "nfs":                       (10,  20),
    "crp":                       (8,   15),
    "hemoc":                     (15,  30),
    "lactates":                  (10,  20),
    "ionogramme":                (12,  22),
    "bilan_hepatique":           (20,  35),
    "bilan_renal":               (15,  25),

    # Infectieux
    "test_grippe_rapide":        (15,  25),
    "strep_rapide":              (10,  20),
    "pcr_covid":                 (20,  40),

    # Digestif
    "echographie_abdominale":    (50,  90),
    "endoscopie_digestive":      (150, 300),
    "coproculture":              (20,  35),

    # Autres
    "bilan_thyroidien":          (20,  35),
    "glycemie":                  (8,   15),
    "bilan_lipidique":           (15,  25),
}

# Consultation de base
CONSULTATION_COST_RANGE = (25, 50)

# Standard sans optimisation — consultation × 2 + NFS + CRP + radio_thorax
STANDARD_BASELINE_COST = (
    CONSULTATION_COST_RANGE[0] * 2 + TEST_COST_MAP["nfs"][0] + TEST_COST_MAP["crp"][0] + TEST_COST_MAP["radio_thorax"][0],
    CONSULTATION_COST_RANGE[1] * 2 + TEST_COST_MAP["nfs"][1] + TEST_COST_MAP["crp"][1] + TEST_COST_MAP["radio_thorax"][1],
)


def _test_cost(test_key: str) -> tuple[int, int]:
    """Повертає (low, high) для тесту. Fallback: (20, 40)."""
    key = test_key.lower().strip()
    return TEST_COST_MAP.get(key, (20, 40))


def compute_economic_score(
    recommended_tests: list[dict],
    orientation: str,
    top_hypothesis: str | None,
) -> dict:
    """
    Розраховує economic_impact для v2 output.

    Параметри:
    - recommended_tests: список з полем 'test'
    - orientation:       medical_orientation_v2
    - top_hypothesis:    основний діагноз
    """

    test_keys = [t.get("test", "") for t in recommended_tests if t.get("test")]

    # Вартість оптимізованого шляху
    opt_low  = CONSULTATION_COST_RANGE[0]
    opt_high = CONSULTATION_COST_RANGE[1]
    for key in test_keys:
        low, high = _test_cost(key)
        opt_low  += low
        opt_high += high

    # Стандартний шлях (базовий)
    std_low, std_high = STANDARD_BASELINE_COST

    # Якщо emergency — стандарт вищий (госпіталізація)
    if "emergency" in orientation.lower():
        std_low  = max(std_low,  400)
        std_high = max(std_high, 800)

    # Уникнуті тести (тести що є в стандарті але не в оптимізованому)
    _standard_tests = {"nfs", "crp", "radio_thorax"}
    tests_added   = [k for k in test_keys if k not in _standard_tests]
    tests_avoided = [k for k in _standard_tests if k not in test_keys]

    # Consultation avoided — якщо orientation не emergency/urgent
    consultation_avoided = orientation in (
        "supportive_followup",
        "medical_review_with_targeted_tests",
    )

    return {
        "consultation_avoided": consultation_avoided,
        "tests_avoided":        tests_avoided,
        "tests_added":          tests_added,
        "estimated_cost_range": {
            "low":  opt_low,
            "high": opt_high,
        },
        "standard_cost_range": {
            "low":  std_low,
            "high": std_high,
        },
        "estimated_savings_range": {
            "low":  max(0, std_low  - opt_high),
            "high": max(0, std_high - opt_low),
        },
    }