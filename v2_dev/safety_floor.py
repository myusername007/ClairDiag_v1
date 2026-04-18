"""
ClairDiag v2 — Global Safety Floor

Post-scoring safety layer.
Спрацьовує після основного scoring/reasoning, до final return.

Правило:
  Якщо є хоча б один global red flag trigger:
  - confidence_level не може бути 'faible' (мінімум 'modéré')
  - medical_orientation_v2 не може бути 'supportive_followup' (мінімум 'medical_review_with_targeted_tests')

ПРАВИЛО v1 ЗАЛИШАЄТЬСЯ ГОЛОВНИМ:
  urgent_emergency_workup і urgent_medical_review_with_tests не знижуються.
"""

import json
import os

# ──────────────────────────────────────────────
# РАНЖУВАННЯ
# ──────────────────────────────────────────────

CONFIDENCE_RANK = {
    "faible":  1,
    "modéré":  2,
    "élevé":   3,
}

ORIENTATION_RANK = {
    "insufficient_data":                   0,
    "supportive_followup":                 1,
    "medical_review_with_targeted_tests":  2,
    "urgent_medical_review_with_tests":    3,
    "urgent_emergency_workup":             4,
}

# ──────────────────────────────────────────────
# ЗАВАНТАЖЕННЯ
# ──────────────────────────────────────────────

def load_red_flags_global(path: str = None) -> dict:
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "red_flags_global.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def _matches_trigger(symptom_key: str, trigger: dict) -> bool:
    mode     = trigger.get("match", "exact")
    trig_key = trigger["key"]
    if mode == "prefix":
        return symptom_key.startswith(trig_key)
    return symptom_key == trig_key


def detect_triggered_flags(symptoms: list, config: dict) -> list:
    """
    Повертає список спрацьованих тригерів.
    """
    symptom_keys = set()
    for s in (symptoms or []):
        if isinstance(s, str):
            symptom_keys.add(s.strip())
        elif isinstance(s, dict) and s.get("key"):
            symptom_keys.add(str(s["key"]).strip())

    matched = []
    for trigger in config.get("triggers", []):
        for sk in symptom_keys:
            if _matches_trigger(sk, trigger):
                matched.append({
                    "trigger_key":      trigger["key"],
                    "matched_symptom":  sk,
                    "label":            trigger.get("label", trigger["key"]),
                })
                break  # один тригер — один match

    return matched


def _max_confidence(current: str, minimum: str) -> str:
    cur = CONFIDENCE_RANK.get(current, 1)
    mn  = CONFIDENCE_RANK.get(minimum, 2)
    return minimum if mn > cur else current


def _max_orientation(current: str, minimum: str) -> str:
    cur = ORIENTATION_RANK.get(current, 0)
    mn  = ORIENTATION_RANK.get(minimum, 2)
    return minimum if mn > cur else current

# ──────────────────────────────────────────────
# ГОЛОВНА ФУНКЦІЯ
# ──────────────────────────────────────────────

def apply_global_safety_floor(
    result: dict,
    input_symptoms: list,
    config_path: str = None,
) -> dict:
    """
    Застосовує глобальний safety floor до output v2.

    Вхід:  повний result з run_recommendation_engine()
    Вихід: той самий result, можливо з підвищеним confidence_level
           і medical_orientation_v2

    Поля які може змінити:
      - confidence_level:      faible → modéré (якщо є тригер)
      - medical_orientation_v2: supportive_followup → medical_review_with_targeted_tests

    Поля які НІКОЛИ не знижує:
      - urgent_emergency_workup
      - urgent_medical_review_with_tests
      - élevé confidence
    """

    config        = load_red_flags_global(config_path)
    matched_flags = detect_triggered_flags(input_symptoms, config)

    if not matched_flags:
        return result

    min_confidence   = config.get("minimum_confidence_if_triggered", "modéré")
    min_orientation  = config.get("minimum_orientation_if_triggered", "medical_review_with_targeted_tests")

    original_confidence  = result.get("confidence_level", "faible")
    original_orientation = result.get("medical_orientation_v2", "supportive_followup")

    new_confidence  = _max_confidence(original_confidence, min_confidence)
    new_orientation = _max_orientation(original_orientation, min_orientation)

    changed = []
    if new_confidence != original_confidence:
        result["confidence_level"] = new_confidence
        changed.append(f"confidence_level: {original_confidence} → {new_confidence}")

    if new_orientation != original_orientation:
        result["medical_orientation_v2"] = new_orientation
        changed.append(f"medical_orientation_v2: {original_orientation} → {new_orientation}")

    # Додаємо інфо в reasoning_summary
    flag_labels = [f["label"] for f in matched_flags]
    result.setdefault("reasoning_summary", [])
    result["reasoning_summary"].append(
        f"safety floor activé: {', '.join(flag_labels)}"
    )

    # Meta інфо (не ламає existing поля)
    result["safety_floor"] = {
        "triggered":     True,
        "matched_flags": matched_flags,
        "changes":       changed,
    }

    return result