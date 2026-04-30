"""
ClairDiag v3 — Patient Follow-up Journey Engine

Module: followup_journey_engine
Version: v1.0
Date: 2026-04-30

Inspiré de Infermedica (Follow-up module) — concept, pas implémentation.

PRINCIPE:
1. Après orientation initiale, programmer des check-ins automatisés:
   - J+3: "Vos symptômes ont-ils évolué?"
   - J+7: "Toujours présents? Aggravation?"
2. Si réponse indique aggravation → escalation (re-évaluation v3)
3. Si pas de réponse → fallback rappel ou archive

VALEUR:
- Safety: capture des cas qui se dégradent
- Engagement: patient se sent suivi (vs Ada / Infermedica one-shot)
- Argument économique: re-évaluation = nouvelle valeur
- ARGUMENT MAIRE: démontrable suivi populationnel

INTÉGRATION:
- Endpoint nouveau: POST /v3/followup_journey/schedule
- Endpoint nouveau: POST /v3/followup_journey/checkin
- Backend: scheduler (cron / Celery) qui envoie notifications J+3 et J+7

RGPD:
- Conservation données 30 jours par défaut
- Patient peut refuser follow-up (opt-out facile)
- Ne stocke pas symptômes en clair, juste session_id + schedule + response

NE CASSE PAS la régression:
- Module 100% additif. Pas de modification du pipeline v3 principal.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional


# ============================================================
# 1. Configuration
# ============================================================

FOLLOWUP_SCHEDULES = {
    "standard": {
        "label": "Standard (cas non urgent)",
        "checkpoints_days": [3, 7],
        "description": "Suivi pour symptômes courants : 2 check-ins.",
    },
    "high_risk": {
        "label": "Haut risque (urgent_medical_review, conditions chroniques)",
        "checkpoints_days": [1, 3, 7, 14],
        "description": "Suivi rapproché pour conditions à risque de dégradation.",
    },
    "urgent_post_consultation": {
        "label": "Post-urgences (vérification que patient a consulté)",
        "checkpoints_days": [1, 3],
        "description": "Vérifie que le patient orienté en urgent a effectivement été pris en charge.",
    },
    "minimal": {
        "label": "Minimal (cas simples auto-soin)",
        "checkpoints_days": [7],
        "description": "Un seul check-in à J+7.",
    },
}

CHECKIN_RESPONSES = {
    "better": {
        "label": "Mes symptômes se sont améliorés",
        "action": "close_journey",
        "next_message": "Bonne nouvelle. Si les symptômes reviennent, vous pouvez relancer une orientation.",
    },
    "same": {
        "label": "Mes symptômes sont stables, ni mieux ni pire",
        "action": "continue_journey",
        "next_message": "Continuez la surveillance. Prochain check-in prévu.",
    },
    "worse": {
        "label": "Mes symptômes se sont aggravés",
        "action": "trigger_re_evaluation",
        "next_message": "Une nouvelle évaluation est recommandée. Voulez-vous refaire le questionnaire ?",
    },
    "consulted": {
        "label": "J'ai vu un médecin",
        "action": "close_journey",
        "next_message": "Merci. Si la situation évolue, vous pouvez relancer.",
    },
    "no_response": {
        "label": "(Pas de réponse du patient)",
        "action": "send_reminder",
        "next_message": None,
    },
}

# Mapping urgency → schedule_type recommandé
URGENCY_TO_SCHEDULE = {
    "urgent": "urgent_post_consultation",
    "medical_urgent": "urgent_post_consultation",
    "urgent_medical_review": "high_risk",
    "medical_consultation": "standard",
    "non_urgent": "minimal",
}


# ============================================================
# 2. Schedule creation
# ============================================================

def create_followup_schedule(
    v3_response: dict,
    schedule_type: str = None,
    patient_consent: bool = True,
) -> Optional[dict]:
    """
    Crée un planning de suivi pour un patient après orientation v3.

    Args:
        v3_response: réponse v3 originale (après _flatten ou raw)
        schedule_type: si None, déduit automatiquement de l'urgency
        patient_consent: si False, ne crée pas de schedule (RGPD)

    Returns:
        Dict schedule ou None si pas de consent
    """
    if not patient_consent:
        return None

    # Support both flat (after _flatten) and nested triage
    urgency = (
        v3_response.get("urgency")
        or v3_response.get("final_triage")
        or (v3_response.get("triage") or {}).get("urgency")
        or "non_urgent"
    )

    if schedule_type is None:
        schedule_type = URGENCY_TO_SCHEDULE.get(urgency, "standard")

    if schedule_type not in FOLLOWUP_SCHEDULES:
        return None

    schedule_config = FOLLOWUP_SCHEDULES[schedule_type]
    journey_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)

    # Catégorie depuis general_orientation (support flat et nested)
    general_orientation = v3_response.get("general_orientation") or {}
    category = (
        general_orientation.get("category")
        if isinstance(general_orientation, dict)
        else None
    ) or (v3_response.get("clinical") or {}).get("category")

    checkpoints = []
    for days in schedule_config["checkpoints_days"]:
        checkpoint_date = created_at + timedelta(days=days)
        checkpoints.append({
            "checkpoint_id": str(uuid.uuid4()),
            "scheduled_at": checkpoint_date.isoformat(),
            "days_offset": days,
            "status": "pending",  # pending | sent | answered | missed | cancelled
            "response": None,
            # Roman's required rule-based fields per checkpoint
            "trigger_condition": "symptoms_persist",
            "action_on_worse": "re-evaluate",
            "action_on_better": "close_journey",
            "action_on_same": "continue_monitoring",
        })

    first_delay = schedule_config["checkpoints_days"][0]

    return {
        "journey_id": journey_id,
        "created_at": created_at.isoformat(),
        "schedule_type": schedule_type,
        "schedule_label": schedule_config["label"],
        "category": category,
        "initial_urgency": urgency,
        "checkpoints": checkpoints,
        "status": "active",  # active | closed | escalated | expired
        "expires_at": (created_at + timedelta(days=30)).isoformat(),
        "patient_consent": True,
        # Roman's required top-level rule-based fields
        "follow_up_needed": True,
        "delay_days": first_delay,
        "trigger_condition": "symptoms_persist",
        "action": "re-evaluate",
    }


# ============================================================
# 3. Check-in handling
# ============================================================

def handle_checkin_response(
    journey: dict,
    checkpoint_id: str,
    response: str,
) -> dict:
    """
    Traite la réponse d'un patient à un check-in.

    Args:
        journey: dict journey existant
        checkpoint_id: ID du checkpoint répondu
        response: "better" | "same" | "worse" | "consulted"

    Returns:
        Dict avec journey mis à jour + action recommandée
    """
    if response not in CHECKIN_RESPONSES:
        return {
            "error": "invalid_response",
            "valid_responses": list(CHECKIN_RESPONSES.keys()),
        }

    response_config = CHECKIN_RESPONSES[response]
    action = response_config["action"]
    now = datetime.now(timezone.utc).isoformat()

    # Update checkpoint
    checkpoint_found = False
    for checkpoint in journey["checkpoints"]:
        if checkpoint["checkpoint_id"] == checkpoint_id:
            checkpoint["status"] = "answered"
            checkpoint["response"] = response
            checkpoint["answered_at"] = now
            checkpoint_found = True
            break

    if not checkpoint_found:
        return {"error": "checkpoint_not_found", "checkpoint_id": checkpoint_id}

    # Update journey status
    if action == "close_journey":
        journey["status"] = "closed"
        journey["closed_at"] = now
        journey["closed_reason"] = response

    elif action == "trigger_re_evaluation":
        journey["status"] = "escalated"
        journey["escalated_at"] = now
        journey["escalation_reason"] = "patient_reported_worse"
        # Cancel remaining pending checkpoints
        for checkpoint in journey["checkpoints"]:
            if checkpoint["status"] == "pending":
                checkpoint["status"] = "cancelled"

    return {
        "journey": journey,
        "action_recommended": action,
        "patient_message": response_config["next_message"],
        "trigger_re_evaluation": (action == "trigger_re_evaluation"),
    }


def get_pending_checkpoints(journey: dict, now: datetime = None) -> list:
    """
    Retourne les checkpoints qui doivent être envoyés maintenant.
    À appeler par un cron / scheduler.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if journey["status"] != "active":
        return []

    pending = []
    for checkpoint in journey["checkpoints"]:
        if checkpoint["status"] != "pending":
            continue
        scheduled = datetime.fromisoformat(checkpoint["scheduled_at"])
        # Normalise timezone si nécessaire
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=timezone.utc)
        if now >= scheduled:
            pending.append(checkpoint)
    return pending


def expire_journey_if_needed(journey: dict, now: datetime = None) -> bool:
    """
    Marque un journey comme expiré si dépassé sa date d'expiration.
    Utile pour cleanup RGPD (30 jours).

    Returns: True si expiré, False sinon.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if journey["status"] != "active":
        return False

    expires = datetime.fromisoformat(journey["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if now > expires:
        journey["status"] = "expired"
        journey["expired_at"] = now.isoformat()
        return True
    return False