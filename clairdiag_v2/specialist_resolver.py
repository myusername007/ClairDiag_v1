"""
ClairDiag v2.0 — SpecialistResolver
core/specialist_resolver.py

Resout le specialiste via routing_rules de specialist_mapping.json.
Supporte body_zone dans les features (ROUTE-CONSULT-MUSCULO-PIED).
Fallback doctrine enforced.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

URGENCY_ORDER = ["urgent", "urgent_medical_review", "medical_consultation", "non_urgent"]


def _eval_node(node: Dict, features: Dict) -> bool:
    """Evaluateur recursif de conditions JSON (identique a red_flags_engine)."""
    if "all_of" in node:
        return all(_eval_node(c, features) for c in node["all_of"])
    if "any_of" in node and "any_of_count_gte" not in node:
        return any(_eval_node(c, features) for c in node["any_of"])
    if "any_of_count_gte" in node:
        n = node["any_of_count_gte"]
        return sum(1 for c in node["any_of"] if _eval_node(c, features)) >= n
    if "not" in node:
        return not _eval_node(node["not"], features)

    feature = node.get("feature")
    if not feature:
        return False

    # Resoudre le chemin (supporte demographics.sex, etc.)
    parts = feature.split(".")
    value = features
    for p in parts:
        if isinstance(value, dict):
            value = value.get(p)
        else:
            value = None
            break

    if "contains" in node:
        return node["contains"] in (value or [])
    if "eq" in node:
        return value == node["eq"]
    if "in" in node:
        return value in node["in"]
    if "gte" in node:
        try:
            return float(value) >= float(node["gte"])
        except (TypeError, ValueError):
            return False
    if "lte" in node:
        try:
            return float(value) <= float(node["lte"])
        except (TypeError, ValueError):
            return False
    return False


class SpecialistResolver:
    """
    Resout le specialiste en appliquant les routing_rules dans l ordre.
    Premier match wins.
    """

    def __init__(self, specialist_mapping: Optional[Dict] = None):
        if not specialist_mapping:
            self._routing_rules = []
            self._specialists = {}
            self._fallback_doctrine = {}
            self._mt_allowed = {"fatigue", "douleur_generale_vague", "infectieux"}
            logger.warning("SpecialistResolver: no mapping provided")
            return

        self._routing_rules = specialist_mapping.get("routing_rules", [])
        self._specialists = specialist_mapping.get("specialists", {})
        self._fallback_doctrine = specialist_mapping.get("fallback_doctrine", {})
        self._mt_allowed = set(
            self._fallback_doctrine.get("mt_allowed_as_primary_for_categories", [])
        )
        logger.info(
            f"SpecialistResolver: {len(self._routing_rules)} routing rules, "
            f"{len(self._specialists)} specialists"
        )

    def resolve(
        self,
        pathway_category: str,
        urgency: str,
        body_zone: Optional[str] = None,
        demographics: Optional[Dict] = None,
        modifier_specialist_override: Optional[str] = None,
    ) -> Dict:
        """
        Resout le specialiste pour une categorie + urgency + body_zone.

        Si modifier_specialist_override est fourni (depuis AnalysisInterpreter),
        il prend priorite sur les routing_rules standard.

        Returns:
            {"primary": str, "alternatives": [str], "fallback": [str],
             "matched_rule": str, "rationale": str, "specialist_info": dict}
        """
        # Override depuis modifier (ex: troponines elevees -> urgences_15)
        if modifier_specialist_override:
            spec_info = self._specialists.get(modifier_specialist_override, {})
            return {
                "primary": modifier_specialist_override,
                "alternatives": [],
                "fallback": [],
                "matched_rule": "MODIFIER_OVERRIDE",
                "rationale": f"Modifier specialist override: {modifier_specialist_override}",
                "specialist_info": spec_info,
                "is_mt_legitimate": False,
            }

        # Construire les features pour l evaluation
        features = {
            "pathway_category": pathway_category,
            "urgency": urgency,
            "body_zone": body_zone,
            "demographics": demographics or {},
        }

        # Evaluer les routing_rules dans l ordre
        for rule in self._routing_rules:
            try:
                if _eval_node(rule.get("when", {}), features):
                    specs = rule.get("specialists", {})
                    primary_list = specs.get("primary", [])
                    primary = primary_list[0] if primary_list else "medecin_traitant"
                    spec_info = self._specialists.get(primary, {})
                    is_mt = primary in ("medecin_traitant", "teleconsultation")
                    return {
                        "primary": primary,
                        "alternatives": specs.get("alternatives", []),
                        "fallback": specs.get("fallback", []),
                        "matched_rule": rule["rule_id"],
                        "rationale": rule.get("rationale", "Routing rule match"),
                        "specialist_info": spec_info,
                        "is_mt_legitimate": is_mt and pathway_category in self._mt_allowed,
                    }
            except Exception as e:
                logger.warning(f"Rule eval error for {rule.get('rule_id')}: {e}")

        # Fallback doctrine
        if pathway_category in self._mt_allowed:
            return {
                "primary": "medecin_traitant",
                "alternatives": ["teleconsultation"],
                "fallback": [],
                "matched_rule": "FALLBACK_DOCTRINE_MT_ALLOWED",
                "rationale": f"MT legitime pour {pathway_category}",
                "specialist_info": self._specialists.get("medecin_traitant", {}),
                "is_mt_legitimate": True,
            }

        # Last resort
        logger.warning(f"No routing rule matched for {pathway_category}/{urgency}/{body_zone}")
        return {
            "primary": "medecin_traitant",
            "alternatives": [],
            "fallback": [],
            "matched_rule": "LAST_RESORT",
            "rationale": "Aucune regle matched — fallback MT",
            "specialist_info": self._specialists.get("medecin_traitant", {}),
            "is_mt_legitimate": False,
        }

    def get_specialist_info(self, specialist_id: str) -> Dict:
        return self._specialists.get(specialist_id, {})

    def is_ready(self) -> bool:
        return len(self._routing_rules) > 0