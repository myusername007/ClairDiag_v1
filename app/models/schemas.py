from pydantic import BaseModel
from typing import List, Optional, Dict, Literal


# ── CORE LOCK constants (mirrored from orchestrator) ──────────────────────────
ENGINE_VERSION: str = "v2.3"
RULES_VERSION: str = "v1.2"
REGISTRY_VERSION: str = "v1.0"
VALIDATION_BASELINE: str = "H15_G30_F40_S100"
CORE_STATUS: str = "LOCKED"

# ── Decision type ─────────────────────────────────────────────────────────────
DecisionType = Literal[
    "EMERGENCY",
    "URGENT_MEDICAL_REVIEW",
    "TESTS_REQUIRED",
    "MEDICAL_REVIEW",
    "LOW_RISK_MONITOR",
]


class AnalyzeRequest(BaseModel):
    symptoms: List[str]
    onset: Optional[str] = None
    duration: Optional[str] = None
    debug: bool = False
    validation_mode: bool = False

    model_config = {
        "json_schema_extra": {
            "example": {
                "symptoms": ["fièvre", "toux", "fatigue"],
                "onset": "brutal",
                "duration": "days",
                "debug": False,
            }
        }
    }


class ParseSymptomsRequest(BaseModel):
    text: str


class Diagnosis(BaseModel):
    name: str
    probability: float
    key_symptoms: List[str] = []


class Tests(BaseModel):
    required: List[str]
    optional: List[str]




# ── Debug Trace ───────────────────────────────────────────────────────────────

class DebugBPU(BaseModel):
    raw_scores: Dict[str, float] = {}
    probs_after_combos: Dict[str, float] = {}
    probs_after_penalties: Dict[str, float] = {}
    combo_bonuses_applied: List[str] = []
    penalties_applied: List[str] = []
    incoherence_score: float = 0.0
    final_probs: Dict[str, float] = {}


class DebugCRE(BaseModel):
    rules_applied: List[str] = []
    probs_before: Dict[str, float] = {}
    probs_after: Dict[str, float] = {}


class DebugTCE(BaseModel):
    onset: Optional[str] = None
    duration: Optional[str] = None
    boosts_applied: List[str] = []
    penalties_applied: List[str] = []
    probs_before: Dict[str, float] = {}
    probs_after: Dict[str, float] = {}


class DebugTCS(BaseModel):
    coverage: float = 0.0
    coherence: float = 0.0
    quality: float = 0.0
    raw_score: float = 0.0
    incoherence_penalty: float = 0.0
    final_score: float = 0.0
    low_data_cap_applied: bool = False
    confidence_level: str = ""
    tcs_level: str = ""


class DebugTrace(BaseModel):
    # CORE LOCK
    engine_version: str = ENGINE_VERSION
    rules_version: str = RULES_VERSION
    registry_version: str = REGISTRY_VERSION
    core_status: str = CORE_STATUS

    # Parser
    symptoms_after_parser: List[str] = []
    symptoms_after_scm: List[str] = []

    # RFE
    red_flags_detected: List[str] = []
    emergency: bool = False

    # BPU
    bpu: DebugBPU = DebugBPU()

    # CRE
    cre: DebugCRE = DebugCRE()

    # TCE
    tce: DebugTCE = DebugTCE()

    # TCS
    tcs: DebugTCS = DebugTCS()

    # LME
    selected_tests: List[str] = []

    # SGL
    sgl_warnings: List[str] = []
    confidence_final: str = ""

    # Emergency override
    emergency_override_triggered: bool = False
    emergency_override_patterns: List[str] = []

    # Confidence
    confidence_gap_top1_top2: float = 0.0

    # Misdiagnosis risk
    misdiagnosis_risk: str = ""
    misdiagnosis_risk_score: float = 0.0

    # Do not miss
    do_not_miss: List[str] = []

    # Decision
    decision: str = ""

    # Test priority reasoning
    test_priority_reasoning: List[str] = []

    # Diagnostic path summary
    diagnostic_path_summary: str = ""


# ── Validation Mode ───────────────────────────────────────────────────────────

class ValidationDiagnosis(BaseModel):
    name: str
    probability: float
    why: List[str]
    why_not: List[str]


class ValidationResponse(BaseModel):
    top3: List[ValidationDiagnosis]
    tests_reasoning: List[str]
    confidence_breakdown: dict
    engine_version: str = ENGINE_VERSION
    rules_version: str = RULES_VERSION


