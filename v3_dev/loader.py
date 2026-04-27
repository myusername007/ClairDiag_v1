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