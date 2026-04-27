"""
ClairDiag v3 — JSON config loader
Завантажує всі конфіги один раз при імпорті модуля.
"""

import json
import os

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _load(filename: str) -> dict:
    path = os.path.join(_DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Завантаження при старті (кешується в пам'яті)
COMMON_CONDITIONS_CONFIG: dict = _load("common_conditions_config.json")
COMMON_SYMPTOM_MAPPING: list = _load("common_symptom_mapping_v1.json")["mappings"]
URGENT_TRIGGERS: list = _load("urgent_triggers_v1.json")["urgent_triggers"]["expressions"]
URGENT_MESSAGE: str = _load("urgent_triggers_v1.json")["urgent_triggers"]["message"]
CLINICAL_COMBINATIONS: list = _load("clinical_combinations_v1.json")["rules"]
DANGER_EXCLUSION_RULES: dict = _load("danger_exclusion_rules_v1.json")
DANGER_REFORMULATION: dict = _load("danger_reformulation_v1.json")

# Пороги тривалості для показу danger_to_exclude пацієнту (в днях)
# None = завжди показувати, 0 = тільки при red flag або urgent
DANGER_EXPOSURE_THRESHOLDS: dict = {
    "dermatologie_simple":           14,
    "orl_simple":                    7,
    "digestif_simple":               5,
    "fatigue_asthenie":              None,   # завжди
    "musculo_squelettique":          7,
    "urinaire":                      None,   # завжди
    "gynecologique_simple":          0,      # тільки red flag
    "metabolique_hormonal_suspect":  None,   # завжди
    "sommeil_stress_anxiete":        0,      # тільки red flag
    "general_vague":                 None,   # завжди
}

# Архетипальні паттерни для confidence boost
ARCHETYPAL_PATTERNS: dict = {
    "orl_simple": [
        ["nez bouché", "mal à la gorge"],
        ["nez bouché", "mal de gorge"],
        ["rhume", "toux"],
        ["rhinorrhée", "mal de gorge"],
        ["nez qui coule", "gorge"],
    ],
    "urinaire": [
        ["brûlure", "urin"],
        ["envie", "brûlure"],
        ["pollakiurie", "dysurie"],
    ],
    "musculo_squelettique": [
        ["mal au dos", "jambe"],
        ["lombalgie"],
        ["torticolis"],
        ["entorse"],
    ],
    "gynecologique_simple": [
        ["règles", "douloureuses"],
        ["douleur", "règles"],
        ["cycle", "irrégulier"],
    ],
    "digestif_simple": [
        ["diarrhée", "nausée"],
        ["vomissements", "diarrhée"],
        ["ballonnements", "constipation"],
    ],
    "dermatologie_simple": [
        ["peau sèche", "démangeaisons"],
        ["plaques", "gratte"],
        ["boutons", "rougeurs"],
    ],
    "metabolique_hormonal_suspect": [
        ["prise de poids", "fatigue"],
        ["fatigue", "froid"],
        ["chute de cheveux", "fatigue"],
    ],
    "sommeil_stress_anxiete": [
        ["stress", "sommeil"],
        ["insomnie", "anxiété"],
        ["dors mal", "stressé"],
    ],
}