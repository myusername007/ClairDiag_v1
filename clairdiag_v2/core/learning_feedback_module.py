"""
ClairDiag v2.0 — LearningFeedbackModule
core/learning_feedback_module.py

Collecte le feedback structuré sur les orientations (pas de ML actif — v2.0).
Stocke les feedbacks pour analyse future.
Schema: learning_feedback_schema.json.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LearningFeedbackModule:
    """
    Collecte et persiste le feedback structuré sur les orientations.

    Version v2.0: feedback collector uniquement (pas ML actif).
    Les données sont stockées pour analyse offline + future intégration ML.

    Schema du feedback:
    {
        "session_id": str,
        "timestamp": str (ISO),
        "input_summary": {"category": str, "urgency": str},
        "orientation_given": {"specialist": str, "urgency": str},
        "feedback_type": "correct" | "too_urgent" | "not_urgent_enough" | "wrong_specialist" | "other",
        "feedback_detail": str | None,
        "patient_outcome": str | None,  # renseigné plus tard si disponible
    }
    """

    def __init__(
        self,
        schema: Optional[Dict] = None,
        storage_path: Optional[Path] = None,
    ):
        self._schema = schema or {}
        self._storage_path = storage_path
        self._buffer: List[Dict] = []
        logger.info("LearningFeedbackModule: initialized (collector mode)")

    def record(
        self,
        session_id: str,
        input_summary: Dict[str, Any],
        orientation_given: Dict[str, Any],
        feedback_type: str,
        feedback_detail: Optional[str] = None,
        patient_outcome: Optional[str] = None,
    ) -> Dict:
        """
        Enregistre un feedback.

        Args:
            session_id: identifiant unique de session
            input_summary: résumé de l input (category, symptoms_count, etc.)
            orientation_given: orientation que le système a donnée
            feedback_type: "correct" | "too_urgent" | "not_urgent_enough" | "wrong_specialist" | "other"
            feedback_detail: texte libre optionnel
            patient_outcome: résultat patient si disponible (renseigné après)

        Returns:
            feedback_record enregistré
        """
        valid_types = {"correct", "too_urgent", "not_urgent_enough", "wrong_specialist", "other"}
        if feedback_type not in valid_types:
            logger.warning(f"Unknown feedback_type: {feedback_type}, using 'other'")
            feedback_type = "other"

        record = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_summary": input_summary,
            "orientation_given": orientation_given,
            "feedback_type": feedback_type,
            "feedback_detail": feedback_detail,
            "patient_outcome": patient_outcome,
        }

        self._buffer.append(record)
        logger.info(f"Feedback recorded: session={session_id}, type={feedback_type}")

        if self._storage_path:
            self._persist(record)

        return record

    def get_stats(self) -> Dict:
        """Retourne les statistiques de feedback collecté (session courante)."""
        if not self._buffer:
            return {"total": 0, "by_type": {}}

        by_type: Dict[str, int] = {}
        for r in self._buffer:
            t = r["feedback_type"]
            by_type[t] = by_type.get(t, 0) + 1

        return {
            "total": len(self._buffer),
            "by_type": by_type,
            "accuracy_rate": by_type.get("correct", 0) / len(self._buffer),
        }

    def _persist(self, record: Dict) -> None:
        """Persiste un record dans le fichier de storage (append JSONL)."""
        try:
            with open(self._storage_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"LearningFeedbackModule persist error: {e}")
