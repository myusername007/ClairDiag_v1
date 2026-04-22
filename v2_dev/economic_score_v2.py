"""
ClairDiag v2 — Economic Score v2 (TASK #011)
Realistic, structured, defensible economic model.

RULES:
- Estimated ranges only — no exact savings claims
- Probabilistic logic — no patient-level certainty
- France baseline costs (rough ranges acceptable per ТЗ)
"""

from __future__ import annotations

# ── STEP 1 — Cost table (France baseline, EUR) ────────────────────────────────
# Format: key → (low, high)

CONSULTATION_COST = {
    "standard": (25, 50),
    "urgent":   (60, 100),
}

TEST_COST_MAP: dict[str, tuple[int, int]] = {
    # Cardiaque
    "ecg":                       (25,  40),
    "troponine":                  (15,  30),
    "echocardiographie":          (80, 150),
    "bnp":                        (20,  35),
    "holter_ecg":                 (60, 100),
    # Pulmonaire / EP
    "d_dimeres":                  (15,  25),
    "radio_thorax":               (30,  50),
    "scanner_thoracique":         (100, 150),
    "angioscan_thoracique":       (100, 150),
    "scintigraphie_pulmonaire":   (120, 200),
    # Neurologique
    "imagerie_cerebrale_urgente": (100, 150),
    "scanner_cerebral":           (100, 150),
    "irm_cerebrale":              (150, 300),
    # Biologique général
    "nfs":                        (10,  20),
    "crp":                        (8,   15),
    "hemoc":                      (15,  30),
    "lactates":                   (10,  20),
    "ionogramme":                 (12,  22),
    "ionogramme_creatinine":      (15,  25),
    "bilan_hepatique":            (20,  35),
    "bilan_renal":                (15,  25),
    "procalcitonine":             (20,  35),
    # Infectieux
    "test_grippe_rapide":         (15,  25),
    "strep_rapide":               (10,  20),
    "pcr_covid":                  (20,  40),
    # Digestif
    "echographie_abdominale":     (50,  90),
    "endoscopie_digestive":       (150, 300),
    "coproculture":               (20,  35),
    "calprotectine_fecale":       (30,  50),
    # Autres
    "bilan_thyroidien":           (20,  35),
    "glycemie":                   (8,   15),
    "bilan_lipidique":            (15,  25),
    "saturometrie":               (8,   15),
    "gazometrie_arterielle":      (25,  45),
}

# Standard "without guidance" baseline: generic consult + NFS + CRP + radio
_STANDARD_TESTS = {"nfs", "crp", "radio_thorax"}
_STANDARD_BASELINE = (
    CONSULTATION_COST["standard"][0]
    + TEST_COST_MAP["nfs"][0]
    + TEST_COST_MAP["crp"][0]
    + TEST_COST_MAP["radio_thorax"][0],
    CONSULTATION_COST["standard"][1]
    + TEST_COST_MAP["nfs"][1]
    + TEST_COST_MAP["crp"][1]
    + TEST_COST_MAP["radio_thorax"][1],
)

# High-confidence conditions → economic confidence "high"
_HIGH_CONF_CONDITIONS = {
    "sca", "avc_ischemique", "embolie_pulmonaire", "meningite_bacterienne",
    "sepsis_suspect", "appendicite_aigue", "dissection_aortique",
}

# ── STEP 4 — Economic confidence logic ───────────────────────────────────────

def _economic_confidence(
    top_hypothesis: str | None,
    clinical_confidence: str,
    orientation: str,
) -> str:
    """
    high   → clear triage (SCA, AVC, EP, etc.)
    medium → probable orientation
    low    → uncertain / insufficient data
    """
    if top_hypothesis in _HIGH_CONF_CONDITIONS and clinical_confidence in ("élevé", "modéré"):
        return "high"
    if clinical_confidence == "élevé":
        return "high"
    if clinical_confidence == "modéré" and orientation not in ("insufficient_data", ""):
        return "medium"
    return "low"


def _test_cost(key: str) -> tuple[int, int]:
    return TEST_COST_MAP.get(key.lower().strip(), (20, 40))


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def compute_economic_score(
    recommended_tests: list[dict],
    orientation: str,
    top_hypothesis: str | None,
    clinical_confidence: str = "faible",
) -> dict:
    """
    Compute economic_impact for v2 output.

    Returns new ТЗ #011 structure:
    {
        "consultation_avoided": bool,
        "tests_recommended_cost": int,
        "tests_avoided_estimated": [...],
        "estimated_savings": {"low": int, "high": int},
        "confidence": "low | medium | high"
    }
    """
    test_keys = [t.get("test", "") for t in recommended_tests if t.get("test")]

    # STEP 2.1 — tests_recommended_cost (midpoint of range)
    tests_cost_low  = sum(_test_cost(k)[0] for k in test_keys)
    tests_cost_high = sum(_test_cost(k)[1] for k in test_keys)
    tests_recommended_cost = (tests_cost_low + tests_cost_high) // 2

    # STEP 2.2 — tests_avoided_estimated
    # Standard tests not in recommended → avoided
    tests_avoided_estimated = [k for k in _STANDARD_TESTS if k not in test_keys]

    # STEP 2.3 — consultation_avoided
    consultation_avoided = orientation in (
        "supportive_followup",
        "medical_review_with_targeted_tests",
    )

    # STEP 2.4+2.5 — estimated_total_cost and savings
    # Optimised path cost
    consult_cost = CONSULTATION_COST["urgent"] if "emergency" in orientation else CONSULTATION_COST["standard"]
    opt_low  = consult_cost[0] + tests_cost_low
    opt_high = consult_cost[1] + tests_cost_high

    # Standard baseline (higher for emergency)
    std_low, std_high = _STANDARD_BASELINE
    if "emergency" in orientation:
        std_low  = max(std_low,  400)
        std_high = max(std_high, 800)

    savings_low  = max(0, std_low  - opt_high)
    savings_high = max(0, std_high - opt_low)

    # STEP 4 — economic confidence
    econ_confidence = _economic_confidence(top_hypothesis, clinical_confidence, orientation)

    return {
        "consultation_avoided":      consultation_avoided,
        "tests_recommended_cost":    tests_recommended_cost,
        "tests_avoided_estimated":   tests_avoided_estimated,
        "estimated_savings": {
            "low":  savings_low,
            "high": savings_high,
        },
        "confidence": econ_confidence,
    }