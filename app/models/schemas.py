from pydantic import BaseModel
from typing import List, Optional, Dict


class AnalyzeRequest(BaseModel):
    symptoms: List[str]
    # TCE — temporal logic (étape 6)
    onset: Optional[str] = None        # "brutal" | "progressif" | None
    duration: Optional[str] = None     # "hours" | "days" | "weeks" | None
    # Debug mode (étape Sprint 3)
    debug: bool = False

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


# ── Debug Trace (Sprint 3, étape 4) ──────────────────────────────────────────

class DebugBPU(BaseModel):
    """Scores bruts BPU — avant normalisation, après combos et pénalités."""
    raw_scores: Dict[str, float] = {}        # scores avant normalisation
    probs_after_combos: Dict[str, float] = {}
    probs_after_penalties: Dict[str, float] = {}
    combo_bonuses_applied: List[str] = []    # ex: "fièvre+toux+essoufflement → Pneumonie +0.30"
    penalties_applied: List[str] = []        # ex: "rhinorrhée → Angine -0.15"
    incoherence_score: float = 0.0
    final_probs: Dict[str, float] = {}

class DebugCRE(BaseModel):
    """Règles CRE appliquées."""
    rules_applied: List[str] = []            # ex: "fièvre → Pneumonie +0.06"
    probs_before: Dict[str, float] = {}
    probs_after: Dict[str, float] = {}

class DebugTCE(BaseModel):
    """Modificateurs temporels appliqués."""
    onset: Optional[str] = None
    duration: Optional[str] = None
    boosts_applied: List[str] = []
    penalties_applied: List[str] = []
    probs_before: Dict[str, float] = {}
    probs_after: Dict[str, float] = {}

class DebugTCS(BaseModel):
    """Calcul confidence composite."""
    coverage: float = 0.0       # composante 1
    coherence: float = 0.0      # composante 2
    quality: float = 0.0        # composante 3
    raw_score: float = 0.0      # avant pénalité incoherence
    incoherence_penalty: float = 0.0
    final_score: float = 0.0
    low_data_cap_applied: bool = False
    confidence_level: str = ""
    tcs_level: str = ""

class DebugTrace(BaseModel):
    """Trace complète du pipeline — activée par debug=True."""
    # Versions
    engine_version: str = "v2.1"
    rules_version: str = "v1.0"

    # Étape 1+2 : NSE + SCM
    symptoms_after_parser: List[str] = []
    symptoms_after_scm: List[str] = []

    # Étape 3 : RFE
    red_flags_detected: List[str] = []
    emergency: bool = False

    # Étape 4 : BPU
    bpu: DebugBPU = DebugBPU()

    # Étape 7 : CRE
    cre: DebugCRE = DebugCRE()

    # Étape 6 : TCE
    tce: DebugTCE = DebugTCE()

    # Étape 8 : TCS
    tcs: DebugTCS = DebugTCS()

    # Étape 9 : LME
    selected_tests: List[str] = []

    # Étape 10 : SGL
    sgl_warnings: List[str] = []
    confidence_final: str = ""


# ── Response ──────────────────────────────────────────────────────────────────

class AnalyzeResponse(BaseModel):
    diagnoses: List[Diagnosis]
    tests: Tests
    cost: Cost
    explanation: str
    comparison: Comparison

    # Niveaux
    confidence_level: str = "modéré"   # élevé | modéré | faible  (SGL)
    urgency_level: str = "faible"       # élevé | modéré | faible  (RME)

    # RFE — red flags (étape 3)
    emergency_flag: bool = False
    emergency_reason: str = ""

    # TCS — seuil de décision (étape 8)
    tcs_level: str = "incertain"        # fort | besoin_tests | incertain

    # SGL — warnings (étape 10)
    sgl_warnings: List[str] = []

    # Détails analyses
    test_explanations: dict = {}
    test_probabilities: dict = {}
    test_costs: dict = {}
    consultation_cost: int = 30

    # Session ID pour le re-evaluation loop (étape 5)
    session_id: Optional[str] = None

    # Debug trace — None si debug=False
    debug_trace: Optional[DebugTrace] = None


# ── Exam Re-evaluation Loop (Sprint 3, étape 5) ───────────────────────────────

class RevaluateRequest(BaseModel):
    session_id: str
    exam_results: Dict[str, str]   # ex: {"CRP": "high", "radiographie": "infiltrat"}

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


class RevaluateResponse(BaseModel):
    session_id: str
    diagnoses_before: List[Diagnosis]   # résultats étape 1
    diagnoses_after: List[Diagnosis]    # résultats après réévaluation
    changes_log: List[str] = []         # ex: "CRP high → Pneumonie +0.36"
    tcs_level: str = "incertain"
    confidence_level: str = "modéré"
    urgency_level: str = "faible"
    sgl_warnings: List[str] = []


# ── Parser Confirmation Step (пункт 8) ───────────────────────────────────────

class ParseConfirmRequest(BaseModel):
    text: str

    model_config = {
        "json_schema_extra": {
            "example": {"text": "j'ai de la fièvre et je tousse depuis 3 jours"}
        }
    }


class ParseConfirmResponse(BaseModel):
    detected: List[str]          # симптоми після NSE+SCM
    unknown: List[str]           # слова не розпізнані
    confirmation_message: str    # текст для показу користувачу
    ready_to_analyze: bool       # True якщо ≥1 симптом розпізнано