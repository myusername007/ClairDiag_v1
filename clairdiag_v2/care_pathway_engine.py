"""
ClairDiag v2.0 — CarePathwayEngineV2
core/care_pathway_engine.py

Construit l orientation depuis care_pathway_rules.json.
Integre les modifiers (urgency escalation, exams union).
Delegue la resolution specialist a SpecialistResolver.
"""

import logging
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from specialist_resolver import SpecialistResolver

logger = logging.getLogger(__name__)

URGENCY_ORDER = ["urgent", "urgent_medical_review", "medical_consultation", "non_urgent"]


def _urgency_rank(level: str) -> int:
    try:
        return URGENCY_ORDER.index(level)
    except ValueError:
        return len(URGENCY_ORDER)


def _max_urgency(a: Optional[str], b: Optional[str]) -> str:
    if not a:
        return b or "non_urgent"
    if not b:
        return a
    return a if _urgency_rank(a) <= _urgency_rank(b) else b


@dataclass
class Orientation:
    urgency: str
    pathway_category: str
    body_zone: Optional[str]
    exams_first_line: List[str]
    exams_if_persistent: List[str]
    exams_if_red_flags: List[str]
    additional_exams_from_modifiers: List[str]
    warning_signs: List[str]
    patient_message: str
    economic_logic: str
    time_gain_logic: str
    specialist: Dict
    red_flag_triggered: bool
    red_flags_detail: List[Dict]
    modifiers_applied: List[str]
    audit_trail: List[str]


