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
    "TESTS_FIRST",
    "TESTS_REQUIRED",
    "MEDICAL_REVIEW",
    "CONFIRMED_PATH",
    "FOLLOW_UP",
    "LOW_RISK_MONITOR",
]


# ── Context Parser (патч п.4) ─────────────────────────────────────────────────

class SymptomContext(BaseModel):
    trigger:          Optional[str] = None   # "après repas"
    pattern:          Optional[str] = None   # "répétitif"
    cause:            Optional[str] = None   # "post-antibiotiques"
    frequency:        Optional[str] = None   # "chaque fois" | "souvent" | "parfois"
    chronology:       Optional[str] = None   # "depuis plusieurs jours"
    aggravation_time: Optional[str] = None   # "la nuit" | "le matin"
    after_food:       bool = False
    post_medication:  bool = False
    night_worsening:  bool = False


# ── Symptom Traceability (ТЗ п.3) ───────────────────────────────────────────
class SymptomTrace(BaseModel):
    """Кожен симптом traceable до вхідного слова."""
    traces: Dict[str, str] = {}   # symptom → matched_input_word


# ── Request / Response models ─────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    symptoms: List[str]
    onset: Optional[str] = None
    duration: Optional[str] = None
    debug: bool = False
    validation_mode: bool = False
    voice_confidence: Optional[str] = None   # "high" | "medium" | "low" — з фронту
    raw_text: Optional[str] = None            # оригінальний текст юзера для context_parser

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
    confirm_type: Optional[Literal["urgent", "ambiguity", "low_data", "voice_uncertain"]] = None
    confirm_message: str = ""
    parser_score: float = 1.0          # 0.0–1.0, деградує за fuzzy/typo/short


# ── Decision Logic (п.4) ──────────────────────────────────────────────────────

class DecisionLogic(BaseModel):
    score: float = 0.0
    risk: float = 0.0
    decision: str = ""
    reason: str = ""
    decision_basis: List[str] = []
    override_applied: bool = False
    override_reason: str = ""


# ── Safety Layer (п.5) ───────────────────────────────────────────────────────

class SafetyLayer(BaseModel):
    red_flags_checked: List[str] = []
    emergency_path: bool = False
    miss_risk: Literal["low", "medium", "high"] = "low"
    fallback_triggered: bool = False
    safety_notes: List[str] = []
    urgent_confirmation_required: bool = False


# ── Economic Impact (п.6) ────────────────────────────────────────────────────

class EconomicImpact(BaseModel):
    tests_avoided: int = 0
    cost_saved: float = 0.0
    efficiency_gain: str = "1.0x"
    system_impact: str = ""
    consultations_avoided: int = 0
    pathway_shortened: bool = False


# ── Consistency Check (п.7) ──────────────────────────────────────────────────

class ConsistencyCheck(BaseModel):
    top1_stability: bool = True
    score_gap: float = 0.0
    decision_robustness: Literal["high", "medium", "low"] = "medium"
    symptom_logic_consistent: bool = True
    context_logic_consistent: bool = True


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
    goal: str = ""
    priority: str = ""
    estimated_value: str = ""


# ── Trust Score (п.10) ───────────────────────────────────────────────────────

class TrustScore(BaseModel):
    global_score: float = 0.0
    data_quality: float = 0.0
    model_confidence: float = 0.0
    risk_factor: float = 0.0
    parser_reliability: float = 0.0
    context_quality: float = 0.0


# ── Edge Case Analysis (п.11) ────────────────────────────────────────────────

class EdgeCaseAnalysis(BaseModel):
    atypical_presentation: bool = False
    conflict_detected: bool = False
    fallback_reason: str = ""
    manual_review_recommended: bool = False


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
    context_influence: str = ""
    negative_signals: List[str] = []
    discriminator_logic: str = ""


# ── Audit Mode (фінальний блок 1) ────────────────────────────────────────────

class AuditMode(BaseModel):
    input_received: List[str] = []
    normalized_symptoms: List[str] = []
    rules_triggered: List[str] = []
    scores_before: Dict[str, float] = {}
    scores_after: Dict[str, float] = {}
    final_decision_path: str = ""
    context_detected: Dict[str, str] = {}
    symptom_trace: Dict[str, str] = {}


