"""
ClairDiag v3 — Adaptive Follow-up Questions Engine

Module: followup_engine
Version: v1.0
Date: 2026-04-30

Inspiré de Ada Health (lite version, sans Bayesian inference).

PRINCIPE:
- Si premier passage donne confidence < 5 OU category = general_vague
  OU fallback_used = True → activer follow-up.
- Présenter 3 questions ciblées maximum.
- Réponses modifient urgency, category, ou specialist.
- Maximum 2 rounds de questions (3 + 3 = 6 questions max).

INTÉGRATION:
1. Endpoint actuel: POST /v3/analyze
2. Nouveau endpoint: POST /v3/analyze/followup
   Body: {
     "session_id": "uuid",
     "round": 1 | 2,
     "answers": [{"qid": "DERM-Q1", "tag": "duration_acute"}, ...]
   }
3. Output: same schema que /v3/analyze, avec champ "followup_completed": true

NE CASSE PAS la régression:
- Si confidence >= 5 et category != vague → pas de follow-up déclenché
- Tous les 90 cases existants doivent passer sans changement de comportement
"""

import json
import uuid
from typing import Optional
from pathlib import Path

# CONFIG_PATH: JSON est dans data/ à côté de followup_engine.py
CONFIG_PATH = Path(__file__).parent / "data" / "followup_questions_v1.json"


# ============================================================
# 1. Loader
# ============================================================

class FollowupConfig:
    """Charge le JSON de configuration des questions au démarrage."""

    def __init__(self, config_path: Path = CONFIG_PATH):
        with open(config_path, encoding="utf-8") as f:
            self.config = json.load(f)
        self.questions_by_category = self.config["questions_by_category"]
        self.global_safety = self.config["global_safety_questions"]
        self.trigger_conditions = self.config["meta"]["trigger_conditions"]
        self.max_questions = self.config["meta"]["max_questions_per_round"]
        self.max_rounds = self.config["meta"]["max_rounds"]


# ============================================================
# 2. Trigger logic
# ============================================================

def should_trigger_followup(v3_response: dict) -> bool:
    """
    Décide si le follow-up doit être activé après le premier passage v3.

    Args:
        v3_response: dict — la réponse complète de /v3/analyze (après _flatten)

    Returns:
        True si follow-up à activer, False sinon.
    """
    # Pas de follow-up si urgent déjà détecté (safety prime)
    final_triage = v3_response.get("final_triage") or v3_response.get("urgency")
    if final_triage in ("urgent", "medical_urgent"):
        return False

    # Pas de follow-up si red flag déjà détecté
    if v3_response.get("red_flag_triggered"):
        return False

    # Activer si confidence basse
    # Support both flat (after _flatten) and nested confidence_detail
    confidence_detail = v3_response.get("confidence_detail") or v3_response.get("confidence", {})
    if isinstance(confidence_detail, dict):
        confidence = confidence_detail.get("score", 10)
    else:
        confidence = 10

    if confidence < 5:
        return True

    # Activer si catégorie vague
    # Support both flat general_orientation and nested clinical
    general_orientation = (
        v3_response.get("general_orientation")
        or (v3_response.get("clinical") or {}).get("general_orientation")
        or {}
    )
    category = general_orientation.get("category") if isinstance(general_orientation, dict) else None
    if category == "general_vague_non_specifique" or category == "general_vague":
        return True

    # Activer si fallback utilisé
    if v3_response.get("fallback_used"):
        return True

    # Activer si seulement 1 expression matchée ET confidence non-élevée
    matched_count = v3_response.get("matched_expressions_count")
    if matched_count is not None and matched_count <= 1 and confidence < 7:
        return True

    return False


# ============================================================
# 3. Question selection
# ============================================================

