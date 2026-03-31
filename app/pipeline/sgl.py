# ── SGL — Safety & Guard Layer (étape 10) ───────────────────────────────────
# Entrée : diagnostics, probs, symptom_count, confidence_level, incoherence_score
# Sortie : confidence_level ajusté + warnings
#
# Responsabilité :
#   - incohérence → baisser confidence (ТЗ п.6)
#   - faible data → cap confidence (ТЗ п.5)
#   - contradictions → warning
#   - Ne modifie jamais diagnostics ni tests.

_MIN_SYMPTOMS_HIGH: int = 3
_MIN_SYMPTOMS_MOD: int = 1

# Incoherence Engine (ТЗ п.6) — seuils de déclenchement
_INCOHERENCE_WARN: float = 0.15    # warning
_INCOHERENCE_DROP: float = 0.30    # baisser confidence d'un niveau

_INCOMPATIBLE_PAIRS: list[tuple[str, str]] = [
    ("Allergie",  "Pneumonie"),
    ("Gastrite",  "Angor"),
    ("Allergie",  "Angor"),
    ("Gastrite",  "Grippe"),
]


def run(
    diagnoses_names: list[str],
    probs: dict[str, float],
    symptom_count: int,
    confidence_level: str,
    incoherence_score: float = 0.0,
) -> tuple[str, list[str]]:
    """
    Retourne (confidence_level_final, warnings).
    """
    warnings: list[str] = []
    level = confidence_level

    # ── 1. Données insuffisantes (ТЗ п.5) ────────────────────────────────────
    if symptom_count < _MIN_SYMPTOMS_MOD:
        warnings.append("Données insuffisantes : symptômes non reconnus.")
        level = "faible"
    elif symptom_count < _MIN_SYMPTOMS_HIGH and level == "élevé":
        warnings.append("Confiance abaissée : moins de 3 symptômes.")
        level = "modéré"

    # ── 2. Aucun diagnostic ───────────────────────────────────────────────────
    if not diagnoses_names:
        warnings.append("Aucun diagnostic identifiable — consultez un médecin.")
        return "faible", warnings

    # ── 3. Incoherence Engine (ТЗ п.6) ───────────────────────────────────────
    # Les symptômes contradictoires ont accumulé un score dans BPU.
    # Ici on l'utilise pour baisser confidence et générer un warning.
    if incoherence_score >= _INCOHERENCE_DROP:
        warnings.append(
            f"Contradictions détectées entre les symptômes (score {incoherence_score:.2f}). "
            "Résultat moins fiable — consultation recommandée."
        )
        if level == "élevé":
            level = "modéré"
        elif level == "modéré":
            level = "faible"
    elif incoherence_score >= _INCOHERENCE_WARN:
        warnings.append(
            "Légères contradictions entre certains symptômes — résultat à confirmer."
        )
        if level == "élevé":
            level = "modéré"

    # ── 4. Paires incompatibles au top ────────────────────────────────────────
    top_set = set(diagnoses_names[:2])
    for diag_a, diag_b in _INCOMPATIBLE_PAIRS:
        if diag_a in top_set and diag_b in top_set:
            warnings.append(
                f"Incohérence : {diag_a} et {diag_b} sont peu compatibles. "
                "Consultation médicale recommandée."
            )
            if level == "élevé":
                level = "modéré"
            elif level == "modéré":
                level = "faible"

    # ── 5. Probabilités trop proches ─────────────────────────────────────────
    if len(probs) >= 2:
        sorted_probs = sorted(probs.values(), reverse=True)
        if abs(sorted_probs[0] - sorted_probs[1]) < 0.05:
            warnings.append(
                "Plusieurs diagnostics à probabilité proche — tests complémentaires nécessaires."
            )
            if level == "élevé":
                level = "modéré"

    # ── 6. Cap final : élevé nécessite ≥ 3 symptômes ─────────────────────────
    if level == "élevé" and symptom_count < _MIN_SYMPTOMS_HIGH:
        level = "modéré"

    return level, warnings