"""
ClairDiag v2 — Test Recommendation Engine
Bloc B + C: sélection des examens et stratégie exclude/confirm.

RÈGLE ABSOLUE: v1 ne doit pas être touché.
"""

import json
import os
from typing import Optional

# ──────────────────────────────────────────────
# CONSTANTES
# ──────────────────────────────────────────────

DANGER_LEVELS_HIGH = {"critical", "high"}

# Mapping final_action_v1 → medical_orientation_v2
V1_ACTION_TO_ORIENTATION = {
    "EMERGENCY":             "urgent_emergency_workup",
    "URGENT_MEDICAL_REVIEW": "urgent_medical_review_with_tests",
    "CONSULT_URGENT":        "urgent_medical_review_with_tests",
    "MEDICAL_REVIEW":        "medical_review_with_targeted_tests",
    "CONSULT_DOCTOR":        "medical_review_with_targeted_tests",
    "TESTS_FIRST":           "medical_review_with_targeted_tests",
    "LOW_RISK_MONITOR":      "supportive_followup",
    "AUTO_CARE":             "supportive_followup",
}

# ──────────────────────────────────────────────
# CHARGEMENT
# ──────────────────────────────────────────────

def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_tests_master(path: str) -> dict:
    data = _load_json(path)
    return data["tests"]

def load_differential_rules(path: str) -> dict:
    data = _load_json(path)
    return data["rules"]

def load_conditions(path: str) -> dict:
    data = _load_json(path)
    return data["conditions"]

# ──────────────────────────────────────────────
# ЛОГИКА РЕЖИМА
# ──────────────────────────────────────────────

def determine_logic_mode(
    top_hypothesis: str,
    exclude_priority: list,
    confidence_level: str,
    conditions: dict,
    differential_rules: dict,
) -> str:
    """
    Визначає режим:
    - exclude_danger_first: є небезпечні стани в exclude
    - urgent_parallel: top сам по собі critical/high
    - confirm_top_first: все відносно безпечне
    """

    # Якщо top сам critical/high → urgent_parallel
    top_danger = conditions.get(top_hypothesis, {}).get("danger_level", "low")
    if top_danger in DANGER_LEVELS_HIGH:
        return "urgent_parallel"

    # Якщо є high-danger в exclude → exclude_danger_first
    for exc in exclude_priority:
        exc_danger = conditions.get(exc, {}).get("danger_level", "low")
        if exc_danger in DANGER_LEVELS_HIGH:
            return "exclude_danger_first"

    # Інакше confirm_top_first
    return "confirm_top_first"


def find_differential_rule(
    top_hypothesis: str,
    exclude_priority: list,
    secondary_hypotheses: list,
    differential_rules: dict,
) -> Optional[dict]:
    """
    Шукає найбільш релевантне differential rule для поточної пари.
    Спочатку top vs exclude, потім top vs secondary.
    """
    candidates = list(exclude_priority) + list(secondary_hypotheses)

    for rule_key, rule in differential_rules.items():
        conditions_set = set(rule.get("conditions", []))
        if top_hypothesis in conditions_set:
            for candidate in candidates:
                if candidate in conditions_set:
                    return rule
    return None

# ──────────────────────────────────────────────
# ВИБІР ТЕСТІВ
# ──────────────────────────────────────────────

def select_tests(
    top_hypothesis: str,
    exclude_priority: list,
    secondary_hypotheses: list,
    logic_mode: str,
    conditions: dict,
    tests_master: dict,
    differential_rule: Optional[dict],
    final_action_v1: str,
    max_tests: int = 3,
) -> list:
    """
    Повертає список recommended_tests з priority і reason.

    Стратегія:
    1. exclude_danger_first → тести для виключення небезпечного стану
    2. urgent_parallel → тести для top (критичний) паралельно
    3. confirm_top_first → тести для підтвердження top
    """

    recommended = []
    seen_tests = set()

    def add_test(test_key: str, priority: str, reason: str):
        if test_key not in seen_tests and len(recommended) < max_tests:
            seen_tests.add(test_key)
            test_data = tests_master.get(test_key, {})
            recommended.append({
                "test":     test_key,
                "label_fr": test_data.get("label_fr", test_key),
                "priority": priority,
                "reason":   reason,
            })

    # ── 1. Тести з differential rule (найвища пріоритетність) ──
    if differential_rule:
        for t in differential_rule.get("tests_to_differentiate", []):
            if t in tests_master:
                add_test(t, "exclude_first", f"differentiating test: {' vs '.join(differential_rule.get('conditions', []))}")

    # ── 2. exclude_danger_first: тести для виключення небезпечних станів ──
    if logic_mode == "exclude_danger_first":
        for exc in exclude_priority:
            exc_danger = conditions.get(exc, {}).get("danger_level", "low")
            if exc_danger in DANGER_LEVELS_HIGH:
                # сортуємо тести: urgent_relevant першими
                priority_order = {"urgent_relevant": 0, "first_line": 1, "second_line": 2, "supportive": 3, "optional": 4}
                sorted_tests = sorted(
                    tests_master.items(),
                    key=lambda x: priority_order.get(x[1].get("priority_class", "optional"), 4)
                )
                for test_key, test_data in sorted_tests:
                    if exc in test_data.get("exclude_power", []):
                        add_test(
                            test_key,
                            "exclude_first",
                            f"exclure {exc} ({conditions.get(exc, {}).get('label_fr', exc)})",
                        )

    # ── 3. urgent_parallel: тести для top critical — сортуємо urgent першими ──
    elif logic_mode == "urgent_parallel":
        priority_order = {"urgent_relevant": 0, "first_line": 1, "second_line": 2, "supportive": 3, "optional": 4}
        sorted_tests = sorted(
            tests_master.items(),
            key=lambda x: priority_order.get(x[1].get("priority_class", "optional"), 4)
        )
        for test_key, test_data in sorted_tests:
            if top_hypothesis in test_data.get("use_for", []):
                priority = "exclude_first" if top_hypothesis in test_data.get("exclude_power", []) else "confirm_top"
                add_test(
                    test_key,
                    priority,
                    f"bilan urgent: {conditions.get(top_hypothesis, {}).get('label_fr', top_hypothesis)}",
                )

    # ── 4. confirm_top_first: тести для підтвердження top ──
    elif logic_mode == "confirm_top_first":
        for test_key, test_data in tests_master.items():
            if top_hypothesis in test_data.get("confirm_power", []):
                add_test(
                    test_key,
                    "confirm_top",
                    f"confirmer {conditions.get(top_hypothesis, {}).get('label_fr', top_hypothesis)}",
                )

    # ── 5. Supportive: тести для secondary якщо місце є ──
    for sec in secondary_hypotheses:
        if len(recommended) >= max_tests:
            break
        for test_key, test_data in tests_master.items():
            if len(recommended) >= max_tests:
                break
            if sec in test_data.get("use_for", []) and test_key not in seen_tests:
                add_test(
                    test_key,
                    "supportive",
                    f"hypothèse secondaire: {conditions.get(sec, {}).get('label_fr', sec)}",
                )

    return recommended


