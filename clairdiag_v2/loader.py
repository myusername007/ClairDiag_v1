"""
ClairDiag v3/v2 — JSON config loader v2.0
Завантажує v3 конфіги (backward compat) + v2 JSON rules через UniversalRulesLoader.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _load(filename: str) -> dict:
    path = os.path.join(_DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── v3 конфіги (незмінні) ─────────────────────────────────────────────────────
COMMON_CONDITIONS_CONFIG: dict = _load("common_conditions_config.json")
COMMON_SYMPTOM_MAPPING: list = _load("common_symptom_mapping_v1.json")["mappings"]
URGENT_TRIGGERS: list = _load("urgent_triggers_v1.json")["urgent_triggers"]["expressions"]
URGENT_MESSAGE: str = _load("urgent_triggers_v1.json")["urgent_triggers"]["message"]
CLINICAL_COMBINATIONS: list = _load("clinical_combinations_v1.json")["rules"]
DANGER_EXCLUSION_RULES: dict = _load("danger_exclusion_rules_v1.json")
DANGER_REFORMULATION: dict = _load("danger_reformulation_v1.json")

DANGER_EXPOSURE_THRESHOLDS: dict = {
    "dermatologie_simple":           14,
    "orl_simple":                    7,
    "digestif_simple":               5,
    "fatigue_asthenie":              None,
    "musculo_squelettique":          7,
    "urinaire":                      None,
    "gynecologique_simple":          0,
    "metabolique_hormonal_suspect":  None,
    "sommeil_stress_anxiete":        0,
    "general_vague":                 None,
}

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


# ── v2 JSON rules via UniversalRulesLoader ────────────────────────────────────

_V2_RULES_LOADER = None


def get_v2_rules_loader():
    """
    Singleton accessor для UniversalRulesLoader з v2 JSON rules.
    Повертає None якщо недоступний (graceful fallback).
    """
    global _V2_RULES_LOADER
    if _V2_RULES_LOADER is not None:
        return _V2_RULES_LOADER

    try:
        from pathlib import Path
        from universal_rules_loader import UniversalRulesLoader

        rules_dir = Path(_DATA_DIR)
        loader = UniversalRulesLoader(rules_dir)
        status = loader.load()

        if status.success:
            _V2_RULES_LOADER = loader
            logger.info(
                f"v2 rules loaded: {len(status.loaded)} files, "
                f"{len(status.warnings)} warnings"
            )
        else:
            logger.warning(
                f"v2 rules partial load: failed={status.failed}, "
                f"errors={status.errors}"
            )
            # Часткове завантаження — повертаємо loader якщо хоча б щось є
            if len(status.loaded) > 0:
                _V2_RULES_LOADER = loader

    except Exception as e:
        logger.warning(f"v2 rules loader unavailable: {e}")
        _V2_RULES_LOADER = None

    return _V2_RULES_LOADER


# Ініціалізація при імпорті (non-blocking)
try:
    get_v2_rules_loader()
except Exception:
    pass