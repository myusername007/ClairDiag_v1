"""
ClairDiag v2 — Medical Probability Engine
Bloc C: calcul des scores et ranking des conditions cliniques.

RÈGLE ABSOLUE: v1 ne doit pas être touché.
Ce module travaille uniquement sur l'output de v1.
"""

import json
import os
from typing import Optional

# ──────────────────────────────────────────────
# CONSTANTES
# ──────────────────────────────────────────────

SCORE_THRESHOLDS = {
    "élevé":  6.0,
    "modéré": 3.0,
    "faible": 0.0,
}

NEGATIVE_MARKER_PENALTY   = 1.5
RED_FLAG_CONFLICT_PENALTY = 3.0
MIN_SCORE_TO_INCLUDE      = 0.5

CRITICAL_DANGER_LEVELS  = {"critical", "high"}
EXCLUDE_SCORE_THRESHOLD = 1.0

# ──────────────────────────────────────────────
# CHARGEMENT
# ──────────────────────────────────────────────

def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_conditions(conditions_path: str) -> dict:
    data = _load_json(conditions_path)
    return data["conditions"]

def load_weights(weights_path: str) -> dict:
    data = _load_json(weights_path)
    return data["symptom_weights"]

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def get_confidence_level(score: float, ceiling: str) -> str:
    ceiling_order = ["faible", "modéré", "élevé"]

    if score >= SCORE_THRESHOLDS["élevé"]:
        raw = "élevé"
    elif score >= SCORE_THRESHOLDS["modéré"]:
        raw = "modéré"
    else:
        raw = "faible"

    raw_idx     = ceiling_order.index(raw)
    ceiling_idx = ceiling_order.index(ceiling) if ceiling in ceiling_order else 2
    return ceiling_order[min(raw_idx, ceiling_idx)]


def red_flag_conflict(condition: dict, v1_red_flags: list) -> bool:
    for flag in v1_red_flags:
        if flag in condition.get("exclude_red_flags", []):
            return True
    return False

# ──────────────────────────────────────────────
# CALCUL PRINCIPAL
# ──────────────────────────────────────────────

def compute_scores(
    input_symptoms: list,
    v1_red_flags: list,
    conditions: dict,
    weights: dict,
) -> dict:
    scores = {}

    for cond_name, cond_data in conditions.items():
        score = cond_data["base_weight"]

        for symptom in input_symptoms:
            if symptom in weights:
                score += weights[symptom].get(cond_name, 0.0)

        for neg_marker in cond_data.get("negative_markers", []):
            if neg_marker in input_symptoms:
                score -= NEGATIVE_MARKER_PENALTY

        if red_flag_conflict(cond_data, v1_red_flags):
            score -= RED_FLAG_CONFLICT_PENALTY

        scores[cond_name] = round(score, 3)

    return scores


def rank_conditions(scores: dict) -> list:
    ranked = [
        (name, score)
        for name, score in scores.items()
        if score >= MIN_SCORE_TO_INCLUDE
    ]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def build_exclude_priority(
    ranked: list,
    conditions: dict,
    top_condition: str,
) -> list:
    top_cond_data = conditions.get(top_condition, {})
    top_excludes  = set(top_cond_data.get("exclude_red_flags", []))

    exclude = []
    for cond_name, score in ranked:
        if cond_name == top_condition:
            continue
        cond_data = conditions.get(cond_name, {})
        danger    = cond_data.get("danger_level", "low")
        if danger in CRITICAL_DANGER_LEVELS and score >= EXCLUDE_SCORE_THRESHOLD:
            exclude.append(cond_name)
        elif cond_name in top_excludes:
            exclude.append(cond_name)

    seen = set()
    result = []
    for item in exclude:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_reasoning_summary(
    input_symptoms: list,
    top_condition: str,
    conditions: dict,
    v1_red_flags: list,
) -> list:
    cond_data  = conditions.get(top_condition, {})
    core       = set(cond_data.get("core_symptoms", []))
    supporting = set(cond_data.get("supporting_symptoms", []))
    negative   = set(cond_data.get("negative_markers", []))

    summary = []

    matched_core = [s for s in input_symptoms if s in core]
    matched_supp = [s for s in input_symptoms if s in supporting]
    matched_neg  = [s for s in input_symptoms if s in negative]

    summary.extend(matched_core[:3])
    summary.extend(matched_supp[:2])

    if matched_neg:
        for m in matched_neg[:2]:
            summary.append(f"présence de {m} (contre-indicateur partiel)")

    if not v1_red_flags:
        summary.append("absence de red flags majeurs")
    else:
        summary.append(f"red flags v1 présents: {', '.join(v1_red_flags)}")

    return summary[:6]

