"""
ClairDiag v2 — Output Formatter
Bloc D: formatage et validation du résultat final v2.
"""

import json
from typing import Optional

# ──────────────────────────────────────────────
# LABELS
# ──────────────────────────────────────────────

CONFIDENCE_LABELS = {
    "élevé":  "🔴 Élevé",
    "modéré": "🟠 Modéré",
    "faible": "🟡 Faible",
}

DANGER_LABELS = {
    "critical":        "⚠️ CRITIQUE",
    "high":            "🔴 Élevé",
    "moderate":        "🟠 Modéré",
    "low_to_moderate": "🟡 Faible–Modéré",
    "low":             "🟢 Faible",
}

V2_STATUS_MESSAGES = {
    "ok":          "Analyse complète",
    "no_input":    "Aucun symptôme reçu",
    "no_match":    "Score insuffisant pour toutes les conditions",
    "tied_scores": "Scores identiques — ranking non discriminant",
}

# ──────────────────────────────────────────────
# VALIDATION
# ──────────────────────────────────────────────

REQUIRED_FIELDS = [
    "top_hypothesis",
    "secondary_hypotheses",
    "exclude_priority",
    "confidence_level",
    "clinical_group",
    "reasoning_summary",
    "v2_status",
]

VALID_CONFIDENCE_LEVELS = {"élevé", "modéré", "faible"}


def validate_output(raw_output: dict) -> tuple:
    errors = []

    for field in REQUIRED_FIELDS:
        if field not in raw_output:
            errors.append(f"Champ manquant: '{field}'")

    confidence = raw_output.get("confidence_level")
    if confidence and confidence not in VALID_CONFIDENCE_LEVELS:
        errors.append(
            f"confidence_level invalide: '{confidence}'. "
            f"Valeurs acceptées: {VALID_CONFIDENCE_LEVELS}"
        )

    for field in ("secondary_hypotheses", "exclude_priority", "reasoning_summary"):
        if not isinstance(raw_output.get(field, []), list):
            errors.append(f"{field} doit être une liste")

    return len(errors) == 0, errors

# ──────────────────────────────────────────────
# FORMAT STANDARD
# ──────────────────────────────────────────────

def format_standard(raw_output: dict) -> dict:
    return {
        "top_hypothesis":       raw_output.get("top_hypothesis"),
        "secondary_hypotheses": raw_output.get("secondary_hypotheses", []),
        "exclude_priority":     raw_output.get("exclude_priority", []),
        "confidence_level":     raw_output.get("confidence_level"),
        "clinical_group":       raw_output.get("clinical_group"),
        "reasoning_summary":    raw_output.get("reasoning_summary", []),
        "v2_status":            raw_output.get("v2_status", "unknown"),
    }

# ──────────────────────────────────────────────
# FORMAT LISIBLE
# ──────────────────────────────────────────────

def format_human_readable(raw_output: dict, conditions: Optional[dict] = None) -> str:
    def get_label(cond_name: str) -> str:
        if conditions and cond_name in conditions:
            cond   = conditions[cond_name]
            danger = DANGER_LABELS.get(cond.get("danger_level", ""), "")
            return f"{cond.get('label_fr', cond_name)} {danger}"
        return cond_name

    status = raw_output.get("v2_status", "unknown")
    msg    = V2_STATUS_MESSAGES.get(status, status)
    lines  = [f"=== ClairDiag v2 — {msg} ===", ""]

    top = raw_output.get("top_hypothesis")
    if top:
        conf       = raw_output.get("confidence_level", "?")
        conf_label = CONFIDENCE_LABELS.get(conf, conf)
        group      = raw_output.get("clinical_group", "?")
        lines.append(f"🏥 Hypothèse principale : {get_label(top)}")
        lines.append(f"   Confiance           : {conf_label}")
        lines.append(f"   Groupe clinique     : {group}")
        lines.append("")
    else:
        lines.append("❌ Aucune hypothèse principale identifiée")
        lines.append("")

    secondary = raw_output.get("secondary_hypotheses", [])
    if secondary:
        lines.append("📋 Hypothèses secondaires :")
        for s in secondary:
            lines.append(f"   • {get_label(s)}")
        lines.append("")

    exclude = raw_output.get("exclude_priority", [])
    if exclude:
        lines.append("⛔ À exclure en priorité :")
        for e in exclude:
            lines.append(f"   • {get_label(e)}")
        lines.append("")

    reasoning = raw_output.get("reasoning_summary", [])
    if reasoning:
        lines.append("💡 Raisonnement :")
        for r in reasoning:
            lines.append(f"   → {r}")
        lines.append("")

    debug = raw_output.get("_debug")
    if debug:
        lines.append("🔧 Debug :")
        lines.append(f"   Top score : {debug.get('top_score', '?')}")
        for name, score in debug.get("all_ranked", []):
            lines.append(f"      {name:40s} {score:.3f}")

    return "\n".join(lines)

# ──────────────────────────────────────────────
# FORMAT TEST
# ──────────────────────────────────────────────

def format_for_test(raw_output: dict) -> dict:
    return {
        "top":        raw_output.get("top_hypothesis"),
        "secondary":  raw_output.get("secondary_hypotheses", []),
        "confidence": raw_output.get("confidence_level"),
        "status":     raw_output.get("v2_status"),
    }

# ──────────────────────────────────────────────
# PIPELINE COMPLET
# ──────────────────────────────────────────────

def process_and_format(
    raw_output: dict,
    conditions: Optional[dict] = None,
    output_format: str = "standard",
    strict_validation: bool = True,
):
    is_valid, errors = validate_output(raw_output)

    if not is_valid:
        if strict_validation:
            raise ValueError(f"Output v2 invalide: {errors}")
        else:
            raw_output["validation_errors"] = errors

    if output_format == "human":
        return format_human_readable(raw_output, conditions)
    elif output_format == "test":
        return format_for_test(raw_output)
    else:
        return format_standard(raw_output)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    from medical_probability_engine import run_probability_engine, load_conditions

    example_v1 = {
        "symptoms_normalized": [
            "douleur_post_prandiale",
            "brulure_epigastrique",
            "ballonnements",
            "regurgitation",
        ],
        "red_flags": [],
        "final_action_v1": "consult_doctor",
    }

    raw        = run_probability_engine(example_v1)
    conditions = load_conditions("conditions_master.json")

    print(format_human_readable(raw, conditions))
    print("\n--- Standard JSON ---")
    print(json.dumps(format_standard(raw), ensure_ascii=False, indent=2))