# ── Version Lock (фінальний блок 2) ──────────────────────────────────────────

class EngineMeta(BaseModel):
    engine_version: str = ENGINE_VERSION
    rules_version: str = RULES_VERSION
    mode: str = "ABSOLUTE"
    build_hash: str = "8ea6d8f3e436"
    core_status: str = CORE_STATUS


# ── Investor Safe Mode (фінальний блок 3) ────────────────────────────────────

class SafeOutput(BaseModel):
    is_medical_advice: bool = False
    requires_validation: bool = True
    risk_level: str = "controlled"
    usage_scope: str = "orientation_only"


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


# ── Clinical Reasoning V2 (п.1 — Global Explainability) ─────────────────────

class ClinicalReasoningV2(BaseModel):
    """Per-response explainability block — кожен діагноз має обґрунтування."""
    main_logic: List[str] = []          # symptom → hypothesis links + context influence
    why_this_diagnosis: List[str] = []  # чому top1 вибраний
    why_not_others: List[str] = []      # explicit downgrade logic per альтернатива


# ── Probability Reasoning (п.2) ───────────────────────────────────────────────

class ProbabilityEntry(BaseModel):
    score: float = 0.0
    based_on: List[str] = []       # symptoms + context що дали цей score
    downgrade_factors: List[str] = []  # що знизило ймовірність


class ProbabilityReasoning(BaseModel):
    """Замінює голі числа — кожна ймовірність пояснена."""
    diagnoses: Dict[str, ProbabilityEntry] = {}


# ── Test Reasoning (п.3) ──────────────────────────────────────────────────────

class TestReasoning(BaseModel):
    """Кожен тест прив'язаний до діагнозу."""
    links: Dict[str, str] = {}   # test_name → reason (linked to diagnosis)


# ── Do-Not-Miss Engine (п.4) ──────────────────────────────────────────────────

class DoNotMissEngine(BaseModel):
    """Hard rules — критичні діагнози що ЗАВЖДИ перевіряються."""
    flags: List[str] = []              # triggered hard rules
    mandatory_tests: List[str] = []    # тести що ОБОВ'ЯЗКОВІ за hard rules
    urgency_override: Optional[str] = None   # "moderate" | "high" | None
    cdiff_risk: bool = False           # diarrhea + post_antibiotics
    ecg_required: bool = False         # chest pain
    pe_baseline: bool = False          # dyspnea → PE evaluation


# ── Economic Reasoning (п.5) ──────────────────────────────────────────────────

class EconomicReasoning(BaseModel):
    """Замінює статичний savings — клінічна логіка за кожним рішенням."""
    tests_removed: List[str] = []
    why_removed: str = "low diagnostic value at this stage"
    risk_control: str = "escalation if needed"
    tests_kept: List[str] = []
    why_kept: str = ""


# ── Economic Engine V2 (investor-grade) ──────────────────────────────────────

class CostItem(BaseModel):
    """Один тест з ціною та прив'язкою до діагнозу."""
    test: str
    cost_eur: float = 0.0
    linked_diagnosis: str = ""
    clinical_justification: str = ""

class PathwayComparison(BaseModel):
    """Порівняння стандартного і оптимізованого шляхів."""
    standard_tests: List[CostItem] = []
    optimized_tests: List[CostItem] = []
    standard_cost: float = 0.0
    optimized_cost: float = 0.0
    savings: float = 0.0
    currency: str = "EUR"

class EconomicReasoningV2(BaseModel):
    """Investor-grade: traceable, clinically linked, defensible."""
    pathway: PathwayComparison = PathwayComparison()
    tests_removed: List[CostItem] = []
    why_removed: List[str] = []
    tests_kept: List[CostItem] = []
    why_kept: List[str] = []
    risk_control: str = "No critical test removed"
    critical_test_preserved: bool = True
    savings_blocked: bool = False            # True if critical test was in removed set
    savings_blocked_reason: str = ""
    summary: str = ""                        # human-readable 1-liner


# ── Explainability Score (п.7) ────────────────────────────────────────────────

