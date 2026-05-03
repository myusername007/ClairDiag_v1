"""
ClairDiag v2.0 — ExamInterpreter (S7)
core/exam_interpreter.py

Interprète les résultats d'examens (ECG, imagerie, biologie composite)
via exam_interpretation_rules.json.
Réutilise la même structure Modifier que analysis_interpreter.py.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

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
class ExamFinding:
    """Résultat d'examen fourni par le patient ou le médecin."""
    exam_type: str           # "ECG", "echographie_abdominale", "radiographie", ...
    finding_text: str        # texte libre: "sus-decalage ST", "fracture", ...
    source: str = "patient_uploaded"


@dataclass
class AppliedExamModifier:
    modifier_id: str
    label: str
    exam_id: str
    exam_type: str
    matched_keyword: str
    affects: str
    delta: Dict
    add_exams: List[str]
    specialist_override: Optional[str]
    next_step: Optional[str]
    rationale: str


@dataclass
class ExamResult:
    applied_modifiers: List[AppliedExamModifier] = field(default_factory=list)
    urgency_override: Optional[str] = None
    specialist_override: Optional[str] = None
    additional_exams: List[str] = field(default_factory=list)
    audit_trail: List[str] = field(default_factory=list)

    @property
    def has_modifiers(self) -> bool:
        return len(self.applied_modifiers) > 0


def _normalize(text: str) -> str:
    return text.lower().strip()


class ExamInterpreter:
    """
    Interprète les findings d'examens via exam_interpretation_rules.json.

    Usage:
        findings = [
            ExamFinding("ECG", "sus-decalage ST"),
            ExamFinding("radiographie", "fracture"),
        ]
        result = interpreter.apply(findings)
        # result.urgency_override = "urgent"
        # result.specialist_override = "urgences_15"
    """

    def __init__(self, exam_rules: Optional[Dict] = None):
        if not exam_rules:
            self._interpretations = []
            self._modifiers = {}
            logger.warning("ExamInterpreter: no rules provided")
            return

        self._interpretations = exam_rules.get("exam_interpretations", [])
        self._modifiers = {
            m["modifier_id"]: m
            for m in exam_rules.get("modifiers", [])
        }
        # Build keyword index: (keyword_norm, exam_type_norm) -> exam_interpretation
        self._keyword_index: List[tuple] = []
        for interp in self._interpretations:
            exam_type = _normalize(interp.get("exam_type", ""))
            for kw in interp.get("match_keywords", []):
                self._keyword_index.append((
                    _normalize(kw), exam_type, interp
                ))

        logger.info(
            f"ExamInterpreter: {len(self._interpretations)} interpretations, "
            f"{len(self._modifiers)} modifiers, "
            f"{len(self._keyword_index)} keywords indexed"
        )

    def apply(self, findings: List[ExamFinding]) -> ExamResult:
        """
        Applique les règles d'interprétation aux findings.

        Composition des modifiers:
        - urgency: max (le plus urgent)
        - specialist_override: premier qui gagne
        - exams: union
        """
        result = ExamResult()

        for finding in findings:
            finding_norm = _normalize(finding.finding_text)
            exam_type_norm = _normalize(finding.exam_type)

            matched_interp = None
            matched_kw = None

            # Chercher le keyword le plus long qui match (greedy)
            for kw_norm, rule_exam_type, interp in sorted(
                self._keyword_index, key=lambda x: len(x[0]), reverse=True
            ):
                # Vérifier que l'exam_type correspond (ou que le finding le mentionne)
                type_matches = (
                    rule_exam_type == "" or
                    rule_exam_type == exam_type_norm or
                    rule_exam_type in exam_type_norm or
                    exam_type_norm in rule_exam_type
                )
                if not type_matches:
                    continue
                if kw_norm in finding_norm:
                    matched_interp = interp
                    matched_kw = kw_norm
                    break

            if not matched_interp:
                continue

            modifier_id = matched_interp.get("modifier_id")
            modifier = self._modifiers.get(modifier_id)
            if not modifier:
                logger.warning(f"modifier_id {modifier_id} not found in modifiers")
                continue

            applied = AppliedExamModifier(
                modifier_id=modifier["modifier_id"],
                label=modifier.get("label", ""),
                exam_id=matched_interp["exam_id"],
                exam_type=finding.exam_type,
                matched_keyword=matched_kw,
                affects=modifier.get("affects", ""),
                delta=modifier.get("delta", {}),
                add_exams=modifier.get("add_exams", []),
                specialist_override=modifier.get("specialist_override"),
                next_step=modifier.get("next_step"),
                rationale=modifier.get("rationale", ""),
            )
            result.applied_modifiers.append(applied)
            result.audit_trail.append(
                f"{finding.exam_type}: '{matched_kw}' -> {modifier_id}"
            )

        # Composition urgency (max)
        for mod in result.applied_modifiers:
            set_min = mod.delta.get("set_minimum")
            if set_min:
                result.urgency_override = _max_urgency(result.urgency_override, set_min)

        # Composition specialist (first wins)
        for mod in result.applied_modifiers:
            if mod.specialist_override and result.specialist_override is None:
                result.specialist_override = mod.specialist_override

        # Composition exams (union)
        seen = set()
        for mod in result.applied_modifiers:
            for exam in mod.add_exams + mod.delta.get("add_exams", []):
                if exam not in seen:
                    result.additional_exams.append(exam)
                    seen.add(exam)

        return result

    def is_ready(self) -> bool:
        return len(self._interpretations) > 0

    def list_exam_types(self) -> List[str]:
        return list({i.get("exam_type", "") for i in self._interpretations})