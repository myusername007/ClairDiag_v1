"""
ClairDiag v2.0 — Orchestrator v2 (S10)
pipeline/orchestrator_v2.py

Pipeline complet S1–S9:
  S1  body_system_detector
  S2  red_flags_engine
  S3  analysis_interpreter (lab results)
  S4  care_pathway_engine
  S5  specialist_resolver (intégré dans care_pathway)
  S6  (analysis_rules déjà dans S3)
  S7  exam_interpreter (exam findings)
  S8  reimbursement_engine
  S9  learning_feedback_module (async)
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
from exam_interpreter import ExamInterpreter, ExamFinding
from care_pathway_engine import CarePathwayEngineV2
from reimbursement_engine import ReimbursementEngine
from learning_feedback_module import LearningFeedbackModule

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "ClairDiag v2.0 — Outil d'orientation médicale non diagnostique. "
    "Contenu médical pending_physician_validation. "
    "Ne remplace pas une consultation médicale. "
    "En cas d'urgence: appelez le 15."
)


class OrchestratorV2:
    """
    Pipeline ClairDiag v2.0 complet.

    Usage:
        orch = OrchestratorV2()
        orch.initialize()
        result = orch.analyze(
            text="J'ai mal au talon gauche depuis 3 jours",
            patient_context={"age": 45, "sex": "M"},
            lab_results=[{"analysis_id": "NFS", "fields": {"Hemoglobine_g_dL": 6.2}}],
            exam_findings=[{"exam_type": "radiographie", "finding_text": "fracture"}],
        )
    """

    def __init__(self, rules_dir: Optional[Path] = None):
        self._rules_dir = rules_dir or (Path(__file__).parent.parent / "rules")
        self._loader = UniversalRulesLoader(self._rules_dir)
        self._detector: Optional[BodySystemDetector] = None
        self._red_flags: Optional[RedFlagsEngine] = None
        self._analysis: Optional[AnalysisInterpreter] = None
        self._exam_interp: Optional[ExamInterpreter] = None
        self._care_pathway: Optional[CarePathwayEngineV2] = None
        self._reimbursement: Optional[ReimbursementEngine] = None
        self._feedback: Optional[LearningFeedbackModule] = None
        self._ready = False

    def initialize(self) -> Dict:
        status = self._loader.load()
        if not status.success:
            return {"success": False, "errors": status.errors, "warnings": status.warnings}

        # S1-S2
        self._detector = BodySystemDetector(self._loader.get("symptoms_rules"))
        self._red_flags = RedFlagsEngine(self._loader.get_rules("red_flags", "red_flags"))

        # S3 — analysis_interpreter (lab)
        self._analysis = AnalysisInterpreter(self._loader.get("analysis_rules"))

        # S7 — exam_interpreter (imagerie, ECG, etc.)
        self._exam_interp = ExamInterpreter(self._loader.get("exam_interpretation_rules"))

        # S4-S5 — care_pathway + specialist_resolver
        self._care_pathway = CarePathwayEngineV2(
            care_pathway_rules=self._loader.get("care_pathway_rules"),
            specialist_mapping=self._loader.get("specialist_mapping"),
        )

        # S8 — reimbursement
        self._reimbursement = ReimbursementEngine(self._loader.get("reimbursement_rules"))

        # S9 — feedback (queue mémoire par défaut)
        self._feedback = LearningFeedbackModule(
            feedback_schema=self._loader.get("learning_feedback_schema"),
        )

        self._ready = True
        return {
            "success": True,
            "versions": self._loader.versions(),
            "warnings": status.warnings,
            "modules": {
                "detector": self._detector.is_ready(),
                "red_flags": len(self._red_flags._flags) > 0,
                "analysis": self._analysis.is_ready(),
                "exam_interpreter": self._exam_interp.is_ready(),
                "care_pathway": self._care_pathway.is_ready(),
                "specialist": self._care_pathway._resolver.is_ready(),
                "reimbursement": self._reimbursement.is_ready(),
                "feedback": self._feedback.is_ready(),
            }
        }

    def is_ready(self) -> bool:
        return self._ready

    def analyze(
        self,
        text: str,
        patient_context: Optional[Dict] = None,
        lab_results: Optional[List[Dict]] = None,
        exam_findings: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Analyse complète S1→S8.

        Args:
            text: texte libre patient
            patient_context: {"age": int, "sex": "M"|"F", "risk_factors": [...], ...}
            lab_results: [{"analysis_id": "NFS", "fields": {"Hemoglobine_g_dL": 6.2}}]
            exam_findings: [{"exam_type": "ECG", "finding_text": "sus-decalage ST"}]
        """
        if not self._ready:
            return {"error": "not_initialized"}

        patient_context = patient_context or {}
        audit = []

        # S1 — Body system detection
        detection = self._detector.detect(text, patient_context)
        dominant = detection["dominant_system"] or "douleur_generale_vague"
        body_zone = detection["body_zone"]
        audit.append(f"S1 detection: {dominant} (conf={detection['confidence']}, zone={body_zone})")

        # S2 — Red flags
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

        # S3 — Analysis interpreter (lab results)
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

        # S7 — Exam interpreter (findings imagerie/ECG)
        exam_result = None
        if exam_findings:
            finding_objs = [
                ExamFinding(
                    exam_type=ef["exam_type"],
                    finding_text=ef["finding_text"],
                    source=ef.get("source", "patient_uploaded"),
                )
                for ef in exam_findings
            ]
            exam_result = self._exam_interp.apply(finding_objs)
            if exam_result.has_modifiers:
                audit.append(
                    f"S7 exam_interp: {len(exam_result.applied_modifiers)} modifiers, "
                    f"urgency_override={exam_result.urgency_override}"
                )
                # Fusionner exam_result dans analysis_result pour care_pathway
                if analysis_result is None:
                    # Créer un analysis_result synthétique depuis exam_result
                    from analysis_interpreter import AnalysisResult
                    analysis_result = AnalysisResult()
                # Merge urgency (max)
                from analysis_interpreter import _max_urgency
                analysis_result.urgency_override = _max_urgency(
                    analysis_result.urgency_override,
                    exam_result.urgency_override,
                )
                # Merge specialist (first wins)
                if exam_result.specialist_override and analysis_result.specialist_override is None:
                    analysis_result.specialist_override = exam_result.specialist_override
                # Merge exams (union)
                seen = set(analysis_result.additional_exams)
                for exam in exam_result.additional_exams:
                    if exam not in seen:
                        analysis_result.additional_exams.append(exam)
                        seen.add(exam)
                analysis_result.audit_trail.extend(exam_result.audit_trail)

        # S4-S5 — Care pathway + specialist
        orientation = self._care_pathway.resolve(
            body_system=dominant,
            body_zone=body_zone,
            red_flags_result=rf_result,
            analysis_result=analysis_result,
            patient_context=patient_context,
        )
        audit.append(
            f"S4 orientation: urgency={orientation.urgency}, "
            f"specialist={orientation.specialist['primary']}"
        )

        # S8 — Reimbursement
        economy_data = None
        if self._reimbursement and self._reimbursement.is_ready():
            all_exams = (
                orientation.exams_first_line +
                orientation.additional_exams_from_modifiers
            )
            economy_data = self._reimbursement.estimate(
                orientation.pathway_category,
                all_exams,
            )
            if economy_data:
                audit.append(
                    f"S8 economy: savings={economy_data.estimated_savings_eur}€, "
                    f"confidence={economy_data.confidence}"
                )

        # Build response
        response = {
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
            "economy": {
                "available": economy_data is not None,
                "savings_eur": economy_data.estimated_savings_eur if economy_data else None,
                "consultations_avoided": economy_data.consultations_avoided if economy_data else None,
                "tests_avoided": economy_data.tests_avoided if economy_data else None,
                "patient_out_of_pocket_eur": economy_data.patient_out_of_pocket_optimal_eur if economy_data else None,
                "confidence": economy_data.confidence if economy_data else None,
            },
            "modifiers_applied": orientation.modifiers_applied,
            "audit": {
                "pipeline": audit,
                "pathway": orientation.audit_trail,
                "rule_versions": self._loader.versions(),
            },
            "disclaimer": DISCLAIMER,
        }

        return response

    def submit_feedback(self, event: Dict) -> Dict:
        """
        S9 — Soumet un événement de feedback (async).
        Ne modifie JAMAIS les règles.
        """
        if not self._feedback:
            return {"success": False, "error": "feedback_module_not_initialized"}
        result = self._feedback.ingest(event)
        return {
            "success": result.success,
            "event_id": result.event_id,
            "queue": result.queue,
            "errors": result.validation_errors,
        }

    def versions(self) -> Dict:
        return self._loader.versions()