class ExplainabilityScore(BaseModel):
    score: float = 0.0       # 0.0–1.0
    factors: List[str] = []  # що склало score


# ── Triage Level (UX layer) ──────────────────────────────────────────────────

class SeverityAssessment(BaseModel):
    """П.1: Severity engine — based on red flags, NOT risk."""
    level: Literal["mild", "moderate", "severe"] = "mild"
    drivers: List[str] = []
    red_flags_detected: List[str] = []

class TriageLevel(BaseModel):
    """П.2: Triage = severity only."""
    level: Literal["mild", "moderate", "severe"] = "moderate"
    label_fr: str = "Consultation recommandée"
    icon: str = "🟡"
    color: str = "amber"
    description: str = ""

class DiagnosticStatus(BaseModel):
    """П.3: Confidence ladder — dynamic threshold."""
    confidence: float = 0.0
    threshold_required: float = 0.97
    status: Literal["orientation_probable", "strongly_supported", "referral_required"] = "orientation_probable"

class FollowUp(BaseModel):
    """П.4: Follow-up engine."""
    recheck_in: str = "48h"
    if_worse: str = ""
    if_no_improvement: str = ""

class ActionPlan(BaseModel):
    """Concrete next steps for the patient."""
    immediate: List[str] = []
    within_24h: List[str] = []
    watch_for: List[str] = []
    self_care: List[str] = []

class UserReassurance(BaseModel):
    """П.6: Reassurance layer — do not panic without severity."""
    message: str = ""
    why_not_panic: List[str] = []

class UserExplanation(BaseModel):
    """П.7: Simple explanation for the user."""
    because_you_reported: List[str] = []
    this_suggests: List[str] = []

class KpiMetrics(BaseModel):
    """П.8: KPI engine for investors."""
    tests_avoided: int = 0
    low_value_tests_removed: int = 0
    estimated_savings_eur: float = 0.0
    unnecessary_consultations_avoided: int = 0

class ConfidenceExplanation(BaseModel):
    """UX: explain why confidence is not 100%."""
    why_not_100_percent: str = ""
    what_is_missing: List[str] = []
    what_would_increase_certainty: List[str] = []

class SystemValue(BaseModel):
    """UX: value even when savings == 0€."""
    value_delivered: List[str] = []
    confirmation_message: str = ""
    is_already_optimal: bool = False

class UxMessage(BaseModel):
    """БЛОК 4: UX message engine — severity+gap-aware user-facing message."""
    headline: str = ""
    detail: str = ""
    gap_warning: str = ""

# ── Explainability V3 ────────────────────────────────────────────────────────

class ReasoningStep(BaseModel):
    """Single fact→meaning→impact reasoning step."""
    fact: str = ""
    meaning: str = ""
    impact: str = ""

class ClinicalExplanationV3(BaseModel):
    """FIX 1: Causal chain explanation — fact → meaning → impact."""
    core_reasoning: List[ReasoningStep] = []
    final_synthesis: str = ""

class PrimaryActionBlock(BaseModel):
    """FIX 2: Single-focus primary action block — always first on screen."""
    action: str = ""
    severity_label: str = ""
    reason: str = ""

class UserReassuranceV2(BaseModel):
    """П.6: Why not to panic (only if severity != severe)."""
    headline: str = ""
    points: List[str] = []

class WhyConsultation(BaseModel):
    """П.7: Why consultation is needed — danger or uncertainty?"""
    reason_type: str = ""  # uncertainty | severity | follow_up
    message: str = ""

class DataQualityMessage(BaseModel):
    """П.10: Low-data / vague case honest message."""
    status: str = "sufficient"  # sufficient | insufficient_data | vague
    message: str = ""


# ── NLP Fallback (БЛОК 1) ─────────────────────────────────────────────────────

class NlpFallback(BaseModel):
    """Partial parse result — always show something, never 'Aucun résultat'."""
    understood: List[str] = []          # симптоми що розпізнані
    not_understood: List[str] = []      # сегменти що НЕ розпізнані
    suggestions: List[str] = []         # "Voulez-vous dire ?"
    partial_success: bool = False       # True якщо хоч 1 знайдено


# ── Baseline Pathway (БЛОК 2) ─────────────────────────────────────────────────

