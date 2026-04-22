"""
ClairDiag v2 — Economic Score v3 (TASK #012)
Comparative model: WITH ClairDiag vs WITHOUT ClairDiag.

RULES:
- Ranges only — no exact savings claims
- Confidence-adjusted savings (STEP 6)
- No negative/absurd values
"""

from __future__ import annotations

# ── COST TABLE (France baseline, EUR) ─────────────────────────────────────────

CONSULTATION_COST = {
    "standard": (25, 50),
    "urgent":   (60, 100),
}

TEST_COST_MAP: dict[str, tuple[int, int]] = {
    "ecg":                       (25,  40),
    "troponine":                  (15,  30),
    "echocardiographie":          (80, 150),
    "bnp":                        (20,  35),
    "holter_ecg":                 (60, 100),
    "d_dimeres":                  (15,  25),
    "radio_thorax":               (30,  50),
    "scanner_thoracique":         (100, 150),
    "angioscan_thoracique":       (100, 150),
    "scintigraphie_pulmonaire":   (120, 200),
    "imagerie_cerebrale_urgente": (100, 150),
    "scanner_cerebral":           (100, 150),
    "irm_cerebrale":              (150, 300),
    "nfs":                        (10,  20),
    "crp":                        (8,   15),
    "hemoc":                      (15,  30),
    "lactates":                   (10,  20),
    "ionogramme":                 (12,  22),
    "ionogramme_creatinine":      (15,  25),
    "bilan_hepatique":            (20,  35),
    "bilan_renal":                (15,  25),
    "procalcitonine":             (20,  35),
    "test_grippe_rapide":         (15,  25),
    "strep_rapide":               (10,  20),
    "pcr_covid":                  (20,  40),
    "echographie_abdominale":     (50,  90),
    "endoscopie_digestive":       (150, 300),
    "coproculture":               (20,  35),
    "calprotectine_fecale":       (30,  50),
    "bilan_thyroidien":           (20,  35),
    "glycemie":                   (8,   15),
    "bilan_lipidique":            (15,  25),
    "saturometrie":               (8,   15),
    "gazometrie_arterielle":      (25,  45),
}

# ── STEP 1 — BASELINE SCENARIOS (without ClairDiag) ──────────────────────────
# clinical_group → typical exams ordered without guidance

_BASELINE_TESTS: dict[str, list[str]] = {
    "cardiaque": [
        "ecg", "troponine", "crp", "nfs", "radio_thorax",
    ],
    "respiratoire": [
        "radio_thorax", "crp", "d_dimeres", "ecg", "saturometrie",
    ],
    "neurologique": [
        "scanner_cerebral", "nfs", "crp",
    ],
    "digestif": [
        "crp", "nfs", "echographie_abdominale",
    ],
    "infectieux": [
        "nfs", "crp", "hemoc", "test_grippe_rapide",
    ],
    "general": [
        "nfs", "crp", "radio_thorax",
    ],
}
_BASELINE_DEFAULT = ["nfs", "crp", "radio_thorax"]

# ── STEP 4 — High-confidence conditions → economic confidence "high" ──────────

_HIGH_CONF_CONDITIONS = {
    "sca", "avc_ischemique", "embolie_pulmonaire", "meningite_bacterienne",
    "sepsis_suspect", "appendicite_aigue", "dissection_aortique",
}

# ── HELPERS ───────────────────────────────────────────────────────────────────

def _test_cost(key: str) -> tuple[int, int]:
    return TEST_COST_MAP.get(key.lower().strip(), (20, 40))


def _sum_costs(test_keys: list[str]) -> tuple[int, int]:
    low  = sum(_test_cost(k)[0] for k in test_keys)
    high = sum(_test_cost(k)[1] for k in test_keys)
    return low, high


def _economic_confidence(
    top_hypothesis: str | None,
    clinical_confidence: str,
    orientation: str,
) -> str:
    if top_hypothesis in _HIGH_CONF_CONDITIONS and clinical_confidence in ("élevé", "modéré"):
        return "high"
    if clinical_confidence == "élevé":
        return "high"
    if clinical_confidence == "modéré" and orientation not in ("insufficient_data", ""):
        return "medium"
    return "low"


