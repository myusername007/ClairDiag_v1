# ── NSE — Natural Symptom Extractor (étape 1) ───────────────────────────────
# Entrée : texte libre OU liste de symptômes bruts
# Sortie : liste de symptômes canoniques connus du système
#
# Responsabilité unique : normaliser l'entrée vers les clés de SYMPTOM_DIAGNOSES.
# Ne calcule aucun score.

from app.data.symptoms import ALIASES, SYMPTOM_DIAGNOSES


def run(symptoms_raw: list[str]) -> list[str]:
    """
    Normalise et dédoublonne une liste de symptômes saisis par l'utilisateur.
    Applique les alias, met en minuscules, supprime les entrées vides.
    Retourne les symptômes canoniques présents dans SYMPTOM_DIAGNOSES.
    """
    result: set[str] = set()
    for raw in symptoms_raw:
        token = raw.lower().strip()
        if not token:
            continue
        # Résolution d'alias exact
        canonical = ALIASES.get(token, token)
        # Accepte uniquement les symptômes connus du dictionnaire
        if canonical in SYMPTOM_DIAGNOSES:
            result.add(canonical)
    return sorted(result)


def parse_text(text: str) -> list[str]:
    """
    Détecte les symptômes connus dans un texte libre.
    Utilisé par l'endpoint /parse-symptoms.
    Priorité aux alias longs (évite les correspondances partielles).
    """
    text_lower = text.lower()
    detected: set[str] = set()
    for alias in sorted(ALIASES, key=len, reverse=True):
        if alias in text_lower:
            detected.add(ALIASES[alias])
    for symptom in SYMPTOM_DIAGNOSES:
        if symptom in text_lower:
            detected.add(symptom)
    return sorted(detected)