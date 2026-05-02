"""
ClairDiag v2.0 — BodySystemDetector
core/body_system_detector.py

Détecte le body_system dominant à partir du texte patient.
Toute la logique de mapping vient de symptoms_rules.json — zéro hardcoding.
"""

import logging
from collections import Counter
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BodySystemDetector:
    """
    Détecte le body_system dominant via triggers du JSON.

    Principe:
    - Pour chaque symptôme dans symptoms_rules.json, vérifie les triggers dans le texte
    - Accumule les scores par body_system
    - Retourne le système dominant + scores complets

    Aucune règle médicale hardcodée — tout vient du JSON chargé.
    """

    def __init__(self, symptoms_rules: List[Dict]):
        """
        Args:
            symptoms_rules: liste des symptômes depuis symptoms_rules.json["symptoms"]
        """
        self._symptoms = symptoms_rules
        self._trigger_index = self._build_trigger_index()
        logger.info(f"BodySystemDetector: {len(self._symptoms)} symptoms, "
                    f"{len(self._trigger_index)} triggers indexed")

    def _build_trigger_index(self) -> Dict[str, Tuple[str, str, str]]:
        """
        Construit un index trigger → (symptom_id, body_system, default_severity).
        Permet lookup O(n) au lieu de O(n*m).
        """
        index = {}
        for symptom in self._symptoms:
            sid = symptom.get("symptom_id", "")
            system = symptom.get("body_system", "")
            severity = symptom.get("default_severity", "low")
            for trigger in symptom.get("triggers", []):
                trig_lower = trigger.lower()
                if trig_lower not in index:
                    index[trig_lower] = (sid, system, severity)
        return index

    def detect(
        self,
        text: str,
        patient_context: Optional[Dict] = None,
    ) -> Dict:
        """
        Détecte le body_system dominant dans le texte.

        Returns:
            {
                "dominant_system": str | None,
                "matched_symptoms": [{"symptom_id": ..., "body_system": ..., "trigger": ...}],
                "system_scores": {"cardio": 2, "neuro": 1, ...},
                "confidence": "high" | "medium" | "low" | "none",
                "all_detected_systems": [str],
            }
        """
        text_lower = text.lower()
        matched = []
        system_scores: Counter = Counter()

        for trigger, (symptom_id, body_system, severity) in self._trigger_index.items():
            if trigger in text_lower:
                matched.append({
                    "symptom_id": symptom_id,
                    "body_system": body_system,
                    "trigger": trigger,
                    "severity": severity,
                })
                # Poids severity: high=3, medium=2, low=1
                weight = {"high": 3, "medium": 2, "low": 1}.get(severity, 1)
                system_scores[body_system] += weight

        # Déduplication par symptom_id (garder le trigger le plus long = plus précis)
        seen_symptoms = {}
        for m in matched:
            sid = m["symptom_id"]
            if sid not in seen_symptoms or len(m["trigger"]) > len(seen_symptoms[sid]["trigger"]):
                seen_symptoms[sid] = m
        matched_dedup = list(seen_symptoms.values())

        dominant = system_scores.most_common(1)[0][0] if system_scores else None
        all_systems = [s for s, _ in system_scores.most_common()]

        # Confidence basée sur score dominant
        dominant_score = system_scores.get(dominant, 0) if dominant else 0
        if dominant_score >= 6:
            confidence = "high"
        elif dominant_score >= 3:
            confidence = "medium"
        elif dominant_score >= 1:
            confidence = "low"
        else:
            confidence = "none"

        return {
            "dominant_system": dominant,
            "matched_symptoms": matched_dedup,
            "system_scores": dict(system_scores),
            "confidence": confidence,
            "all_detected_systems": all_systems,
        }

    def get_symptoms_for_system(self, body_system: str) -> List[Dict]:
        """Retourne tous les symptômes d'un body_system donné."""
        return [s for s in self._symptoms if s.get("body_system") == body_system]