def _confidence_factor(econ_conf: str) -> float:
    """STEP 6 — reduce savings by confidence level."""
    return {"high": 1.0, "medium": 0.8, "low": 0.5}.get(econ_conf, 0.5)


# ── STEP 5 — CONSULTATION SCENARIO ───────────────────────────────────────────

def _consultation_scenario(orientation: str, consultation_avoided: bool) -> str:
    if "emergency" in orientation:
        return "urgent_direct"
    if consultation_avoided:
        return "single_consultation"
    return "double_consultation_likely"


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def compute_economic_score(
    recommended_tests: list[dict],
    orientation: str,
    top_hypothesis: str | None,
    clinical_confidence: str = "faible",
    clinical_group: str = "general",
) -> dict:
    """
    Comparative economic model: WITH vs WITHOUT ClairDiag.

    Returns STEP 7 structure:
    {
        "consultation_avoided": bool,
        "consultation_scenario": str,
        "tests_recommended_cost": int,
        "baseline_cost": {"low": int, "high": int},
        "economic_comparison": {
            "savings": {"low": int, "high": int}
        },
        "confidence": str
    }
    """
    test_keys = [t.get("test", "") for t in recommended_tests if t.get("test")]

    # ── STEP 3 — ClairDiag cost ───────────────────────────────────────────────
    tests_cost_low, tests_cost_high = _sum_costs(test_keys)
    consult = CONSULTATION_COST["urgent"] if "emergency" in orientation else CONSULTATION_COST["standard"]
    clairdiag_low  = consult[0] + tests_cost_low
    clairdiag_high = consult[1] + tests_cost_high
    tests_recommended_cost = (tests_cost_low + tests_cost_high) // 2

    # ── STEP 1+2 — Baseline cost (without ClairDiag) ─────────────────────────
    baseline_test_keys = _BASELINE_TESTS.get(clinical_group, _BASELINE_DEFAULT)
    baseline_tests_low, baseline_tests_high = _sum_costs(baseline_test_keys)

    # Baseline always includes double consultation (patient sees GP, then specialist)
    baseline_consult_low  = CONSULTATION_COST["standard"][0] * 2
    baseline_consult_high = CONSULTATION_COST["standard"][1] * 2
    if "emergency" in orientation:
        baseline_consult_low  = max(baseline_consult_low,  400)
        baseline_consult_high = max(baseline_consult_high, 800)

    baseline_low  = baseline_consult_low  + baseline_tests_low
    baseline_high = baseline_consult_high + baseline_tests_high

    # ── STEP 5 — Consultation logic ───────────────────────────────────────────
    consultation_avoided = orientation in (
        "supportive_followup",
        "medical_review_with_targeted_tests",
    )
    consultation_scen = _consultation_scenario(orientation, consultation_avoided)

    # Extra saving if second consultation avoided
    second_consult_saving = 25 if consultation_avoided else 0

    # ── STEP 4+6 — True savings with confidence adjustment ────────────────────
    econ_conf   = _economic_confidence(top_hypothesis, clinical_confidence, orientation)
    factor      = _confidence_factor(econ_conf)

    raw_saving_low  = max(0, baseline_low  - clairdiag_high) + second_consult_saving
    raw_saving_high = max(0, baseline_high - clairdiag_low)  + second_consult_saving

    saving_low  = max(0, int(raw_saving_low  * factor))
    saving_high = max(0, int(raw_saving_high * factor))

    # Sanity: saving_high >= saving_low
    if saving_high < saving_low:
        saving_high = saving_low

    return {
        "consultation_avoided":    consultation_avoided,
        "consultation_scenario":   consultation_scen,
        "tests_recommended_cost":  tests_recommended_cost,
        "baseline_cost": {
            "low":  baseline_low,
            "high": baseline_high,
        },
        "economic_comparison": {
            "savings": {
                "low":  saving_low,
                "high": saving_high,
            },
        },
        "confidence": econ_conf,
    }