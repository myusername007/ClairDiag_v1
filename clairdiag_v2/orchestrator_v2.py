"""
ClairDiag v2.0 — Orchestrator v2
pipeline/orchestrator.py

Pipeline complet: text -> detection -> red_flags -> analysis -> orientation -> specialist.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

_CORE = Path(__file__).parent.parent / "core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

from universal_rules_loader import UniversalRulesLoader
from body_system_detector import BodySystemDetector
from red_flags_engine import RedFlagsEngine
from analysis_interpreter import AnalysisInterpreter, LabResult
from care_pathway_engine import CarePathwayEngineV2

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "ClairDiag v2.0 — Outil d orientation medicale non diagnostique. "
    "Contenu medical pending_physician_validation. "
    "Ne remplace pas une consultation medicale. "
    "En cas d urgence: appelez le 15."
)


class OrchestratorV2:
    """
    Pipeline ClairDiag v2.0.

    Usage:
        orch = OrchestratorV2()
        init_result = orch.initialize()
        result = orch.analyze(
            text="J ai mal au talon gauche depuis 3 jours",
            patient_context={"age": 45, "sex": "M"},
        )
    """

    def __init__(self, rules_dir: Optional[Path] = None):
        self._rules_dir = rules_dir or (Path(__file__).parent.parent / "rules")
        self._loader = UniversalRulesLoader(self._rules_dir)
        self._detector: Optional[BodySystemDetector] = None
        self._red_flags: Optional[RedFlagsEngine] = None
        self._analysis: Optional[AnalysisInterpreter] = None
        self._care_pathway: Optional[CarePathwayEngineV2] = None
        self._ready = False

    def initialize(self) -> Dict:
        status = self._loader.load()
        if not status.success:
            return {"success": False, "errors": status.errors, "warnings": status.warnings}

        self._detector = BodySystemDetector(self._loader.get("symptoms_rules"))
        self._red_flags = RedFlagsEngine(self._loader.get_rules("red_flags", "red_flags"))
        self._analysis = AnalysisInterpreter(self._loader.get("analysis_rules"))
        self._care_pathway = CarePathwayEngineV2(
            care_pathway_rules=self._loader.get("care_pathway_rules"),
            specialist_mapping=self._loader.get("specialist_mapping"),
        )
        self._ready = True

        return {
            "success": True,
            "versions": self._loader.versions(),
            "warnings": status.warnings,
            "modules": {
                "detector": self._detector.is_ready(),
                "red_flags": self._red_flags._flags.__len__() > 0,
                "analysis": self._analysis.is_ready(),
                "care_pathway": self._care_pathway.is_ready(),
                "specialist": self._care_pathway._resolver.is_ready(),
            }
        }

    def is_ready(self) -> bool:
        return self._ready

    def analyze(
        self,
        text: str,
        patient_context: Optional[Dict] = None,
        lab_results: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Analyse complete.

        Args:
            text: texte libre patient
            patient_context: {"age": int, "sex": "M"|"F", "risk_factors": [...], ...}
            lab_results: [{"analysis_id": "NFS", "fields": {"Hemoglobine_g_dL": 6.2}}]

        Returns:
            Response avec detection, triage, care_pathway, specialist, audit.
        """
        if not self._ready:
            return {"error": "not_initialized"}

        patient_context = patient_context or {}
        audit = []

        # Stage 1: Detection body_system
        detection = self._detector.detect(text, patient_context)
        dominant = detection["dominant_system"] or "douleur_generale_vague"
        body_zone = detection["body_zone"]
        audit.append(f"S1 detection: {dominant} (conf={detection['confidence']}, zone={body_zone})")

        # Stage 2: Red flags
        patient_data = {
            "symptoms": [m["symptom_id"] for m in detection["matched_symptoms"]],
            "demographics": {
                "age": patient_context.get("age"),
                "sex": patient_context.get("sex"),
                "pregnancy_status": patient_context.get("pregnancy_status"),
                "pregnancy_trimester": patient_context.get("pregnancy_trimester"),
            },
            "risk_factors": patient_context.get("risk_factors", []),
            "context_flags": patient_context.get("context_flags", []),
            "temporal": {"onset_speed": patient_context.get("onset_speed")},
        }
        rf_result = self._red_flags.evaluate(patient_data)
        if rf_result["triggered"]:
            flags_str = ", ".join(f["flag_id"] for f in rf_result["triggered_flags"])
            audit.append(f"S2 red_flags: {flags_str} -> {rf_result['highest_urgency']}")
        else:
            audit.append("S2 red_flags: none triggered")

        # Stage 3: Analysis interpreter (si lab_results fournis)
        analysis_result = None
        if lab_results:
            lab_objs = [
                LabResult(
                    analysis_id=lr["analysis_id"],
                    fields=lr.get("fields", {}),
                    source=lr.get("source", "patient_uploaded"),
                )
                for lr in lab_results
            ]
            analysis_result = self._analysis.apply(lab_objs)
            if analysis_result.has_modifiers:
                audit.append(
                    f"S3 analysis: {len(analysis_result.applied_modifiers)} modifiers, "
                    f"urgency_override={analysis_result.urgency_override}, "
                    f"specialist_override={analysis_result.specialist_override}"
                )

        # Stage 4: Care pathway
        orientation = self._care_pathway.resolve(
            body_system=dominant,
            body_zone=body_zone,
            red_flags_result=rf_result,
            analysis_result=analysis_result,
            patient_context=patient_context,
        )
        audit.append(f"S4 orientation: urgency={orientation.urgency}, specialist={orientation.specialist['primary']}")

        return {
            "v2_version": "2.0.0",
            "detection": {
                "dominant_system": detection["dominant_system"],
                "body_zone": body_zone,
                "confidence": detection["confidence"],
                "matched_symptoms_count": len(detection["matched_symptoms"]),
                "all_systems": detection["all_detected_systems"],
                "minimization_detected": detection["minimization_detected"],
                "escalation_detected": detection["escalation_detected"],
            },
            "triage": {
                "urgency": orientation.urgency,
                "red_flag_triggered": orientation.red_flag_triggered,
                "red_flags_detail": orientation.red_flags_detail,
            },
            "care_pathway": {
                "category": orientation.pathway_category,
                "urgency": orientation.urgency,
                "specialist": {
                    "primary": orientation.specialist["primary"],
                    "alternatives": orientation.specialist.get("alternatives", []),
                    "fallback": orientation.specialist.get("fallback", []),
                    "matched_rule": orientation.specialist.get("matched_rule"),
                    "rationale": orientation.specialist.get("rationale"),
                    "is_mt_legitimate": orientation.specialist.get("is_mt_legitimate", False),
                },
                "exams": {
                    "first_line": orientation.exams_first_line,
                    "if_persistent": orientation.exams_if_persistent,
                    "if_red_flags": orientation.exams_if_red_flags,
                    "additional_from_analysis": orientation.additional_exams_from_modifiers,
                },
                "warning_signs": orientation.warning_signs,
                "patient_message": orientation.patient_message,
                "economic_logic": orientation.economic_logic,
                "time_gain_logic": orientation.time_gain_logic,
            },
            "modifiers_applied": orientation.modifiers_applied,
            "audit": {
                "pipeline": audit,
                "pathway": orientation.audit_trail,
                "rule_versions": self._loader.versions(),
            },
            "disclaimer": DISCLAIMER,
        }

    def versions(self) -> Dict:
        return self._loader.versions()