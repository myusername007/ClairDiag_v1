"""
ClairDiag v2.0 — CarePathwayEngine
core/care_pathway_engine.py

Construit le care pathway complet depuis care_pathway_rules.json.
Délègue la résolution spécialiste à SpecialistResolver.
Zéro hardcoding médical.
"""

import logging
from typing import Dict, List, Optional

from specialist_resolver import SpecialistResolver

logger = logging.getLogger(__name__)


class CarePathwayEngine:
    """
    Construit le care pathway structuré pour un patient.

    Input: body_system détecté + red_flags result + urgency
    Output: care_pathway complet (specialist, exams, warnings, message, économie)
    """

    def __init__(self, care_pathway_rules: List[Dict], global_rules: Optional[Dict] = None):
        self._resolver = SpecialistResolver(care_pathway_rules, global_rules)
        logger.info("CarePathwayEngine: initialized")

    def build(
        self,
        category_id: str,
        urgency_level: str,
        red_flags_result: Optional[Dict] = None,
        patient_context: Optional[Dict] = None,
    ) -> Dict:
        """
        Construit le care_pathway complet.

        Returns:
            {
                "applicable": bool,
                "matched_category": str,
                "urgency_level": str,
                "specialist": {...},
                "exams": {...},
                "warning_signs": [...],
                "patient_message": str,
                "economic_logic": str,
                "time_gain_logic": str,
                "red_flag_triggered": bool,
                "red_flags_detail": [...],
            }
        """
        red_flags_result = red_flags_result or {}
        red_flag_triggered = red_flags_result.get("triggered", False)
        red_flag_systems = red_flags_result.get("body_systems_flagged", [])
        triggered_flags = red_flags_result.get("triggered_flags", [])

        # Override: urgency from red flags si plus sévère
        rf_urgency = red_flags_result.get("highest_urgency")
        if rf_urgency and rf_urgency == "urgent":
            urgency_level = "urgent"

        resolution = self._resolver.resolve(
            category_id=category_id,
            urgency_level=urgency_level,
            red_flag_triggered=red_flag_triggered,
            red_flag_body_systems=red_flag_systems,
        )

        return {
            "applicable": True,
            "matched_category": category_id,
            "urgency_level": resolution["urgency_level"],
            "specialist": {
                "primary_recommended": resolution["primary_recommended"],
                "alternatives": resolution["alternatives"],
                "fallback_if_unavailable": resolution["fallback_if_unavailable"],
                "rationale": resolution["rationale"],
            },
            "exams": resolution["exams"],
            "warning_signs": resolution["warning_signs"],
            "patient_message": resolution["patient_message"],
            "economic_logic": resolution["economic_logic"],
            "time_gain_logic": resolution["time_gain_logic"],
            "red_flag_triggered": red_flag_triggered,
            "red_flags_detail": [
                {"flag_id": f["flag_id"], "name": f["name"], "urgency": f["urgency"]}
                for f in triggered_flags
            ],
        }
