# ── TCE — Temporal Context Engine (étape 6) ─────────────────────────────────
# Entrée : dict de probabilités (sortie BPU+RME), onset: str, duration: str
# Sortie : dict de probabilités ajustées
#
# Applique des modificateurs temporels selon :
#   onset   : "brutal" | "progressif" | None
#   duration: "hours"  | "days" | "weeks" | None
#
# Règle : boost uniquement si le diagnostic est déjà présent dans probs.
# Ne crée pas de nouveaux diagnostics.

# ── Modificateurs onset ──────────────────────────────────────────────────────
# onset brutal → favorise pathologies aiguës, pénalise chroniques
_ONSET_BRUTAL_BOOST: dict[str, float] = {
    "Grippe":             0.10,
    "Angor":              0.15,
    "Pneumonie":          0.10,
    "Angine":             0.08,
    "Embolie pulmonaire": 0.12,
    "Trouble du rythme":  0.08,
}
_ONSET_BRUTAL_PENALTY: dict[str, float] = {
    "Allergie":    0.10,
    "Asthme":      0.08,
    "Hypertension":0.05,
}

# onset progressif → favorise pathologies chroniques / allergiques
_ONSET_PROGRESSIF_BOOST: dict[str, float] = {
    "Allergie":              0.10,
    "Asthme":                0.08,
    "Anémie":                0.10,
    "Hypertension":          0.08,
    "Insuffisance cardiaque": 0.10,
    "SII":                   0.08,
}
_ONSET_PROGRESSIF_PENALTY: dict[str, float] = {
    "Grippe":    0.10,
    "Angor":     0.10,
}

# ── Modificateurs duration ───────────────────────────────────────────────────
# hours → très aigu
_DURATION_HOURS_BOOST: dict[str, float] = {
    "Grippe":             0.05,
    "Angor":              0.12,
    "Embolie pulmonaire": 0.10,
    "Trouble du rythme":  0.05,
}
_DURATION_HOURS_PENALTY: dict[str, float] = {
    "Anémie":   0.08,
    "Asthme":   0.05,
}

# days → aigu standard
_DURATION_DAYS_BOOST: dict[str, float] = {
    "Grippe":        0.05,
    "Bronchite":     0.05,
    "Rhinopharyngite":0.05,
}

# weeks → subaigu / chronique
_DURATION_WEEKS_BOOST: dict[str, float] = {
    "Allergie":              0.10,
    "Anémie":                0.10,
    "Asthme":                0.08,
    "Hypertension":          0.08,
    "Insuffisance cardiaque": 0.12,
    "SII":                   0.10,
}
_DURATION_WEEKS_PENALTY: dict[str, float] = {
    "Grippe":    0.10,
    "Angor":     0.05,
}

_MAX_PROB: float = 0.90


def _apply(probs: dict[str, float], boosts: dict[str, float], penalties: dict[str, float]) -> dict[str, float]:
    result = dict(probs)
    for diag, val in boosts.items():
        if diag in result:
            result[diag] = min(_MAX_PROB, result[diag] + val)
    for diag, val in penalties.items():
        if diag in result:
            result[diag] = max(0.0, result[diag] - val)
    return result


def run(probs: dict[str, float], onset: str | None, duration: str | None) -> dict[str, float]:
    """
    Ajuste les probabilités selon le contexte temporel.
    Si onset et duration sont None → retourne probs sans modification.
    """
    result = dict(probs)

    if onset == "brutal":
        result = _apply(result, _ONSET_BRUTAL_BOOST, _ONSET_BRUTAL_PENALTY)
    elif onset == "progressif":
        result = _apply(result, _ONSET_PROGRESSIF_BOOST, _ONSET_PROGRESSIF_PENALTY)

    if duration == "hours":
        result = _apply(result, _DURATION_HOURS_BOOST, _DURATION_HOURS_PENALTY)
    elif duration == "days":
        result = _apply(result, _DURATION_DAYS_BOOST, {})
    elif duration == "weeks":
        result = _apply(result, _DURATION_WEEKS_BOOST, _DURATION_WEEKS_PENALTY)

    return result