# ── NLP Input Confidence (п.1, 2) ────────────────────────────────────────────

class InputConfidence(BaseModel):
    input_confidence: Literal["high", "medium", "low"] = "medium"
    confirm_required: bool = False
    confirm_type: Optional[Literal["urgent", "ambiguity", "low_data"]] = None
    parser_score: float = 1.0          # 0.0–1.0, деградує за fuzzy/typo/short


# ── Decision Logic (п.4) ──────────────────────────────────────────────────────

class DecisionLogic(BaseModel):
    score: float = 0.0
    risk: float = 0.0
    decision: str = ""
    reason: str = ""


# ── Safety Layer (п.5) ───────────────────────────────────────────────────────

class SafetyLayer(BaseModel):
    red_flags_checked: List[str] = []
    emergency_path: bool = False
    miss_risk: Literal["low", "medium", "high"] = "low"
    fallback_triggered: bool = False


# ── Economic Impact (п.6) ────────────────────────────────────────────────────

class EconomicImpact(BaseModel):
    tests_avoided: int = 0
    cost_saved: float = 0.0
    efficiency_gain: str = "1.0x"
    system_impact: str = ""


# ── Consistency Check (п.7) ──────────────────────────────────────────────────

class ConsistencyCheck(BaseModel):
    top1_stability: bool = True
    score_gap: float = 0.0
    decision_robustness: Literal["high", "medium", "low"] = "medium"


# ── Scenario Simulation (п.8) ────────────────────────────────────────────────

class ScenarioSimulation(BaseModel):
    best_case: str = ""
    worst_case: str = ""
    most_likely: str = ""


# ── Diagnostic Tree step (п.9) ───────────────────────────────────────────────

class DiagnosticTreeStep(BaseModel):
    step: int
    action: str
    if_positive: str = ""
    if_negative: str = ""


# ── Trust Score (п.10) ───────────────────────────────────────────────────────

class TrustScore(BaseModel):
    global_score: float = 0.0
    data_quality: float = 0.0
    model_confidence: float = 0.0
    risk_factor: float = 0.0


# ── Edge Case Analysis (п.11) ────────────────────────────────────────────────

class EdgeCaseAnalysis(BaseModel):
    atypical_presentation: bool = False
    conflict_detected: bool = False
    fallback_reason: str = ""


# ── Compliance (п.12) ────────────────────────────────────────────────────────

class Compliance(BaseModel):
    gdpr_ready: bool = True
    hds_ready: bool = True
    clinical_use: str = "decision_support_only"
    liability_level: Literal["low", "medium", "high"] = "low"


# ── Clinical Reasoning (п.3) ─────────────────────────────────────────────────

class ClinicalReasoning(BaseModel):
    symptom_clusters: List[str] = []
    rules_triggered: List[str] = []
    why_top1: str = ""
    why_not_others: str = ""
    risk_logic: str = ""
    test_strategy: str = ""


# ── Absolute Mode — Quality Gate (п.1) ───────────────────────────────────────

class QualityGate(BaseModel):
    passed: bool = True
    score: float = 0.0
    threshold: float = 0.97
    block_reason: str = ""


# ── Self-Check Engine (п.3) ───────────────────────────────────────────────────

class SelfCheck(BaseModel):
    logic_consistent: bool = True
    no_conflicts: bool = True
    decision_valid: bool = True
    tests_relevant: bool = True
    risk_aligned: bool = True


# ── Stability Check (п.6) ─────────────────────────────────────────────────────

class StabilityCheck(BaseModel):
    reproducible: bool = True
    variance: float = 0.0


# ── Main Response ─────────────────────────────────────────────────────────────

