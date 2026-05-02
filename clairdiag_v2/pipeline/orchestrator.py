"""
ClairDiag v2.0 — Orchestrator
pipeline/orchestrator.py

Pipeline principal v2.0. Orchestre tous les modules core.
Toute logique médicale vient des JSON — zéro hardcoding.

Flow:
  1. Charger les règles (UniversalRulesLoader)
  2. Détecter body_system (BodySystemDetector)
  3. Évaluer red flags (RedFlagsEngine)
  4. Construire care pathway (CarePathwayEngine)
  5. [Optionnel] Interpréter analyses (AnalysisInterpreter)
  6. [Optionnel] Calculer remboursement (ReimbursementEngine)
  7. Retourner response structuré
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Path setup pour import des modules core
_CORE_DIR = Path(__file__).parent.parent / "core"
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

from universal_rules_loader import UniversalRulesLoader
from body_system_detector import BodySystemDetector
from red_flags_engine import RedFlagsEngine
from care_pathway_engine import CarePathwayEngine
from analysis_interpreter import AnalysisInterpreter
from reimbursement_engine import ReimbursementEngine
from learning_feedback_module import LearningFeedbackModule

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "ClairDiag v2.0 — Outil d orientation médicale non diagnostique. "
    "Contenu médical en cours de validation (pending_physician_validation). "
    "Ne remplace pas une consultation médicale. "
    "En cas d urgence: appelez le 15."
)


class Orchestrator:
    """
    Pipeline principal ClairDiag v2.0.

    Usage:
        orch = Orchestrator()
        orch.initialize()  # charge les JSON
        result = orch.analyze(text="J ai mal au talon", patient_context={...})
    """

    def __init__(self, rules_dir: Optional[Path] = None):
        self._rules_dir = rules_dir or (Path(__file__).parent.parent / "rules")
        self._loader = UniversalRulesLoader(self._rules_dir)
        self._detector: Optional[BodySystemDetector] = None
        self._red_flags: Optional[RedFlagsEngine] = None
        self._care_pathway: Optional[CarePathwayEngine] = None
        self._analysis: Optional[AnalysisInterpreter] = None
        self._reimbursement: Optional[ReimbursementEngine] = None
        self._feedback: Optional[LearningFeedbackModule] = None
        self._ready = False

    def initialize(self) -> Dict:
        """
        Charge tous les JSON et initialise les modules.
        Doit être appelé une fois au démarrage du backend.

        Returns:
            {"success": bool, "versions": dict, "warnings": [...], "errors": [...]}
        """
        status = self._loader.load()

        if not status.success:
            logger.error(f"Orchestrator init failed: {status.errors}")
            return {
                "success": False,
                "versions": self._loader.versions(),
                "warnings": status.warnings,
                "errors": status.errors,
            }

        # Initialiser les modules avec les données JSON
        symptoms_data = self._loader.get_rules("symptoms_rules", "symptoms")
        red_flags_data = self._loader.get_rules("red_flags", "red_flags")
        care_pathway_data = self._loader.get("care_pathway_rules") or {}
        care_pathway_rules = care_pathway_data.get("rules", [])
        global_rules = care_pathway_data.get("global_rules", {})

        self._detector = BodySystemDetector(symptoms_data)
        self._red_flags = RedFlagsEngine(red_flags_data)
        self._care_pathway = CarePathwayEngine(care_pathway_rules, global_rules)
        self._analysis = AnalysisInterpreter(self._loader.get_rules("analysis_rules"))
        self._reimbursement = ReimbursementEngine(self._loader.get_rules("reimbursement_rules"))
        self._feedback = LearningFeedbackModule(
            schema=self._loader.get("learning_feedback_schema")
        )

        self._ready = True
        logger.info("Orchestrator: initialized and ready")

        return {
            "success": True,
            "versions": self._loader.versions(),
            "warnings": status.warnings,
            "errors": [],
        }

    def is_ready(self) -> bool:
        return self._ready

    def analyze(
        self,
        text: str,
        patient_context: Optional[Dict] = None,
    ) -> Dict:
        """
        Analyse principale: texte patient → orientation structurée.

        Args:
            text: texte libre du patient
            patient_context: {
                "age": int|None,
                "sex": "M"|"F"|None,
                "risk_factors": [str],
                "context_flags": [str],
                "temporal": {"onset_speed": str|None},
                "pregnancy_status": str|None,
            }

        Returns:
            Response structuré avec care_pathway, red_flags, specialist, exams, etc.
        """
        if not self._ready:
            return {
                "error": "orchestrator_not_initialized",
                "detail": "Call initialize() before analyze()",
            }

        patient_context = patient_context or {}

        # 1. Détecter le body_system dominant
        detection = self._detector.detect(text, patient_context)
        dominant_system = detection["dominant_system"]
        matched_symptoms_ids = [m["symptom_id"] for m in detection["matched_symptoms"]]

        # 2. Construire patient_data pour red flags
        demographics = {
            "age": patient_context.get("age"),
            "sex": patient_context.get("sex"),
            "pregnancy_status": patient_context.get("pregnancy_status"),
            "pregnancy_trimester": patient_context.get("pregnancy_trimester"),
        }
        patient_data = {
            "symptoms": matched_symptoms_ids,
            "demographics": demographics,
            "risk_factors": patient_context.get("risk_factors", []),
            "context_flags": patient_context.get("context_flags", []),
            "temporal": patient_context.get("temporal", {"onset_speed": None}),
        }

        # 3. Évaluer red flags
        rf_result = self._red_flags.evaluate(patient_data)

        # 4. Déterminer urgency_level
        if rf_result.get("override_triggered"):
            urgency_level = "urgent"
        elif rf_result.get("triggered"):
            urgency_level = rf_result.get("highest_urgency", "urgent_medical_review")
        else:
            urgency_level = "medical_consultation" if dominant_system else "medical_consultation"

        # 5. Construire care pathway
        category_id = dominant_system or "douleur_generale_vague"
        care_pathway = self._care_pathway.build(
            category_id=category_id,
            urgency_level=urgency_level,
            red_flags_result=rf_result,
            patient_context=patient_context,
        )

        return {
            "v2_version": "2.0.0",
            "detection": {
                "dominant_system": dominant_system,
                "confidence": detection["confidence"],
                "all_systems": detection["all_detected_systems"],
                "matched_symptoms_count": len(detection["matched_symptoms"]),
            },
            "triage": {
                "urgency": urgency_level,
                "red_flag_triggered": rf_result.get("triggered", False),
                "override_triggered": rf_result.get("override_triggered", False),
            },
            "care_pathway": care_pathway,
            "disclaimer": DISCLAIMER,
        }

    def versions(self) -> Dict:
        """Retourne les versions de tous les fichiers de règles."""
        return self._loader.versions()
