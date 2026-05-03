"""
ClairDiag v2.0 — BodySystemDetector
core/body_system_detector.py

Detecte le body_system depuis le texte patient.
Utilise symptoms_rules.json (triggers, negation_markers, minimization_markers, escalation_markers).
Aucune logique medicale hardcodee.
"""

import logging
import re
from collections import Counter
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}


def _normalize(text: str) -> str:
    text = text.lower()
    for ch in ["\u2019", "\u2018", "\u02bc"]:
        text = text.replace(ch, "'")
    text = re.sub(r"[^\w\s\u00c0-\u024f\-']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_negated(text: str, trigger: str, negation_markers: List[str], window: int = 30) -> bool:
    idx = text.find(trigger)
    if idx == -1:
        return False
    prefix = text[max(0, idx - window):idx]
    return any(neg in prefix for neg in negation_markers)


class BodySystemDetector:
    """
    Detecte le body_system dominant via triggers du JSON.
    Respecte negation, minimization, escalation markers.

    Retourne:
    {
        "dominant_system": str | None,
        "body_zone": str | None,
        "matched_symptoms": [{"symptom_id": ..., "trigger": ..., "body_system": ..., "body_zone": ...}],
        "system_scores": {"cardio": 6, ...},
        "confidence": "high" | "medium" | "low" | "none",
        "all_detected_systems": [...],
        "minimization_detected": bool,
        "escalation_detected": bool,
    }
    """

    def __init__(self, symptoms_rules: Optional[Dict] = None):
        if not symptoms_rules:
            self._symptoms = []
            self._negation_markers = []
            self._minimization_markers = []
            self._escalation_markers = []
            self._trigger_index = {}
            logger.warning("BodySystemDetector: no symptoms rules")
            return

        self._symptoms = symptoms_rules.get("symptoms", [])
        self._negation_markers = symptoms_rules.get("negation_markers", [
            "pas de", "pas d", "aucun", "aucune", "sans", "jamais"
        ])
        self._minimization_markers = symptoms_rules.get("minimization_markers", [])
        self._escalation_markers = symptoms_rules.get("escalation_markers", [])

        # Build trigger index: trigger_text -> (symptom_id, body_system, body_zone, severity)
        self._trigger_index: Dict[str, Tuple] = {}
        for s in self._symptoms:
            sid = s.get("symptom_id", "")
            system = s.get("body_system", "")
            zone = s.get("body_zone")
            severity = s.get("default_severity", "low")
            for trig in s.get("triggers", []):
                trig_lower = trig.lower()
                if trig_lower not in self._trigger_index:
                    self._trigger_index[trig_lower] = (sid, system, zone, severity)

        logger.info(
            f"BodySystemDetector: {len(self._symptoms)} symptoms, "
            f"{len(self._trigger_index)} triggers indexed"
        )

    def detect(self, text: str, patient_context: Optional[Dict] = None) -> Dict:
        text_norm = _normalize(text)
        system_scores: Counter = Counter()
        matched: Dict[str, Dict] = {}  # symptom_id -> best match

        # Sort triggers longest first (greedy)
        for trig in sorted(self._trigger_index, key=len, reverse=True):
            if trig not in text_norm:
                continue
            if _is_negated(text_norm, trig, self._negation_markers):
                continue

            sid, system, zone, severity = self._trigger_index[trig]
            weight = SEVERITY_WEIGHT.get(severity, 1)

            # Keep longest trigger per symptom_id
            if sid not in matched or len(trig) > len(matched[sid]["trigger"]):
                matched[sid] = {
                    "symptom_id": sid,
                    "trigger": trig,
                    "body_system": system,
                    "body_zone": zone,
                    "severity": severity,
                }
                system_scores[system] += weight

        matched_list = list(matched.values())

        # Detect minimization & escalation
        minimization = any(m in text_norm for m in self._minimization_markers)
        escalation = any(m in text_norm for m in self._escalation_markers)

        dominant = system_scores.most_common(1)[0][0] if system_scores else None
        all_systems = [s for s, _ in system_scores.most_common()]

        # Body zone: zone du symptome dominant le plus severe
        body_zone = None
        if dominant:
            dominant_symptoms = [m for m in matched_list if m["body_system"] == dominant]
            dominant_symptoms.sort(key=lambda m: SEVERITY_WEIGHT.get(m["severity"], 1), reverse=True)
            if dominant_symptoms:
                body_zone = dominant_symptoms[0].get("body_zone")

        # Confidence
        score = system_scores.get(dominant, 0) if dominant else 0
        if score >= 6:
            confidence = "high"
        elif score >= 3:
            confidence = "medium"
        elif score >= 1:
            confidence = "low"
        else:
            confidence = "none"

        return {
            "dominant_system": dominant,
            "body_zone": body_zone,
            "matched_symptoms": matched_list,
            "system_scores": dict(system_scores),
            "confidence": confidence,
            "all_detected_systems": all_systems,
            "minimization_detected": minimization,
            "escalation_detected": escalation,
        }

    def is_ready(self) -> bool:
        return len(self._symptoms) > 0