class BaselinePathway(BaseModel):
    """Real patient pathway cost vs optimized — true savings."""
    gp_visits: int = 2
    specialist_probability: float = 0.4
    extra_tests_cost: float = 150.0
    baseline_cost: float = 0.0          # реальний parcours без системи
    optimized_cost: float = 0.0         # optimized з ClairDiag
    savings_real: float = 0.0           # реальна економія
    currency: str = "EUR"
    profile: str = ""                   # digestif | cardiaque | respiratoire | general
    summary: str = ""

class PublicHealth(BaseModel):
    """П.9: Public mode — state-ready aggregation."""
    case_severity: Literal["mild", "moderate", "severe"] = "mild"
    pathway_optimized: bool = False
    referral_needed: bool = False

class DifferentialGap(BaseModel):
    """Differential gap — prevent false confidence when top1 ≈ top2."""
    value: float = 0.0
    interpretation: Literal["high_confidence", "low_separation"] = "high_confidence"
    force_referral: bool = False

class RoiProjection(BaseModel):
    """ROI projection — scale economics to system level."""
    per_case_savings_eur: float = 0.0
    per_1000_cases_savings_eur: float = 0.0
    annual_projection_eur: float = 0.0
    cost_reduction_percent: float = 0.0
    # Confidence tiers
    conservative_annual_eur: float = 0.0
    realistic_annual_eur: float = 0.0
    optimistic_annual_eur: float = 0.0
    assumptions: List[str] = []

class SystemImpact(BaseModel):
    """System impact — state-ready metrics."""
    gp_load_reduction: Literal["low", "moderate", "high"] = "low"
    emergency_avoidance: bool = False
    overdiagnosis_reduction: bool = False
    pathway_efficiency: Literal["improved", "neutral"] = "neutral"
    # Risk if NOT using the system
    risk_overload: str = ""
    risk_cost: str = ""
    risk_delay: str = ""


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

    # single primary diagnosis (résout contradiction top1 multi-section)
    primary_diagnosis: Optional[dict] = None

    # NLP Normalizer — симптоми як їх зрозумів normalizer (для UX confirmation)
    interpreted_symptoms: List[str] = []

    # ── Symptom Traceability (ТЗ п.3) ───────────────────────────────────────
    symptom_trace: Optional[SymptomTrace] = None

    # ── Voice Meta (ТЗ п.5) ──────────────────────────────────────────────────
    voice_meta: Optional[Dict] = None

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

    # ── Context Parser (патч п.4) ────────────────────────────────────────────
    context: Optional[SymptomContext] = None

    # ── FINAL LAYER (audit + version + investor) ─────────────────────────────
    audit: Optional[AuditMode] = None
    engine_meta: Optional[EngineMeta] = None
    safe_output: Optional[SafeOutput] = None

    # ── EXPLAINABILITY LAYER (п.1–7) ───────────────────────────────────────────────────
    clinical_reasoning_v2: Optional[ClinicalReasoningV2] = None
    probability_reasoning: Optional[ProbabilityReasoning] = None
    test_reasoning: Optional[TestReasoning] = None
    do_not_miss_engine: Optional[DoNotMissEngine] = None
    economic_reasoning: Optional[EconomicReasoning] = None
    economic_reasoning_v2: Optional[EconomicReasoningV2] = None
    explainability: Optional[ExplainabilityScore] = None

    # ── UX LAYER (п.1–10) ───────────────────────────────────────────────────
    severity_assessment: Optional[SeverityAssessment] = None
    triage: Optional[TriageLevel] = None
    diagnostic_status: Optional[DiagnosticStatus] = None
    follow_up: Optional[FollowUp] = None
    action_plan: Optional[ActionPlan] = None
    user_reassurance: Optional[UserReassurance] = None
    user_explanation: Optional[UserExplanation] = None
    kpi_metrics: Optional[KpiMetrics] = None
    public_health: Optional[PublicHealth] = None
    differential_gap: Optional[DifferentialGap] = None
    roi_projection: Optional[RoiProjection] = None
    system_impact: Optional[SystemImpact] = None
    confidence_explanation: Optional[ConfidenceExplanation] = None
    system_value: Optional[SystemValue] = None
    ux_message: Optional[UxMessage] = None

    # ── EXPLAINABILITY V3 + UX CLEAN ─────────────────────────────────────────
    clinical_explanation_v3: Optional[ClinicalExplanationV3] = None
    primary_action: Optional[PrimaryActionBlock] = None
    user_reassurance_v2: Optional[UserReassuranceV2] = None
    why_consultation: Optional[WhyConsultation] = None
    data_quality: Optional[DataQualityMessage] = None

    # ── FINAL FIX PACK ───────────────────────────────────────────────────────
    nlp_fallback: Optional[NlpFallback] = None          # БЛОК 1: partial NLP
    baseline_pathway: Optional[BaselinePathway] = None  # БЛОК 2: real economics

    # ── CLARIFICATION QUESTIONS ──────────────────────────────────────────────
    clarification_questions: Optional[Dict] = None


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
    context: Optional[SymptomContext] = None


