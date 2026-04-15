# ── Contradiction Guard — v1.1 ────────────────────────────────────────────────
# Élimine les combinaisons impossibles dans le résultat final.
#
# RÈGLES :
#   1. urgency_level == "élevé"   → decision NE PEUT PAS être LOW_RISK_MONITOR
#   2. emergency_flag == True     → decision DOIT être EMERGENCY
#   3. branch min_urgency actif   → urgency_level ne peut pas être en dessous
#   4. RFE high-risk              → LOW_RISK_MONITOR et MEDICAL_REVIEW interdits
#   5. forbid_decisions (branch)  → ces decisions sont interdites
#   6. EMERGENCY / URGENT + 24–48h dans explanation → loggé
#
# VERSION: v1.1 — forbid_decisions support added

from __future__ import annotations
import logging

logger = logging.getLogger("clairdiag.contradiction_guard")

_URGENCY_DECISION_FLOOR: dict[str, list[str]] = {
    "élevé":  ["EMERGENCY", "URGENT_MEDICAL_REVIEW"],
    "modéré": ["EMERGENCY", "URGENT_MEDICAL_REVIEW", "TESTS_REQUIRED", "MEDICAL_REVIEW"],
    "faible": ["EMERGENCY", "URGENT_MEDICAL_REVIEW", "TESTS_REQUIRED", "MEDICAL_REVIEW", "LOW_RISK_MONITOR"],
}

_URGENCY_FALLBACK_DECISION: dict[str, str] = {
    "élevé":  "URGENT_MEDICAL_REVIEW",
    "modéré": "MEDICAL_REVIEW",
}

_FORBIDDEN_DELAY_PHRASES = [
    "dans 24", "dans 48", "24–48h", "24-48h", "48h", "48–72h",
    "surveillance à domicile", "surveiller à domicile", "low_risk_monitor",
]

_FORBIDDEN_REASSURANCE_PHRASES = [
    "pas d'urgence", "aucun signe de gravité", "surveillance suffisante",
    "pas grave", "peut attendre", "dans quelques jours",
]


def check(
    urgency_level: str,
    decision: str,
    emergency_flag: bool,
    branch_min_urgency: str | None,
    explanation: str = "",
    rfe_triggered: bool = False,
    forbid_decisions: set[str] | None = None,
) -> tuple[str, str, str, list[str]]:
    """
    Vérifie et corrige les contradictions dans le résultat final.

    Retourne :
      - urgency_level (str)
      - decision (str)
      - explanation (str)
      - violations (list[str]) — log des corrections
    """
    violations: list[str] = []

    # ── 1. Branch min_urgency override ────────────────────────────────────────
    if branch_min_urgency:
        urgency_level = _upgrade_urgency(urgency_level, branch_min_urgency, violations)

    # ── 2. Emergency flag → force EMERGENCY ───────────────────────────────────
    if emergency_flag and decision != "EMERGENCY":
        violations.append(f"CONTRADICTION: emergency_flag=True + decision={decision} → EMERGENCY")
        decision = "EMERGENCY"
        urgency_level = "élevé"

    # ── 3. RFE urgent (non-emergency) → min URGENT_MEDICAL_REVIEW, max modéré ──
    if rfe_triggered:
        if decision in ("LOW_RISK_MONITOR", "MEDICAL_REVIEW"):
            old_d = decision
            decision = "URGENT_MEDICAL_REVIEW"
            violations.append(f"CONTRADICTION: RFE urgent + decision={old_d} → URGENT_MEDICAL_REVIEW")
        if urgency_level == "faible":
            violations.append("CONTRADICTION: RFE urgent + urgency=faible → modéré")
            urgency_level = "modéré"
        # RFE urgent (non-emergency) ne justifie pas urgency élevé
        if urgency_level == "élevé" and not emergency_flag:
            violations.append("CONTRADICTION: RFE urgent (non-emergency) + urgency=élevé → modéré")
            urgency_level = "modéré"

    # ── 4. Branch forbid_decisions ────────────────────────────────────────────
    if forbid_decisions and decision in forbid_decisions:
        old = decision
        # Remonte au niveau minimum autorisé selon urgency
        decision = _next_allowed_decision(decision, urgency_level, forbid_decisions)
        violations.append(
            f"CONTRADICTION: branch forbids decision={old} → {decision}"
        )

    # ── 5. Urgency / decision floor ───────────────────────────────────────────
    allowed = _URGENCY_DECISION_FLOOR.get(urgency_level, [])
    if allowed and decision not in allowed:
        old = decision
        decision = _URGENCY_FALLBACK_DECISION.get(urgency_level, "MEDICAL_REVIEW")
        violations.append(
            f"CONTRADICTION: urgency={urgency_level} + decision={old} → {decision}"
        )

    # ── 6. Clean explanation ──────────────────────────────────────────────────
    if urgency_level == "élevé" or decision == "EMERGENCY":
        explanation, cleaned = _clean_explanation(explanation, _FORBIDDEN_DELAY_PHRASES)
        for phrase in cleaned:
            violations.append(f"CLEANED delay phrase: '{phrase}'")

    if decision == "EMERGENCY":
        explanation, cleaned = _clean_explanation(explanation, _FORBIDDEN_REASSURANCE_PHRASES)
        for phrase in cleaned:
            violations.append(f"CLEANED reassurance: '{phrase}'")

    if violations:
        for v in violations:
            logger.warning(f"CONTRADICTION GUARD: {v}")

    return urgency_level, decision, explanation, violations


def _upgrade_urgency(current: str, minimum: str, violations: list[str]) -> str:
    _ORDER = {"faible": 0, "modéré": 1, "élevé": 2}
    if _ORDER.get(minimum, 0) > _ORDER.get(current, 0):
        violations.append(f"BRANCH MIN_URGENCY: {current} → {minimum}")
        return minimum
    return current


def _next_allowed_decision(
    current: str,
    urgency_level: str,
    forbid_decisions: set[str],
) -> str:
    """Trouve la prochaine decision autorisée selon urgency floor."""
    _ORDER = [
        "EMERGENCY", "URGENT_MEDICAL_REVIEW", "TESTS_REQUIRED",
        "MEDICAL_REVIEW", "LOW_RISK_MONITOR",
    ]
    allowed_by_urgency = set(_URGENCY_DECISION_FLOOR.get(urgency_level, _ORDER))
    for candidate in _ORDER:
        if candidate not in forbid_decisions and candidate in allowed_by_urgency:
            return candidate
    return "URGENT_MEDICAL_REVIEW"  # fallback safe


def _clean_explanation(text: str, forbidden: list[str]) -> tuple[str, list[str]]:
    found: list[str] = []
    lower = text.lower()
    for phrase in forbidden:
        if phrase in lower:
            found.append(phrase)
    return text, found