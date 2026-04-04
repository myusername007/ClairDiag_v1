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


class Cost(BaseModel):
    required: int
    optional: int
    savings: int


class Comparison(BaseModel):
    standard_tests: List[str]
    standard_cost: int
    optimized_tests: List[str]
    optimized_cost: int
    savings: int
    savings_multiplier: str
    cost_note: str = ""


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


# ── Main Response ─────────────────────────────────────────────────────────────

class AnalyzeResponse(BaseModel):
    # Core fields
    engine_version: str = ENGINE_VERSION
    rules_version: str = RULES_VERSION

    diagnoses: List[Diagnosis]
    tests: Tests
    cost: Cost
    explanation: str
    comparison: Comparison

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

    # Misdiagnosis risk (Bloc G)
    misdiagnosis_risk: str = "faible"
    misdiagnosis_risk_score: float = 0.0

    # Worsening signs (Bloc 3B)
    worsening_signs: List[str] = []

    # Analysis limits (Bloc 3C)
    analysis_limits: List[str] = []

    # Do not miss (Bloc 4C)
    do_not_miss: List[str] = []


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