def select_questions_for_round(
    config: FollowupConfig,
    category: str,
    round_number: int,
    previous_answers: list,
    patient_context: dict,
) -> list:
    """
    Sélectionne jusqu'à max_questions_per_round questions à poser.

    Logique:
    - Round 1: questions safety_critical + always_ask_first en priorité
    - Round 2: questions restantes basées sur les réponses round 1
    - Skip questions déjà répondues
    - Inclure global_safety si âge / contexte le demande
    """
    answered_qids = {a["qid"] for a in previous_answers}

    # Récupérer les questions pour cette catégorie
    category_questions = config.questions_by_category.get(category, [])
    if not category_questions:
        # Fallback sur general_vague si catégorie non reconnue
        category_questions = config.questions_by_category.get(
            "general_vague_non_specifique", []
        )

    candidates = [q for q in category_questions if q["qid"] not in answered_qids]

    if round_number == 1:
        # 1. always_ask_first en premier (ex: idéation suicidaire dans stress)
        always_first = [q for q in candidates if q.get("always_ask_first")]
        # 2. safety_critical
        safety = [
            q for q in candidates
            if q.get("safety_critical") and not q.get("always_ask_first")
        ]
        # 3. autres
        normal = [
            q for q in candidates
            if not q.get("safety_critical") and not q.get("always_ask_first")
        ]
        ordered = always_first + safety + normal
    else:
        # Round 2: questions restantes selon ordre original
        ordered = candidates

    selected = ordered[:config.max_questions]

    # Ajouter questions globales selon contexte (uniquement round 1)
    if round_number == 1:
        for global_q in config.global_safety:
            if global_q["qid"] in answered_qids:
                continue
            if global_q.get("always_check"):
                if global_q not in selected:
                    selected.append(global_q)
            elif "always_check_if_age_over" in global_q:
                age = (patient_context or {}).get("age")
                if age and age > global_q["always_check_if_age_over"]:
                    if global_q not in selected:
                        selected.append(global_q)

    return selected[:config.max_questions]


# ============================================================
# 4. Apply answers to v3 response
# ============================================================

def apply_followup_answers(
    config: FollowupConfig,
    v3_response: dict,
    answers: list,
    category: str,
) -> dict:
    """
    Applique les modifications au v3_response selon les answers.

    Returns:
        v3_response modifié avec:
        - urgency potentiellement élevée
        - specialist potentiellement précisé
        - red_flag_triggered si trigger_red_flag rencontré
        - followup_applied = True
    """
    response = dict(v3_response)  # shallow copy
    response["followup_applied"] = True
    response["followup_completed"] = True
    response["followup_modifications"] = []

    # Récupérer toutes les questions de la catégorie pour lookup
    all_questions = (
        config.questions_by_category.get(category, [])
        + config.global_safety
    )
    questions_index = {q["qid"]: q for q in all_questions}

    urgency_levels = ["non_urgent", "medical_consultation", "urgent_medical_review", "medical_urgent", "urgent"]

    def severity(level: str) -> int:
        try:
            return urgency_levels.index(level)
        except ValueError:
            return 0

    for answer in answers:
        qid = answer["qid"]
        tag = answer["tag"]
        question = questions_index.get(qid)
        if not question:
            continue

        # Trouver l'option choisie
        option = None
        for opt in question.get("answer_options", []):
            if opt["tag"] == tag:
                option = opt
                break
        if not option:
            continue

        # OVERRIDE_ALL — idéation suicidaire et autres absolus
        if option.get("override_all"):
            response["final_triage"] = "urgent"
            response["urgency"] = "urgent"
            response["red_flag_triggered"] = True
            response["specialist_override"] = option.get("specialist", "3114")
            response["specific_message"] = option.get("specific_message")
            response["followup_modifications"].append({
                "qid": qid,
                "action": "override_all",
                "reason": "safety_critical_answer",
            })
            return response

        # Modifier urgency si plus sévère que actuelle
        if option.get("modifies") == "urgency":
            new_urgency = option.get("to")
            # Support both flat and nested
            current_urgency = (
                response.get("final_triage")
                or response.get("urgency")
                or (response.get("triage") or {}).get("urgency")
                or "non_urgent"
            )
            if severity(new_urgency) > severity(current_urgency):
                response["final_triage"] = new_urgency
                response["urgency"] = new_urgency
                response["followup_modifications"].append({
                    "qid": qid,
                    "action": "urgency_raised",
                    "from": current_urgency,
                    "to": new_urgency,
                })

        # Modifier category (cas vague → précision)
        if option.get("modifies") == "category":
            response["category_refined_to"] = option.get("to")
            response["followup_modifications"].append({
                "qid": qid,
                "action": "category_refined",
                "to": option.get("to"),
            })

        # Specialist hint
        if option.get("specialist"):
            response["specialist_hint"] = option["specialist"]

        # Trigger red flag
        if option.get("trigger_red_flag"):
            response["red_flag_triggered"] = True
            response["followup_modifications"].append({
                "qid": qid,
                "action": "red_flag_triggered",
                "reason": tag,
            })

        # Note clinique (ex: "Hyperthyroïdie à exclure avant anxiété")
        if option.get("note"):
            notes = response.setdefault("clinical_notes", [])
            notes.append(option["note"])

    return response


