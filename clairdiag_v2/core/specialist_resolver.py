"""
ClairDiag v2.0 — SpecialistResolver
core/specialist_resolver.py

Résout le spécialiste approprié selon care_pathway_rules.json.
Implémente la fallback doctrine: MT = dernier recours, jamais default si zone identifiable.
Zéro hardcoding médical.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

URGENCY_ORDER = ["urgent", "urgent_medical_review", "medical_consultation", "non_urgent"]


class SpecialistResolver:
    """
    Résout le spécialiste et l orientation à partir des règles JSON.

    Fallback doctrine (depuis global_rules.fallback_doctrine):
    - MT autorisé comme primary uniquement pour: fatigue, douleur_generale_vague, multi_system_no_dominant
    - Pour toute autre catégorie avec zone identifiable → spécialiste direct
    """

    def __init__(self, care_pathway_rules: List[Dict], global_rules: Optional[Dict] = None):
        """
        Args:
            care_pathway_rules: liste depuis care_pathway_rules.json["rules"]
            global_rules: depuis care_pathway_rules.json["global_rules"]
        """
        self._rules = {r["category_id"]: r for r in care_pathway_rules}
        self._global_rules = global_rules or {}
        self._mt_primary_allowed = set(
            self._global_rules.get("fallback_doctrine", {})
            .get("mt_allowed_as_primary_for_categories", ["fatigue", "douleur_generale_vague"])
        )
        logger.info(f"SpecialistResolver: {len(self._rules)} categories loaded")

    def resolve(
        self,
        category_id: str,
        urgency_level: str,
        red_flag_triggered: bool = False,
        red_flag_body_systems: Optional[List[str]] = None,
    ) -> Dict:
        """
        Résout le spécialiste pour une catégorie et un niveau d urgence.

        Returns:
            {
                "primary_recommended": str,
                "alternatives": [str],
                "fallback_if_unavailable": [str],
                "rationale": str,
                "exams": dict,
                "warning_signs": [str],
                "patient_message": str,
                "economic_logic": str,
                "time_gain_logic": str,
                "urgency_level": str,
            }
        """
        rule = self._rules.get(category_id)
        if rule is None:
            logger.warning(f"SpecialistResolver: category '{category_id}' not found in rules")
            return self._minimum_output(category_id, urgency_level)

        specialists = rule.get("specialists", {})
        primary_list = specialists.get("primary", [])
        secondary_list = specialists.get("secondary", [])
        fallback_list = specialists.get("fallback", [])

        # Red flag ou urgence → premier de primary (souvent urgences_15)
        if red_flag_triggered or urgency_level == "urgent":
            recommended = primary_list[0] if primary_list else "urgences_hospitalieres"
            rationale = "Red flag ou urgence — orientation prioritaire vers urgences"
            alternatives = primary_list[1:] + secondary_list
        else:
            # Standard: primary de la catégorie
            if primary_list:
                recommended = primary_list[0]
                alternatives = primary_list[1:] + secondary_list
                rationale = f"Spécialiste de première intention pour {category_id}"
            elif fallback_list:
                recommended = fallback_list[0]
                alternatives = fallback_list[1:]
                rationale = "Fallback légitime (pas de spécialiste primaire défini)"
            else:
                recommended = "medecin_traitant"
                rationale = "Fallback doctrine — aucun spécialiste identifié"
                alternatives = []

        return {
            "primary_recommended": recommended,
            "alternatives": alternatives,
            "fallback_if_unavailable": fallback_list,
            "rationale": rationale,
            "exams": rule.get("exams", {"first_line": ["examen_clinique"], "if_persistent": [], "if_red_flags": []}),
            "warning_signs": rule.get("warning_signs", []),
            "patient_message": rule.get("patient_message", ""),
            "economic_logic": rule.get("economic_logic", ""),
            "time_gain_logic": rule.get("time_gain_logic", ""),
            "urgency_level": urgency_level,
        }

    def get_categories(self) -> List[str]:
        """Retourne la liste de toutes les catégories disponibles."""
        return list(self._rules.keys())

    def _minimum_output(self, category_id: str, urgency_level: str) -> Dict:
        """Output garanti minimum si catégorie inconnue."""
        return {
            "primary_recommended": "medecin_traitant",
            "alternatives": [],
            "fallback_if_unavailable": [],
            "rationale": f"Catégorie '{category_id}' inconnue — fallback doctrine",
            "exams": {"first_line": ["examen_clinique"], "if_persistent": [], "if_red_flags": []},
            "warning_signs": ["Aggravation des symptômes", "Apparition de fièvre", "Douleur intense ou inhabituelle"],
            "patient_message": "Consultez un médecin. Surveillez les signes d aggravation.",
            "economic_logic": "",
            "time_gain_logic": "",
            "urgency_level": urgency_level,
        }