def determine_orientation(
    final_action_v1: str,
    logic_mode: str,
    top_hypothesis: Optional[str],
    recommended_tests: list,
) -> str:
    """
    Визначає medical_orientation_v2.
    v1 safety rule: EMERGENCY не може бути знижений.
    """
    if not top_hypothesis:
        return "insufficient_data"

    # v1 safety master
    for key, orientation in V1_ACTION_TO_ORIENTATION.items():
        if key in final_action_v1.upper():
            return orientation

    # Fallback за logic_mode
    if logic_mode == "urgent_parallel":
        return "urgent_medical_review_with_tests"
    if logic_mode == "exclude_danger_first":
        return "medical_review_with_targeted_tests"
    if not recommended_tests:
        return "supportive_followup"
    return "medical_review_with_targeted_tests"

# ──────────────────────────────────────────────
# ГОЛОВНА ФУНКЦІЯ
# ──────────────────────────────────────────────

def run_recommendation_engine(
    etape1_output: dict,
    v1_output: dict,
    conditions_path: str = None,
    tests_path: str = None,
    differential_path: str = None,
) -> dict:
    """
    Приймає output Étape 1 + v1_output.
    Повертає повний v2 output з recommended_tests і reasoning.

    Étape 1 output:
    {
        "top_hypothesis": "rgo",
        "secondary_hypotheses": [...],
        "exclude_priority": [...],
        "confidence_level": "...",
        "clinical_group": "...",
        "reasoning_summary": [...],
        "v2_status": "ok"
    }
    """

    base_dir = os.path.dirname(os.path.abspath(__file__))
    if conditions_path is None:
        conditions_path   = os.path.join(base_dir, "conditions_master.json")
    if tests_path is None:
        tests_path        = os.path.join(base_dir, "tests_master.json")
    if differential_path is None:
        differential_path = os.path.join(base_dir, "differential_rules.json")

    conditions         = load_conditions(conditions_path)
    tests_master       = load_tests_master(tests_path)
    differential_rules = load_differential_rules(differential_path)

    top_hypothesis      = etape1_output.get("top_hypothesis")
    secondary           = etape1_output.get("secondary_hypotheses", [])
    exclude_priority    = etape1_output.get("exclude_priority", [])
    confidence_level    = etape1_output.get("confidence_level", "faible")
    v2_status           = etape1_output.get("v2_status", "ok")
    final_action_v1     = v1_output.get("final_action_v1", "")

    # ── Edge case: Étape 1 без результату ──
    if v2_status in ("no_input", "no_match", "tied_scores") or not top_hypothesis:
        return {
            **etape1_output,
            "recommended_tests":      [],
            "next_step_logic":        "insufficient_data",
            "medical_orientation_v2": "insufficient_data",
        }

    # ── Визначаємо logic_mode ──
    logic_mode = determine_logic_mode(
        top_hypothesis, exclude_priority, confidence_level, conditions, differential_rules
    )

    # ── Шукаємо differential rule ──
    diff_rule = find_differential_rule(
        top_hypothesis, exclude_priority, secondary, differential_rules
    )

    # ── Вибираємо тести ──
    recommended_tests = select_tests(
        top_hypothesis   = top_hypothesis,
        exclude_priority = exclude_priority,
        secondary_hypotheses = secondary,
        logic_mode       = logic_mode,
        conditions       = conditions,
        tests_master     = tests_master,
        differential_rule = diff_rule,
        final_action_v1  = final_action_v1,
    )

    # ── Визначаємо orientation ──
    orientation = determine_orientation(
        final_action_v1, logic_mode, top_hypothesis, recommended_tests
    )

    return {
        **etape1_output,
        "recommended_tests":      recommended_tests,
        "next_step_logic":        logic_mode,
        "medical_orientation_v2": orientation,
    }


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    from medical_probability_engine import run_probability_engine

    v1_output = {
        "symptoms_normalized": [
            "douleur_thoracique",
            "douleur_post_prandiale",
            "regurgitation",
            "inconfort_digestif",
        ],
        "red_flags": [],
        "final_action_v1": "consult_doctor",
    }

    etape1 = run_probability_engine(v1_output)
    result = run_recommendation_engine(etape1, v1_output)

    print(json.dumps(result, ensure_ascii=False, indent=2))