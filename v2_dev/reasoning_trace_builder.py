"""
ClairDiag v2 — Reasoning Trace Builder
Структурує існуючі дані pipeline у формат reasoning_trace.

ПРАВИЛО: NO new medical logic — тільки реструктурування існуючих даних.
"""

from typing import Optional


def build_reasoning_trace(
    v1_output: dict,
    etape1_output: dict,
    full_result: dict,
) -> dict:
    """
    Будує reasoning_trace з існуючих полів pipeline.

    Джерела даних:
    - v1_output:     symptoms_normalized, red_flags, final_action_v1
    - etape1_output: top_hypothesis, secondary_hypotheses, exclude_priority,
                     confidence_level, reasoning_summary, clinical_group
    - full_result:   recommended_tests, next_step_logic, safety_floor,
                     medical_orientation_v2
    """

    symptoms        = v1_output.get("symptoms_normalized", [])
    red_flags       = v1_output.get("red_flags", [])
    final_action    = v1_output.get("final_action_v1", "")

    top_hypothesis  = etape1_output.get("top_hypothesis")
    secondary       = etape1_output.get("secondary_hypotheses", [])
    exclude         = etape1_output.get("exclude_priority", [])
    confidence      = etape1_output.get("confidence_level", "faible")
    reasoning_raw   = etape1_output.get("reasoning_summary", [])
    clinical_group  = etape1_output.get("clinical_group")

    logic_mode      = full_result.get("next_step_logic", "")
    safety_floor    = full_result.get("safety_floor", {})
    tests           = full_result.get("recommended_tests", [])
    orientation     = full_result.get("medical_orientation_v2", "")

    # ── 1. Red flags ──────────────────────────────────────────────────────────
    red_flags_trace = []
    if red_flags:
        red_flags_trace.extend([f"v1 red flag: {rf}" for rf in red_flags])

    sf_flags = safety_floor.get("matched_flags", []) if isinstance(safety_floor, dict) else []
    for sf in sf_flags:
        label = sf.get("label") or sf.get("trigger_key", "")
        matched = sf.get("matched_symptom", "")
        red_flags_trace.append(f"safety floor: {label} (symptôme: {matched})")

    if not red_flags_trace:
        red_flags_trace.append("aucun red flag détecté")

    # ── 2. Dominant patterns ──────────────────────────────────────────────────
    dominant_patterns = []
    # Беремо перші 3 елементи reasoning_summary що не є safety floor
    for r in reasoning_raw:
        if "safety floor" not in r and "red flags" not in r:
            dominant_patterns.append(r)
        if len(dominant_patterns) >= 3:
            break

    if clinical_group:
        dominant_patterns.insert(0, f"groupe clinique: {clinical_group}")

    if not dominant_patterns:
        dominant_patterns.append(f"symptômes: {', '.join(symptoms[:3])}" if symptoms else "données insuffisantes")

    # ── 3. Danger hypotheses ──────────────────────────────────────────────────
    danger_hypotheses = []
    if exclude:
        danger_hypotheses.extend([f"à exclure: {e}" for e in exclude])
    if top_hypothesis and any(kw in top_hypothesis for kw in ["sca", "avc", "embolie", "sepsis"]):
        danger_hypotheses.insert(0, f"hypothèse principale dangereuse: {top_hypothesis}")

    if not danger_hypotheses:
        danger_hypotheses.append("aucune hypothèse de danger prioritaire")

    # ── 4. Why not top1 ───────────────────────────────────────────────────────
    why_not_top1 = []
    if secondary:
        why_not_top1.append(
            f"hypothèses alternatives présentes: {', '.join(secondary)}"
        )
    if confidence == "faible":
        why_not_top1.append("score insuffisant pour discrimination claire")
    elif confidence == "modéré":
        why_not_top1.append("différentiel possible — confirmation par examens recommandée")

    if not why_not_top1:
        why_not_top1.append("top_hypothesis fortement discriminée par les symptômes")

    # ── 5. Urgency justification ──────────────────────────────────────────────
    urgency_justification = []

    _ORIENTATION_LABELS = {
        "urgent_emergency_workup":           "URGENCE — bilan immédiat requis",
        "urgent_medical_review_with_tests":  "Consultation urgente avec examens",
        "medical_review_with_targeted_tests":"Consultation médicale + examens ciblés",
        "supportive_followup":               "Suivi simple — pas d'urgence",
        "insufficient_data":                 "Données insuffisantes — orientation impossible",
    }

    if orientation:
        urgency_justification.append(_ORIENTATION_LABELS.get(orientation, orientation))

    if "EMERGENCY" in final_action.upper():
        urgency_justification.append("v1: action d'urgence déclenchée")

    sf_changes = safety_floor.get("changes", []) if isinstance(safety_floor, dict) else []
    urgency_justification.extend(sf_changes)

    if not urgency_justification:
        urgency_justification.append("orientation basée sur profil symptomatique")

    # ── 6. Test justification ─────────────────────────────────────────────────
    test_justification = []
    if logic_mode:
        _MODE_LABELS = {
            "exclude_danger_first": "stratégie: exclure danger en premier",
            "urgent_parallel":      "stratégie: bilan urgent parallèle",
            "confirm_top_first":    "stratégie: confirmer hypothèse principale",
            "insufficient_data":    "données insuffisantes — pas de stratégie définie",
        }
        test_justification.append(_MODE_LABELS.get(logic_mode, f"mode: {logic_mode}"))

    for t in tests[:3]:
        reason = t.get("reason", "")
        test_name = t.get("test", "")
        priority = t.get("priority", "")
        if reason and test_name:
            test_justification.append(f"{test_name} [{priority}]: {reason}")

    if not test_justification:
        test_justification.append("aucun examen recommandé")

    return {
        "red_flags":            red_flags_trace,
        "dominant_patterns":    dominant_patterns,
        "danger_hypotheses":    danger_hypotheses,
        "why_not_top1":         why_not_top1,
        "urgency_justification":urgency_justification,
        "test_justification":   test_justification,
    }