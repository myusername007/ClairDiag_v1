"""
ClairDiag v1.1.0 — Abstract Pattern Evaluator + Hybrid Resolution

Module: pattern_evaluator
Version: v2.0
Date: 2026-04-30

PURPOSE:
- Évaluer les abstract patterns ABS-01..ABS-08 contre un objet features
- Implémenter la résolution hybride: ABSTRACT first, TOKEN fallback
- Logger les "would have matched" pour migration signal

INTEGRATION:
1. Charger clinical_patterns_v2_abstract.json au démarrage
2. Appeler hybrid_pre_triage() après Stage 3 (feature extraction)
3. Si abstract layer match → utiliser, marquer primary_layer_used='abstract_v2'
4. Sinon → fall back to existing pattern_engine_v3 (PE-01..PE-34)

NE CASSE PAS la régression:
- Si features mal extracted → patterns ne matchent pas → fallback to token layer
- 90/90 + 49/50 + 20/20 doivent toujours passer
"""

import json
from pathlib import Path
from typing import Optional, Callable

# CONFIG_PATH: JSON est dans data/ au même niveau que le module
CONFIG_PATH = Path(__file__).parent / "data" / "clinical_patterns_v2_abstract.json"


# ============================================================
# 1. Loader
# ============================================================

class AbstractPatternsConfig:
    """Charge clinical_patterns_v2_abstract.json au démarrage."""

    def __init__(self, config_path: Path = CONFIG_PATH):
        with open(config_path, encoding="utf-8") as f:
            self.config = json.load(f)
        self.patterns = self.config["abstract_patterns"]


# ============================================================
# 2. Evaluator core
# ============================================================

def evaluate_pattern(pattern: dict, features: dict) -> bool:
    """Évalue un pattern abstract sur un objet features."""
    return _eval_node(pattern["conditions"], features)


def _eval_node(node: dict, features: dict) -> bool:
    if "all_of" in node:
        return all(_eval_node(c, features) for c in node["all_of"])
    if "any_of" in node:
        return any(_eval_node(c, features) for c in node["any_of"])
    if "not" in node:
        return not _eval_node(node["not"], features)
    return _eval_leaf(node, features)


def _eval_leaf(leaf: dict, features: dict) -> bool:
    feature_path = leaf["feature"]
    actual = _get_feature(features, feature_path)
    if "contains" in leaf:
        return leaf["contains"] in (actual or [])
    if "eq" in leaf:
        return actual == leaf["eq"]
    if "gte" in leaf:
        return actual is not None and actual >= leaf["gte"]
    if "lte" in leaf:
        return actual is not None and actual <= leaf["lte"]
    if "in" in leaf:
        return actual in leaf["in"]
    return False


def _get_feature(features: dict, path: str):
    parts = path.split(".")
    current = features
    for p in parts:
        if isinstance(current, dict):
            current = current.get(p)
        else:
            return None
    return current


# ============================================================
# 3. Severity ordering
# ============================================================

URGENCY_LEVELS = ["non_urgent", "medical_consultation", "urgent_medical_review", "urgent"]


def severity(level: str) -> int:
    try:
        return URGENCY_LEVELS.index(level)
    except ValueError:
        return -1


def max_severity(*levels) -> str:
    valid = [l for l in levels if l in URGENCY_LEVELS]
    if not valid:
        return "non_urgent"
    return max(valid, key=severity)


# ============================================================
# 4. Hybrid resolution
# ============================================================

def evaluate_abstract_layer(config: AbstractPatternsConfig, features: dict) -> dict:
    """Évalue tous les abstract patterns. Retourne match info."""
    matched = []
    override_all = False
    for pattern in config.patterns:
        if evaluate_pattern(pattern, features):
            matched.append(pattern)
            if pattern.get("override_all_other_logic"):
                override_all = True

    if not matched:
        return {
            "abstract_match": False,
            "matched_patterns": [],
            "triage_level": None,
            "override_all": False,
        }

    triage = max_severity(*[p["triage_level"] for p in matched])
    return {
        "abstract_match": True,
        "matched_patterns": [p["pattern_id"] for p in matched],
        "matched_pattern_details": matched,
        "triage_level": triage,
        "override_all": override_all,
        "patient_explanation_hints": [
            p["patient_explanation_hint"]
            for p in matched
            if p.get("patient_explanation_hint")
        ],
        "specialist_hints": [
            p["specialist_hint"]
            for p in matched
            if p.get("specialist_hint")
        ],
    }


def hybrid_pre_triage(
    abstract_config: AbstractPatternsConfig,
    features: dict,
    token_layer_callable: Optional[Callable] = None,
) -> dict:
    """
    Hybrid resolution: abstract patterns (primary) + token engine (fallback).

    Args:
        abstract_config: AbstractPatternsConfig instance
        features: feature object from Stage 3
        token_layer_callable: callable(features) → dict with keys:
                              matched_patterns: list, triage_level: str | None
                              If None, fallback is skipped (abstract-only mode).

    Returns:
        dict with:
          primary_layer_used: 'abstract_v2' | 'token_v1_fallback' | 'none'
          triage_level
          matched_patterns
          override_all
          fallback_would_have_matched  — always logged for audit/migration signal
    """
    abstract_result = evaluate_abstract_layer(abstract_config, features)

    # Always evaluate token layer for logging (migration signal)
    token_result = None
    if token_layer_callable:
        try:
            token_result = token_layer_callable(features)
        except Exception as e:
            token_result = {"error": str(e), "matched_patterns": [], "triage_level": None}

    fallback_would_have_matched = (token_result or {}).get("matched_patterns", [])

    if abstract_result["abstract_match"]:
        return {
            "primary_layer_used": "abstract_v2",
            "matched_patterns": abstract_result["matched_patterns"],
            "triage_level": abstract_result["triage_level"],
            "override_all": abstract_result["override_all"],
            "patient_explanation_hints": abstract_result["patient_explanation_hints"],
            "specialist_hints": abstract_result["specialist_hints"],
            "fallback_would_have_matched": fallback_would_have_matched,
        }

    if token_result and (
        token_result.get("matched_patterns") or token_result.get("triage_level")
    ):
        return {
            "primary_layer_used": "token_v1_fallback",
            "matched_patterns": token_result.get("matched_patterns", []),
            "triage_level": token_result.get("triage_level"),
            "override_all": False,
            "fallback_used_signal": "abstract layer did not match — candidate for migration",
            "patient_explanation_hints": [],
            "specialist_hints": [],
            "fallback_would_have_matched": [],
        }

    return {
        "primary_layer_used": "none",
        "matched_patterns": [],
        "triage_level": None,
        "override_all": False,
        "fallback_would_have_matched": [],
    }