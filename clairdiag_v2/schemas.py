"""
ClairDiag v3 — Pydantic Schemas
"""

from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class PatientContext(BaseModel):
    sex: Optional[str] = "unknown"
    age: Optional[int] = None
    duration_days: Optional[int] = None


class V3Request(BaseModel):
    free_text: str
    patient_context: Optional[PatientContext] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "free_text": "Je suis fatiguée, j'ai pris du poids et j'ai la peau sèche depuis 2 mois.",
                "patient_context": {"sex": "female", "age": 35, "duration_days": 60},
            }
        }
    }


class GeneralOrientation(BaseModel):
    category: str
    recommended_action: str
    possible_specialist: str
    urgency: str
    reason: str
    red_flags_to_watch: List[str]
    suggested_basic_tests: List[str]
    patient_explanation: str
    limitations: str


class ClinicalReasoning(BaseModel):
    dominant_pattern: str
    why_this_orientation: List[str]
    danger_to_exclude: List[str]
    why_not_more_precise: str
    next_best_step: str


class DangerExclusion(BaseModel):
    must_exclude: List[str]
    red_flags: List[str]


class ConfidenceDetail(BaseModel):
    level: str   # low | medium | high
    score: int   # 0-10
    reasons: List[str]


class RoutingDecision(BaseModel):
    used_v2_core: bool
    used_general_orientation: bool
    reason: str


class V3Response(BaseModel):
    v2_output: Dict[str, Any]
    general_orientation: Optional[GeneralOrientation]
    clinical_reasoning: Optional[ClinicalReasoning]
    danger_exclusion: Optional[DangerExclusion]
    confidence_detail: ConfidenceDetail
    routing_decision: RoutingDecision
    disclaimer: str