"""
ClairDiag v2.0 — LearningFeedbackModule (S9)
core/learning_feedback_module.py

Ingère les événements de feedback, les route vers les bonnes queues.
JAMAIS de mutation des fichiers de règles — principe inviolable.
"""

import logging
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VALID_EVENT_TYPES = {"patient_outcome", "physician_feedback", "user_rating"}
VALID_OUTCOME_LABELS = {"improved", "unchanged", "worsened", "hospitalized", "emergency"}
VALID_AGREEMENT_LABELS = {"agree", "partial_disagree", "disagree"}


def _get_feature_value(feature_path: str, event: Dict) -> Any:
    """Résout un chemin de feature dans l'événement (identique red_flags_engine)."""
    parts = feature_path.split(".")
    value = event
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _evaluate_routing_condition(condition: Dict, event: Dict) -> bool:
    """Évalue une condition de routing (même logique que red_flags_engine)."""
    if "all_of" in condition:
        return all(_evaluate_routing_condition(c, event) for c in condition["all_of"])
    if "any_of" in condition and "any_of_count_gte" not in condition:
        return any(_evaluate_routing_condition(c, event) for c in condition["any_of"])

    feature = condition.get("feature")
    if not feature:
        return False
    value = _get_feature_value(feature, event)

    if "eq" in condition:
        return value == condition["eq"]
    if "in" in condition:
        return value in condition["in"]
    if "contains" in condition:
        return condition["contains"] in (value or [])
    return False


@dataclass
class FeedbackEvent:
    event_id: str
    session_id: str
    timestamp: str
    event_type: str
    payload: Dict
    queue: str
    ingested_at: str


@dataclass
class IngestResult:
    success: bool
    event_id: Optional[str] = None
    queue: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)


class LearningFeedbackModule:
    """
    Module de feedback asynchrone.

    Principe absolu: ce module NE MODIFIE JAMAIS les fichiers de règles.
    Il ingère, valide, route, et stocke dans une queue.

    Usage:
        result = module.ingest({
            "session_id": "abc-123",
            "type": "physician_feedback",
            "payload": {
                "payload": {
                    "physician_feedback": {"agreement": "disagree"},
                }
            }
        })
        # result.queue = "reviewer_queue_high_priority"
    """

    NO_AUTO_UPDATE_RULE = (
        "The engine MUST NOT modify any rule file based on feedback automatically. "
        "All feedback events must be reviewed and validated by a human."
    )

    def __init__(
        self,
        feedback_schema: Optional[Dict] = None,
        queue_backend=None,
    ):
        if not feedback_schema:
            self._routing_rules = []
            self._schema = {}
            logger.warning("LearningFeedbackModule: no schema provided")
        else:
            self._schema = feedback_schema
            self._routing_rules = feedback_schema.get("queue_routing", [])

        # Queue backend: en production Redis/SQS/Postgres.
        # En développement: liste en mémoire.
        self._queue_backend = queue_backend
        self._memory_queue: List[FeedbackEvent] = []  # fallback si pas de backend

        logger.info(
            f"LearningFeedbackModule: {len(self._routing_rules)} routing rules. "
            f"NO_AUTO_UPDATE enforced."
        )

    def ingest(self, event: Dict) -> IngestResult:
        """
        Valide et route un événement de feedback.

        L'événement doit contenir: type, payload (et optionnellement session_id).
        Retourne IngestResult avec event_id et queue destination.
        """
        errors = self._validate(event)
        if errors:
            return IngestResult(success=False, validation_errors=errors)

        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Enrichir l'événement
        enriched = {**event, "event_id": event_id, "timestamp": now}

        # Routing
        queue = self._route(enriched)

        feedback_event = FeedbackEvent(
            event_id=event_id,
            session_id=event.get("session_id", "unknown"),
            timestamp=now,
            event_type=event.get("type", "unknown"),
            payload=event.get("payload", {}),
            queue=queue,
            ingested_at=now,
        )

        self._store(feedback_event)
        logger.info(f"Feedback ingested: {event_id} -> {queue}")

        return IngestResult(success=True, event_id=event_id, queue=queue)

    def _validate(self, event: Dict) -> List[str]:
        """Validation minimale — retourne liste d'erreurs."""
        errors = []
        if not isinstance(event, dict):
            return ["event must be a dict"]

        event_type = event.get("type")
        if not event_type:
            errors.append("type is required")
        elif event_type not in VALID_EVENT_TYPES:
            errors.append(f"type '{event_type}' not in {VALID_EVENT_TYPES}")

        payload = event.get("payload")
        if payload is None:
            errors.append("payload is required")

        return errors

    def _route(self, event: Dict) -> str:
        """
        Évalue les routing_rules dans l'ordre.
        Premier match -> queue correspondante.
        Fallback: reviewer_queue_low_priority.
        """
        for rule in self._routing_rules:
            try:
                if _evaluate_routing_condition(rule.get("when", {}), event):
                    return rule["queue"]
            except Exception as e:
                logger.warning(f"Routing rule error {rule.get('rule_id')}: {e}")
        return "reviewer_queue_low_priority"

    def _store(self, event: FeedbackEvent) -> None:
        """
        Stocke l'événement.
        En production: push vers queue_backend.
        En dev: stockage mémoire.
        JAMAIS de modification de fichiers de règles.
        """
        if self._queue_backend is not None:
            try:
                self._queue_backend.push(event.queue, vars(event))
            except Exception as e:
                logger.error(f"Queue backend error: {e}. Falling back to memory.")
                self._memory_queue.append(event)
        else:
            self._memory_queue.append(event)

    def stats(self, since: Optional[datetime] = None) -> Dict:
        """
        Statistiques agrégées depuis la queue mémoire.
        En production: requête sur le backend.
        """
        events = self._memory_queue
        if since:
            events = [e for e in events if e.ingested_at >= since.isoformat()]

        by_type: Dict[str, int] = {}
        by_queue: Dict[str, int] = {}

        for e in events:
            by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
            by_queue[e.queue] = by_queue.get(e.queue, 0) + 1

        return {
            "total_events": len(events),
            "by_type": by_type,
            "by_queue": by_queue,
            "no_auto_update_rule": self.NO_AUTO_UPDATE_RULE,
        }

    def queue_size(self) -> int:
        """Taille de la queue mémoire (pour tests)."""
        return len(self._memory_queue)

    def is_ready(self) -> bool:
        return len(self._routing_rules) > 0