# ──────────────────────────────────────────────
# FONCTION PRINCIPALE
# ──────────────────────────────────────────────

def run_probability_engine(
    v1_output: dict,
    conditions_path: str = None,
    weights_path: str = None,
) -> dict:
    """
    Entrée (depuis v1):
    {
        "symptoms_normalized": [...],
        "red_flags": [...],
        "final_action_v1": "...",
        "duration": "...",     # optionnel
        "onset": "...",        # optionnel
        "intensity": "...",    # optionnel
        "age_group": "...",    # optionnel
        "sex": "..."           # optionnel
    }

    Sortie v2:
    {
        "top_hypothesis": "...",
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
        conditions_path = os.path.join(base_dir, "conditions_master.json")
    if weights_path is None:
        weights_path = os.path.join(base_dir, "condition_weights.json")

    conditions = load_conditions(conditions_path)
    weights    = load_weights(weights_path)

    input_symptoms = v1_output.get("symptoms_normalized", [])
    v1_red_flags   = v1_output.get("red_flags", [])
    final_action   = v1_output.get("final_action_v1", "")

    # Edge case: немає симптомів
    if not input_symptoms:
        return {
            "top_hypothesis":       None,
            "secondary_hypotheses": [],
            "exclude_priority":     [],
            "confidence_level":     "faible",
            "clinical_group":       None,
            "reasoning_summary":    ["aucun symptôme normalisé reçu"],
            "v2_status":            "no_input",
        }

    scores = compute_scores(input_symptoms, v1_red_flags, conditions, weights)
    ranked = rank_conditions(scores)

    # Edge case: нічого не набрало мінімум
    if not ranked:
        return {
            "top_hypothesis":       None,
            "secondary_hypotheses": [],
            "exclude_priority":     [],
            "confidence_level":     "faible",
            "clinical_group":       None,
            "reasoning_summary":    ["score insuffisant pour toutes les conditions"],
            "v2_status":            "no_match",
        }

    # Edge case: всі scores однакові
    all_scores = [s for _, s in ranked]
    if len(set(all_scores)) == 1:
        return {
            "top_hypothesis":       None,
            "secondary_hypotheses": [name for name, _ in ranked[:3]],
            "exclude_priority":     [],
            "confidence_level":     "faible",
            "clinical_group":       None,
            "reasoning_summary":    ["scores identiques — ranking non discriminant"],
            "v2_status":            "tied_scores",
        }

    top_name, top_score = ranked[0]
    top_cond            = conditions[top_name]
    secondary           = [name for name, _ in ranked[1:3]]

    ceiling    = top_cond.get("default_confidence_ceiling", "modéré")
    confidence = get_confidence_level(top_score, ceiling)

    # Règle de sécurité v1: EMERGENCY ne peut pas être affaibli
    if "EMERGENCY" in final_action.upper():
        confidence = max(
            confidence, "modéré",
            key=lambda x: ["faible", "modéré", "élevé"].index(x)
        )

    exclude   = build_exclude_priority(ranked, conditions, top_name)
    reasoning = build_reasoning_summary(input_symptoms, top_name, conditions, v1_red_flags)

    return {
        "top_hypothesis":       top_name,
        "secondary_hypotheses": secondary,
        "exclude_priority":     exclude,
        "confidence_level":     confidence,
        "clinical_group":       top_cond.get("clinical_group"),
        "reasoning_summary":    reasoning,
        "v2_status":            "ok",
        "_debug": {
            "top_score":  top_score,
            "all_ranked": ranked[:5],
        },
    }


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    example = {
        "symptoms_normalized": [
            "douleur_post_prandiale",
            "brulure_epigastrique",
            "ballonnements",
            "regurgitation",
        ],
        "red_flags": [],
        "final_action_v1": "consult_doctor",
    }
    result = run_probability_engine(example)
    print(json.dumps(result, ensure_ascii=False, indent=2))