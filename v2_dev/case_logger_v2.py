"""
ClairDiag v2 — Case Logger
Логує кожен кейс у структурований JSON через stdlib logging → stdout → Railway.

Формат: один JSON рядок на запит, парсується будь-яким log aggregator.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

_log = logging.getLogger("clairdiag.v2")


def new_session_id() -> str:
    return f"v2_{uuid.uuid4().hex[:12]}"


def log_v2_case(
    session_id: str,
    v1_input: dict,
    full_result: dict,
    reasoning_trace: dict,
    economic_impact: dict,
    context_flags: list = None,
    scope_status: str = "in_scope",
) -> None:
    """
    Логує повний кейс v2 в stdout (Railway підхоплює автоматично).

    Поля:
    - session_id        унікальний ID сесії
    - timestamp         UTC ISO
    - input             symptoms_normalized + red_flags + final_action_v1
    - output            top_hypothesis, secondary, exclude, confidence, orientation
    - reasoning_trace   структурований trace
    - economic_impact   economic score
    """

    entry = {
        "session_id":   session_id,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "schema":       "clairdiag_v2_case_v1",
        "input": {
            "symptoms_normalized": v1_input.get("symptoms_normalized", []),
            "red_flags":           v1_input.get("red_flags", []),
            "final_action_v1":     v1_input.get("final_action_v1", ""),
        },
        "output": {
            "top_hypothesis":       full_result.get("top_hypothesis"),
            "secondary_hypotheses": full_result.get("secondary_hypotheses", []),
            "exclude_priority":     full_result.get("exclude_priority", []),
            "confidence_level":     full_result.get("confidence_level"),
            "medical_orientation":  full_result.get("medical_orientation_v2"),
            "v2_status":            full_result.get("v2_status"),
            "safety_floor_triggered": (
                full_result.get("safety_floor", {}).get("triggered", False)
                if isinstance(full_result.get("safety_floor"), dict)
                else False
            ),
            "tests": [t.get("test") for t in full_result.get("recommended_tests", [])],
        },
        "reasoning_trace": reasoning_trace,
        "economic_impact": economic_impact,
        "context_flags":   context_flags or [],
        "scope_status":    scope_status,
    }

    _log.info(json.dumps(entry, ensure_ascii=False))


def build_export_case(
    session_id: str,
    v1_input: dict,
    full_result: dict,
    reasoning_trace: dict,
    economic_impact: dict,
) -> dict:
    """
    Будує export-кейс для лікаря (endpoint /v2/export).
    Те саме що log але повертає dict для API response.
    """
    return {
        "session_id":     session_id,
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "input": {
            "symptoms":       v1_input.get("symptoms_normalized", []),
            "red_flags":      v1_input.get("red_flags", []),
            "urgency_v1":     v1_input.get("final_action_v1", ""),
        },
        "output": {
            "top_hypothesis":        full_result.get("top_hypothesis"),
            "secondary_hypotheses":  full_result.get("secondary_hypotheses", []),
            "exclude_priority":      full_result.get("exclude_priority", []),
            "confidence_level":      full_result.get("confidence_level"),
            "medical_orientation":   full_result.get("medical_orientation_v2"),
            "recommended_tests":     full_result.get("recommended_tests", []),
            "safety_floor":          full_result.get("safety_floor", {}),
        },
        "reasoning_trace":  reasoning_trace,
        "economic_impact":  economic_impact,
        "disclaimer": (
            "ClairDiag v2 — outil d'aide à la décision uniquement. "
            "Ne remplace pas l'avis d'un professionnel de santé."
        ),
    }