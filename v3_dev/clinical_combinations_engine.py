"""
ClairDiag v3 — Clinical Combinations Engine
Матчить набір medical tokens + temporal → комбінаційне правило.
Якщо правило знайдено — повертає орієнтацію з вищою специфічністю.
"""

from typing import Dict, List, Optional
from loader import CLINICAL_COMBINATIONS


def match_combination(tokens: List[str], temporal: str) -> Optional[Dict]:
    """
    Повертає найкраще правило або None.
    Критерії: всі tokens_all присутні + temporal в списку.
    Тай-брейк: highest priority.
    """
    matched = []
    for rule in CLINICAL_COMBINATIONS:
        if not all(t in tokens for t in rule["tokens_all"]):
            continue
        if temporal not in rule["temporal"]:
            continue
        matched.append(rule)

    if not matched:
        return None

    matched.sort(key=lambda r: r["priority"], reverse=True)
    best = matched[0]

    return {
        "matched_rule": best["id"],
        "orientation": best["orientation"],
        "priority": best["priority"],
    }