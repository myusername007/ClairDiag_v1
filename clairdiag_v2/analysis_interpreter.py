"""
ClairDiag v2.0 — AnalysisInterpreter
core/analysis_interpreter.py

Evalue les resultats d analyses depuis analysis_rules.json.
Modifier composition: urgency max, specialist first-wins, exams union.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

URGENCY_ORDER = ["urgent", "urgent_medical_review", "medical_consultation", "non_urgent"]


def _urgency_rank(level: str) -> int:
    try:
        return URGENCY_ORDER.index(level)
    except ValueError:
        return len(URGENCY_ORDER)


def _max_urgency(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if a is None:
        return b
    if b is None:
        return a
    return a if _urgency_rank(a) <= _urgency_rank(b) else b


@dataclass
class LabResult:
    analysis_id: str
    fields: Dict[str, Any]
    source: str = "patient_uploaded"


@dataclass
class AppliedModifier:
    modifier_id: str
    label: str
    analysis_id: str
    field_name: str
    range_name: str
    value: Any
    affects: str
    delta: Dict[str, Any]
    add_exams: List[str]
    specialist_override: Optional[str]
    rationale: str


@dataclass
class AnalysisResult:
    applied_modifiers: List[AppliedModifier] = field(default_factory=list)
    urgency_override: Optional[str] = None
    specialist_override: Optional[str] = None
    additional_exams: List[str] = field(default_factory=list)
    audit_trail: List[str] = field(default_factory=list)

    @property
    def has_modifiers(self) -> bool:
        return len(self.applied_modifiers) > 0


def _match_range(value: Any, range_def: Dict) -> bool:
    if value is None:
        return False
    if "eq" in range_def:
        return str(value).lower() == str(range_def["eq"]).lower()
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    if "lte" in range_def and v > float(range_def["lte"]):
        return False
    if "lt" in range_def and v >= float(range_def["lt"]):
        return False
    if "gt" in range_def and v <= float(range_def["gt"]):
        return False
    if "gte" in range_def and v < float(range_def["gte"]):
        return False
    return True


class AnalysisInterpreter:
    """
    Interprete les resultats biologiques contre analysis_rules.json.

    Usage:
        results = interpreter.apply([
            LabResult("Troponines", {"Troponine_hs_ng_L": 85.0}),
        ])
        # results.urgency_override = "urgent"
        # results.specialist_override = "urgences_15"
    """

    def __init__(self, analysis_rules: Optional[Dict] = None):
        if not analysis_rules:
            self._analyses = {}
            self._modifiers = {}
            logger.warning("AnalysisInterpreter: no rules provided")
            return
        self._analyses = {a["analysis_id"]: a for a in analysis_rules.get("analyses", [])}
        self._modifiers = {m["modifier_id"]: m for m in analysis_rules.get("modifiers", [])}
        logger.info(f"AnalysisInterpreter: {len(self._analyses)} analyses, {len(self._modifiers)} modifiers")

    def apply(self, lab_results: List[LabResult]) -> AnalysisResult:
        result = AnalysisResult()

        for lab in lab_results:
            analysis_def = self._analyses.get(lab.analysis_id)
            if not analysis_def:
                continue
            for field_name, field_value in lab.fields.items():
                field_def = analysis_def.get("fields", {}).get(field_name)
                if not field_def:
                    continue
                for range_name, range_def in field_def.get("ranges", {}).items():
                    if "modifier_id" not in range_def:
                        continue
                    if _match_range(field_value, range_def):
                        modifier = self._modifiers.get(range_def["modifier_id"])
                        if not modifier:
                            continue
                        applied = AppliedModifier(
                            modifier_id=modifier["modifier_id"],
                            label=modifier.get("label", ""),
                            analysis_id=lab.analysis_id,
                            field_name=field_name,
                            range_name=range_name,
                            value=field_value,
                            affects=modifier.get("affects", ""),
                            delta=modifier.get("delta", {}),
                            add_exams=modifier.get("add_exams", []),
                            specialist_override=modifier.get("specialist_override"),
                            rationale=modifier.get("rationale", ""),
                        )
                        result.applied_modifiers.append(applied)
                        result.audit_trail.append(
                            f"{lab.analysis_id}.{field_name}={field_value} -> {range_name} -> {modifier['modifier_id']}"
                        )

        # Compose urgency (max severity)
        for mod in result.applied_modifiers:
            set_min = mod.delta.get("set_minimum")
            if set_min:
                result.urgency_override = _max_urgency(result.urgency_override, set_min)

        # Compose specialist (first wins)
        for mod in result.applied_modifiers:
            if mod.specialist_override and result.specialist_override is None:
                result.specialist_override = mod.specialist_override

        # Compose exams (union)
        seen = set()
        for mod in result.applied_modifiers:
            for exam in mod.add_exams + mod.delta.get("add_exams", []):
                if exam not in seen:
                    result.additional_exams.append(exam)
                    seen.add(exam)

        return result

    def is_ready(self) -> bool:
        return len(self._analyses) > 0

    def list_analysis_ids(self) -> List[str]:
        return list(self._analyses.keys())