# ── Import Tests Module ──────────────────────────────────────────────────────

class ParsedTestResult(BaseModel):
    """Single parsed test result."""
    raw_name: str = ""
    canonical_name: Optional[str] = None
    value: Optional[float] = None
    raw_value: str = ""
    unit: str = ""
    status: str = "inconnu"  # normal | élevé | bas | positif | négatif | inconnu
    recognized: bool = False


class ImportTestsRequest(BaseModel):
    """Request to parse test results from text or file."""
    text: Optional[str] = None
    file_base64: Optional[str] = None
    file_type: Optional[str] = None  # "pdf" | "image"
    # Optional: symptoms for context (if user already did symptom analysis)
    session_id: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "text": "CRP 28 mg/L\nleucocytes 13.2\nC. difficile positif",
            }
        }
    }


class ImportTestsResponse(BaseModel):
    """Parsed test results for confirmation screen."""
    results: List[ParsedTestResult] = []
    recognized_count: int = 0
    unrecognized_count: int = 0
    confirmation_message: str = ""
    ready_to_analyze: bool = False
    parse_method: str = "text"  # text | pdf | image | manual


class AnalyzeWithTestsRequest(BaseModel):
    """Confirmed test results + optional session for revaluation."""
    confirmed_results: List[ParsedTestResult]
    session_id: Optional[str] = None
    # If no session, user can provide symptoms for fresh analysis
    symptoms: Optional[List[str]] = None
    onset: Optional[str] = None
    duration: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "confirmed_results": [
                    {"canonical_name": "CRP", "value": 28, "raw_value": "28", "unit": "mg/L", "status": "élevé", "recognized": True},
                    {"canonical_name": "C. difficile", "raw_value": "positif", "status": "positif", "recognized": True},
                ],
                "session_id": "uuid-from-analyze",
            }
        }
    }


class TestInfluence(BaseModel):
    """Single test influence on diagnosis."""
    test: str
    result: str
    effect: str  # renforce | affaiblit | exclut | confirme
    target: str  # diagnosis name
    detail: str  # human-readable explanation


class AnalyzeWithTestsResponse(BaseModel):
    """Full response after test results integration."""
    # Phase
    phase: str = "phase_2"  # always phase_2 for this endpoint

    # Test influence block
    test_influences: List[TestInfluence] = []

    # Updated diagnoses
    diagnoses_before: List[Diagnosis] = []
    diagnoses_after: List[Diagnosis] = []

    # Decision
    decision_before: str = ""
    decision_after: str = ""
    final_decision: str = ""  # CONFIRMED_PATH | FOLLOW_UP | MEDICAL_REVIEW | URGENT
    confidence_before: str = ""
    confidence_after: str = ""

    # Key findings
    key_test: str = ""
    confirmed_diagnoses: List[str] = []
    excluded_diagnoses: List[str] = []

    # Summary
    changes_summary: str = ""
    reasoning_summary: str = ""
    action_label: str = ""  # human-readable final action

    # Economics (recalculated after tests)
    savings_after_tests: float = 0.0
    tests_avoided_after: int = 0

    # Carry-over from revaluate
    tests_impact: List[TestImpact] = []
    changes_log: List[str] = []
    urgency_level: str = "faible"
    sgl_warnings: List[str] = []