# ============================================================
# 5. Main API entry points
# ============================================================

class FollowupEngine:
    """Façade simple à intégrer dans routes_v3.py."""

    def __init__(self, config: Optional[FollowupConfig] = None):
        self.config = config or FollowupConfig()
        self._sessions = {}  # session_id → state. Production: Redis.

    def initiate_followup(self, v3_response: dict, patient_context: dict) -> dict:
        """
        Premier passage: si follow-up nécessaire, retourner les questions du round 1.

        Returns:
        {
          "followup_needed": bool,
          "session_id": str | None,
          "round": 1,
          "questions": [...]
          # Ou si followup_needed=False, retour direct du v3_response
        }
        """
        if not should_trigger_followup(v3_response):
            return {
                "followup_needed": False,
                **v3_response,
            }

        session_id = str(uuid.uuid4())

        # Support both flat and nested
        general_orientation = (
            v3_response.get("general_orientation")
            or (v3_response.get("clinical") or {}).get("general_orientation")
            or {}
        )
        category = (
            (general_orientation.get("category") if isinstance(general_orientation, dict) else None)
            or "general_vague_non_specifique"
        )

        questions = select_questions_for_round(
            self.config,
            category=category,
            round_number=1,
            previous_answers=[],
            patient_context=patient_context or {},
        )

        self._sessions[session_id] = {
            "v3_response": v3_response,
            "category": category,
            "patient_context": patient_context or {},
            "answers": [],
            "round": 1,
        }

        return {
            "followup_needed": True,
            "session_id": session_id,
            "round": 1,
            "questions": questions,
            "max_rounds": self.config.max_rounds,
        }

    def submit_answers(self, session_id: str, round_number: int, answers: list) -> dict:
        """
        Reçoit les réponses, applique les modifications, décide round 2 ou final.

        Returns:
        - Si round 2 nécessaire: même format que initiate_followup avec round=2
        - Si final: v3_response modifié avec followup_applied=True
        """
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "session_not_found"}

        # Accumuler les réponses
        session["answers"].extend(answers)

        # Appliquer maintenant pour voir si urgent déclenché
        modified_response = apply_followup_answers(
            self.config,
            session["v3_response"],
            session["answers"],
            session["category"],
        )

        # Si urgent déclenché ou override_all → fin immédiate
        urgency = modified_response.get("urgency") or modified_response.get("final_triage")
        if urgency == "urgent" or modified_response.get("red_flag_triggered"):
            del self._sessions[session_id]
            return modified_response

        # Si dernier round → fin
        if round_number >= self.config.max_rounds:
            del self._sessions[session_id]
            return modified_response

        # Round 2: questions restantes
        next_questions = select_questions_for_round(
            self.config,
            category=session["category"],
            round_number=round_number + 1,
            previous_answers=session["answers"],
            patient_context=session["patient_context"],
        )

        if not next_questions:
            del self._sessions[session_id]
            return modified_response

        session["round"] = round_number + 1
        return {
            "followup_needed": True,
            "session_id": session_id,
            "round": round_number + 1,
            "questions": next_questions,
            "max_rounds": self.config.max_rounds,
            "preliminary_response": modified_response,
        }