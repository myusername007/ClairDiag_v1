"""
ClairDiag v2.0 — RedFlagsEngine
core/red_flags_engine.py

Évalue les red flags depuis red_flags.json.
Toute la logique de conditions vient du JSON — zéro hardcoding médical.

Structure des conditions supportées:
  {"feature": "symptoms", "contains": "symptom_id"}
  {"feature": "demographics.age", "gte": 50}
  {"feature": "demographics.sex", "eq": "M"}
  {"feature": "risk_factors", "contains": "HTA"}
  {"feature": "context_flags", "contains": "chute_recente"}
  {"any_of": [...]}
  {"all_of": [...]}
  {"any_of_count_gte": N, "any_of": [...]}
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Urgency priority order (du plus urgent au moins urgent)
URGENCY_ORDER = ["urgent", "urgent_medical_review", "medical_consultation", "non_urgent"]


def _urgency_rank(level: str) -> int:
    try:
        return URGENCY_ORDER.index(level)
    except ValueError:
        return len(URGENCY_ORDER)


def _get_feature_value(feature_path: str, patient_data: Dict) -> Any:
    """
    Extrait une valeur depuis patient_data selon le chemin feature.
    Exemples:
        "symptoms" → patient_data["symptoms"] (list)
        "demographics.age" → patient_data["demographics"]["age"]
        "risk_factors" → patient_data["risk_factors"] (list)
        "context_flags" → patient_data["context_flags"] (list)
    """
    parts = feature_path.split(".")
    value = patient_data
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _evaluate_condition(condition: Dict, patient_data: Dict) -> bool:
    """
    Évalue récursivement une condition JSON.
    Retourne True si la condition est satisfaite.
    """
    # Cas: all_of
    if "all_of" in condition:
        return all(_evaluate_condition(c, patient_data) for c in condition["all_of"])

    # Cas: any_of simple
    if "any_of" in condition and "any_of_count_gte" not in condition:
        return any(_evaluate_condition(c, patient_data) for c in condition["any_of"])

    # Cas: any_of_count_gte N (au moins N conditions satisfaites)
    if "any_of_count_gte" in condition and "any_of" in condition:
        min_count = condition["any_of_count_gte"]
        count = sum(1 for c in condition["any_of"] if _evaluate_condition(c, patient_data))
        return count >= min_count

    # Cas: feature simple
    feature = condition.get("feature")
    if feature is None:
        return False

    value = _get_feature_value(feature, patient_data)

    # Opérateur: contains (pour lists)
    if "contains" in condition:
        target = condition["contains"]
        if isinstance(value, list):
            return target in value
        return False

    # Opérateur: eq
    if "eq" in condition:
        return value == condition["eq"]

    # Opérateur: gte (>=)
    if "gte" in condition:
        try:
            return float(value) >= float(condition["gte"])
        except (TypeError, ValueError):
            return False

    # Opérateur: lte (<=)
    if "lte" in condition:
        try:
            return float(value) <= float(condition["lte"])
        except (TypeError, ValueError):
            return False

    # Opérateur: in (valeur dans liste)
    if "in" in condition:
        return value in condition["in"]

    return False


class RedFlagsEngine:
    """
    Évalue les red flags depuis red_flags.json contre les données patient.

    patient_data structure attendue:
    {
        "symptoms": ["symptom_id_1", "symptom_id_2", ...],
        "demographics": {
            "age": int | None,
            "sex": "M" | "F" | None,
            "pregnancy_status": str | None,
            "pregnancy_trimester": int | None,
        },
        "risk_factors": ["HTA", "diabete", ...],
        "context_flags": ["chute_recente", "trauma_recent", ...],
        "temporal": {
            "onset_speed": "brutal" | "rapid" | "progressive" | "chronic" | None,
        },
    }
    """

    def __init__(self, red_flags_rules: List[Dict]):
        """
        Args:
            red_flags_rules: liste depuis red_flags.json["red_flags"]
        """
        self._flags = red_flags_rules
        # Override flags (psychiatrie_suicide)
        self._override_flags = [f for f in self._flags if f.get("override_all_other_logic")]
        logger.info(f"RedFlagsEngine: {len(self._flags)} flags, "
                    f"{len(self._override_flags)} override flags")

    def evaluate(self, patient_data: Dict) -> Dict:
        """
        Évalue tous les red flags contre les données patient.

        Returns:
            {
                "triggered": bool,
                "override_triggered": bool,
                "triggered_flags": [{"flag_id": ..., "name": ..., "urgency": ..., "rationale": ...}],
                "highest_urgency": str,
                "body_systems_flagged": [str],
            }
        """
        triggered_flags = []

        # 1. Vérifier override flags en premier (psychiatrie_suicide)
        for flag in self._override_flags:
            conditions = flag.get("conditions", {})
            if _evaluate_condition(conditions, patient_data):
                triggered_flags.append({
                    "flag_id": flag["flag_id"],
                    "name": flag["name"],
                    "body_system": flag.get("body_system"),
                    "severity": flag.get("severity"),
                    "urgency": flag.get("triggers_urgency", "urgent"),
                    "rationale": flag.get("rationale", ""),
                    "override": True,
                })
                # Override = retourner immédiatement sans évaluer le reste
                return {
                    "triggered": True,
                    "override_triggered": True,
                    "triggered_flags": triggered_flags,
                    "highest_urgency": "urgent",
                    "body_systems_flagged": [flag.get("body_system")],
                }

        # 2. Évaluer tous les autres flags
        for flag in self._flags:
            if flag.get("override_all_other_logic"):
                continue  # Déjà traités
            conditions = flag.get("conditions", {})
            try:
                if _evaluate_condition(conditions, patient_data):
                    triggered_flags.append({
                        "flag_id": flag["flag_id"],
                        "name": flag["name"],
                        "body_system": flag.get("body_system"),
                        "severity": flag.get("severity"),
                        "urgency": flag.get("triggers_urgency", "urgent"),
                        "rationale": flag.get("rationale", ""),
                        "override": False,
                    })
            except Exception as e:
                logger.warning(f"Red flag evaluation error for {flag.get('flag_id')}: {e}")

        # 3. Déterminer l'urgence la plus haute
        if triggered_flags:
            highest = min(
                triggered_flags,
                key=lambda f: _urgency_rank(f["urgency"])
            )["urgency"]
        else:
            highest = "non_urgent"

        systems_flagged = list({f["body_system"] for f in triggered_flags if f.get("body_system")})

        return {
            "triggered": len(triggered_flags) > 0,
            "override_triggered": False,
            "triggered_flags": triggered_flags,
            "highest_urgency": highest,
            "body_systems_flagged": systems_flagged,
        }
