# ── CRE — Clinical Rules Engine (étape 7) ───────────────────────────────────
# Entrée : dict de probabilités (sortie TCE), liste de symptômes
# Sortie : dict de probabilités ajustées selon règles médicales simples (HAS-like)
#
# Règles simples, explicites, traçables.
# Ne crée pas de nouveaux diagnostics — ajuste uniquement ceux déjà présents.

_MAX_PROB: float = 0.75

# Format : (symptômes requis, symptômes exclus, diagnostic cible, delta)
# delta > 0 → boost, delta < 0 → pénalité
_RULES: list[tuple[set[str], set[str], str, float]] = [
    # Fièvre élevée → infection plus probable
    ({"fièvre"},        set(), "Grippe",          +0.08),
    ({"fièvre"},        set(), "Pneumonie",        +0.06),
    ({"fièvre"},        set(), "Angine",           +0.06),
    ({"fièvre"},        set(), "Bronchite",        +0.04),

    # Pas de fièvre → infection moins probable
    # (absence de fièvre quand d'autres symptômes respiratoires présents)
    ({"toux"},          {"fièvre"}, "Grippe",      -0.08),
    ({"essoufflement"}, {"fièvre"}, "Pneumonie",   -0.06),

    # Œdèmes → cardiaque (non encore dans les symptômes, préparation future)
    # ({"œdèmes"},      set(), "Angor",            +0.10),

    # Éternuements sans fièvre → allergie très probable
    ({"éternuements"},  {"fièvre"}, "Allergie",    +0.12),

    # Douleur thoracique → cardiaque boost
    ({"douleur thoracique"}, set(), "Angor",       +0.08),

    # Nausées + perte d'appétit → gastrite
    ({"nausées", "perte d'appétit"}, set(), "Gastrite", +0.10),

    # Fatigue + perte d'appétit sans fièvre → anémie
    ({"fatigue", "perte d'appétit"}, {"fièvre"}, "Anémie", +0.10),

    # Essoufflement + toux → asthme ou bronchite
    ({"essoufflement", "toux"}, set(), "Asthme",   +0.06),
    ({"essoufflement", "toux"}, set(), "Bronchite", +0.05),

    # Mal de gorge isolé sans fièvre → rhinopharyngite plutôt qu'angine
    ({"mal de gorge"},  {"fièvre"}, "Angine",      -0.08),
    ({"mal de gorge"},  {"fièvre"}, "Rhinopharyngite", +0.06),
]


def run(probs: dict[str, float], symptoms: list[str]) -> dict[str, float]:
    """
    Applique les règles médicales simples.
    Chaque règle vérifie : symptômes requis présents ET symptômes exclus absents.
    Le delta est appliqué uniquement si le diagnostic est déjà dans probs.
    """
    symptom_set = set(symptoms)
    result = dict(probs)

    for required, excluded, diag, delta in _RULES:
        if diag not in result:
            continue
        if required.issubset(symptom_set) and not excluded.intersection(symptom_set):
            result[diag] = max(0.0, min(_MAX_PROB, result[diag] + delta))

    return result