class AnalyzeResponse(BaseModel):
    # Core fields
    engine_version: str = ENGINE_VERSION
    rules_version: str = RULES_VERSION

    diagnoses: List[Diagnosis]
    tests: Tests
    explanation: str

    # Levels
    confidence_level: str = "modéré"
    urgency_level: str = "faible"

    # Decision Engine 2.0
    decision: DecisionType = "LOW_RISK_MONITOR"

    # RFE
    emergency_flag: bool = False
    emergency_reason: str = ""

    # TCS
    tcs_level: str = "incertain"  # incertain | fort | TCS_1..4

    # SGL
    sgl_warnings: List[str] = []

    # Test details
    test_explanations: dict = {}
    test_probabilities: dict = {}
    test_costs: dict = {}
    consultation_cost: int = 30

    # Session
    session_id: Optional[str] = None

    # Debug
    debug_trace: Optional[DebugTrace] = None
    validation: Optional[ValidationResponse] = None

    # Differential (Bloc C)
    differential: dict = {}

    # Test details (Bloc D)
    test_details: List[dict] = []

    # Diagnostic path (Bloc F)
    diagnostic_path: dict = {}

    # Economics (единая правда)
    economics: dict = {}

    # Misdiagnosis risk (Bloc G)
    misdiagnosis_risk: str = "faible"
    misdiagnosis_risk_score: float = 0.0

    # Worsening signs (Bloc 3B)
    worsening_signs: List[str] = []

    # Analysis limits (Bloc 3C)
    analysis_limits: List[str] = []

    # Do not miss (Bloc 4C)
    do_not_miss: List[str] = []

    # NLP Normalizer — симптоми як їх зрозумів normalizer (для UX confirmation)
    interpreted_symptoms: List[str] = []

    # ── NEW BLOCKS (ТЗ п.1–13) ───────────────────────────────────────────────

    # п.1+2 — Input confidence + parser scoring
    input_confidence: Optional[InputConfidence] = None

    # п.3 — Clinical reasoning
    clinical_reasoning: Optional[ClinicalReasoning] = None

    # п.4 — Decision logic
    decision_logic: Optional[DecisionLogic] = None

    # п.5 — Safety layer
    safety: Optional[SafetyLayer] = None

    # п.6 — Economic impact
    economic_impact: Optional[EconomicImpact] = None

    # п.7 — Consistency check
    consistency_check: Optional[ConsistencyCheck] = None

    # п.8 — Scenario simulation
    scenario_simulation: Optional[ScenarioSimulation] = None

    # п.9 — Diagnostic tree
    diagnostic_tree: List[DiagnosticTreeStep] = []

    # п.10 — Trust score
    trust_score: Optional[TrustScore] = None

    # п.11 — Edge case analysis
    edge_case_analysis: Optional[EdgeCaseAnalysis] = None

    # п.12 — Compliance
    compliance: Optional[Compliance] = None

    # п.13 — Failsafe flag
    is_fallback: bool = False

    # ── ABSOLUTE MODE (п.1–7) ────────────────────────────────────────────────
    quality_gate: Optional[QualityGate] = None
    self_check: Optional[SelfCheck] = None
    stability: Optional[StabilityCheck] = None
    is_valid_output: bool = True
    trace_id: str = ""


# ── Exam Re-evaluation Loop ───────────────────────────────────────────────────

class RevaluateRequest(BaseModel):
    session_id: str
    exam_results: Dict[str, str]

    model_config = {
        "json_schema_extra": {
            "example": {
                "session_id": "uuid-from-step1",
                "exam_results": {
                    "CRP": "high",
                    "Radiographie pulmonaire": "infiltrat",
                }
            }
        }
    }


class TestImpact(BaseModel):
    test: str
    result: str
    target_diagnosis: str
    delta: float
    direction: Literal["boost", "suppress"]
    reason: str


class RevaluateResponse(BaseModel):
    session_id: str

    # Before / after
    diagnoses_before: List[Diagnosis]
    diagnoses_after: List[Diagnosis]

    # Decision before / after
    decision_before: str = ""
    decision_after: str = ""

    # Changes
    changes_log: List[str] = []

    # Structured test impact
    tests_impact: List[TestImpact] = []

    # Human-readable summary
    changes_summary: str = ""
    reasoning_summary: str = ""

    # Levels after
    tcs_level: str = "TCS_4"
    confidence_level: str = "modéré"
    urgency_level: str = "faible"
    sgl_warnings: List[str] = []


# ── Parser Confirmation ───────────────────────────────────────────────────────

class ParseConfirmRequest(BaseModel):
    text: str

    model_config = {
        "json_schema_extra": {
            "example": {"text": "j'ai de la fièvre et je tousse depuis 3 jours"}
        }
    }


class ParseConfirmResponse(BaseModel):
    detected: List[str]
    unknown: List[str]
    confirmation_message: str
    ready_to_analyze: bool