class CarePathwayEngineV2:
    """
    Construit l orientation complete.

    Pipeline:
    1. Lookup pathway by body_system dans care_pathway_rules
    2. Compute base urgency (default_urgency de la regle)
    3. Appliquer red flags (escalade urgency)
    4. Appliquer modifiers (escalade urgency, specialist override, exams added)
    5. Resoudre specialiste via SpecialistResolver
    6. Retourner Orientation avec audit trail complet
    """

    def __init__(
        self,
        care_pathway_rules: Optional[Dict] = None,
        specialist_mapping: Optional[Dict] = None,
    ):
        if not care_pathway_rules:
            self._rules = {}
            self._global = {}
            logger.warning("CarePathwayEngineV2: no care pathway rules")
        else:
            self._rules = {
                r["category_id"]: r
                for r in care_pathway_rules.get("rules", [])
            }
            self._global = care_pathway_rules.get("global_rules", {})

        self._resolver = SpecialistResolver(specialist_mapping)
        # Also build body_system -> category_id index
        self._system_to_category: Dict[str, str] = {}
        for cat_id, rule in self._rules.items():
            for system in rule.get("body_systems_covered", []):
                if system not in self._system_to_category:
                    self._system_to_category[system] = cat_id

        logger.info(
            f"CarePathwayEngineV2: {len(self._rules)} pathways, "
            f"{len(self._system_to_category)} body_system mappings"
        )

    def resolve(
        self,
        body_system: str,
        body_zone: Optional[str] = None,
        red_flags_result: Optional[Dict] = None,
        analysis_result=None,   # AnalysisResult | None
        patient_context: Optional[Dict] = None,
    ) -> Orientation:
        """
        Construit l orientation complete pour un body_system.

        Args:
            body_system: systeme detecte (cardio, neuro, etc.)
            body_zone: zone specifique (talon, thorax, etc.)
            red_flags_result: output de RedFlagsEngine.evaluate()
            analysis_result: output de AnalysisInterpreter.apply()
            patient_context: age, sex, risk_factors, etc.
        """
        red_flags_result = red_flags_result or {}
        patient_context = patient_context or {}
        audit: List[str] = []

        # 1. Trouver la categorie pathway
        category_id = self._system_to_category.get(body_system)
        if not category_id:
            # Fallback: chercher par body_system direct
            category_id = body_system if body_system in self._rules else "douleur_generale_vague"
            audit.append(f"body_system '{body_system}' not in index, fallback to '{category_id}'")

        rule = self._rules.get(category_id)
        if not rule:
            logger.warning(f"No pathway rule for '{category_id}'")
            return self._minimum_orientation(category_id, body_zone, red_flags_result, audit)

        audit.append(f"pathway matched: {category_id}")

        # 2. Base urgency depuis la regle
        urgency = rule.get("default_urgency", "medical_consultation")

        # 3. Red flags escalation (jamais downgrade)
        rf_triggered = red_flags_result.get("triggered", False)
        rf_urgency = red_flags_result.get("highest_urgency")
        if rf_urgency:
            new_urgency = _max_urgency(urgency, rf_urgency)
            if new_urgency != urgency:
                audit.append(f"urgency escalated by red_flag: {urgency} -> {new_urgency}")
                urgency = new_urgency

        # 4. Modifiers escalation
        modifier_specialist_override = None
        additional_exams: List[str] = []
        modifiers_applied: List[str] = []

        if analysis_result and analysis_result.has_modifiers:
            if analysis_result.urgency_override:
                new_urgency = _max_urgency(urgency, analysis_result.urgency_override)
                if new_urgency != urgency:
                    audit.append(f"urgency escalated by modifier: {urgency} -> {new_urgency}")
                    urgency = new_urgency
            if analysis_result.specialist_override:
                modifier_specialist_override = analysis_result.specialist_override
                audit.append(f"specialist override by modifier: {modifier_specialist_override}")
            additional_exams = analysis_result.additional_exams
            modifiers_applied = [m.modifier_id for m in analysis_result.applied_modifiers]
            audit.extend(analysis_result.audit_trail)

        # 5. Resoudre specialiste
        demographics = {
            "sex": patient_context.get("sex"),
            "age": patient_context.get("age"),
        }
        specialist = self._resolver.resolve(
            pathway_category=category_id,
            urgency=urgency,
            body_zone=body_zone,
            demographics=demographics,
            modifier_specialist_override=modifier_specialist_override,
        )
        audit.append(f"specialist resolved: {specialist['primary']} via {specialist['matched_rule']}")

        # 6. Construire exams (base + modifiers)
        exams = rule.get("exams", {})

        return Orientation(
            urgency=urgency,
            pathway_category=category_id,
            body_zone=body_zone,
            exams_first_line=exams.get("first_line", []),
            exams_if_persistent=exams.get("if_persistent", []),
            exams_if_red_flags=exams.get("if_red_flags", []),
            additional_exams_from_modifiers=additional_exams,
            warning_signs=rule.get("warning_signs", []),
            patient_message=rule.get("patient_message", ""),
            economic_logic=rule.get("economic_logic", ""),
            time_gain_logic=rule.get("time_gain_logic", ""),
            specialist=specialist,
            red_flag_triggered=rf_triggered,
            red_flags_detail=[
                {"flag_id": f["flag_id"], "name": f["name"], "urgency": f["urgency"]}
                for f in red_flags_result.get("triggered_flags", [])
            ],
            modifiers_applied=modifiers_applied,
            audit_trail=audit,
        )

    def _minimum_orientation(self, category_id: str, body_zone: Optional[str], rf: Dict, audit: List[str]) -> Orientation:
        specialist = self._resolver.resolve(category_id, "medical_consultation", body_zone)
        return Orientation(
            urgency="medical_consultation",
            pathway_category=category_id,
            body_zone=body_zone,
            exams_first_line=["examen_clinique"],
            exams_if_persistent=[],
            exams_if_red_flags=[],
            additional_exams_from_modifiers=[],
            warning_signs=["Aggravation", "Fievre", "Douleur intense"],
            patient_message="Consultation medicale recommandee.",
            economic_logic="",
            time_gain_logic="",
            specialist=specialist,
            red_flag_triggered=rf.get("triggered", False),
            red_flags_detail=[],
            modifiers_applied=[],
            audit_trail=audit + ["minimum_output_guarantee applied"],
        )

    def is_ready(self) -> bool:
        return len(self._rules) > 0