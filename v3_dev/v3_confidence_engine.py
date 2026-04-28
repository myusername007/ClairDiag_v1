"""
ClairDiag v3 — Confidence Engine v3.1.0

Барем §9.3:
  urgent trigger              → high, 9
  and_trigger (AND-logic)     → high, 8  ← CTRL-16: підтверджена клінічна комбінація
  general_vague               → low, 2
  no category                 → low, 2
  1 expr + priority ≥ 5       → medium, 5
  ≥ 2 expr                    → medium, 6
  ≥ 3 expr або archetypal     → high, 7  (плафон 8 без urgent)
  combination matched         → +1 (max 8)
"""

from typing import Dict, List, Optional
from loader import ARCHETYPAL_PATTERNS


def _is_archetypal(category: str, matched_symptoms: List[str]) -> bool:
    patterns = ARCHETYPAL_PATTERNS.get(category, [])
    text_joined = " ".join(s.lower() for s in matched_symptoms)
    for pattern in patterns:
        if len(pattern) == 1:
            if pattern[0].lower() in text_joined:
                return True
        else:
            if all(p.lower() in text_joined for p in pattern):
                return True
    return False


def compute_v3_confidence(
    category: Optional[str],
    category_matches: int,
    all_hits: List,
    combination_matched: bool,
    temporal: str,
    patient_context: Optional[Dict],
    urgent_trigger: Optional[str],
    matched_symptoms: Optional[List[str]] = None,
    category_priority: int = 0,
    and_trigger: Optional[Dict] = None,
) -> Dict:

    if matched_symptoms is None:
        matched_symptoms = []

    # Рівень 9: urgent trigger (одиночний симптом-маркер)
    if urgent_trigger:
        return {
            "level": "high",
            "score": 9,
            "orientation_summary": "Signaux d'urgence détectés — évaluation médicale immédiate requise.",
        }

    # Рівень 8: AND-trigger — підтверджена клінічна комбінація (CTRL-16, CTRL-17)
    # Логіка: три незалежні групи симптомів разом → клінічний паттерн з доведеним ризиком
    if and_trigger:
        summary = and_trigger.get("message", (
            "Association de symptômes cliniquement significative détectée — "
            "consultation médicale recommandée."
        ))
        return {
            "level": "high",
            "score": 8,
            "orientation_summary": summary,
        }

    if not category:
        return {
            "level": "low",
            "score": 2,
            "orientation_summary": "Symptômes non identifiés — consultation médecin traitant recommandée.",
        }

    if category in ("general_vague", "general_vague_non_specifique"):
        return {
            "level": "low",
            "score": 2,
            "orientation_summary": "Symptômes non spécifiques — consultation médecin traitant pour préciser.",
        }

    archetypal = _is_archetypal(category, matched_symptoms)

    if category_matches >= 3:
        score = 8 if (combination_matched or archetypal) else 7
    elif category_matches >= 2:
        score = 7 if combination_matched else 6
    elif category_matches == 1 and category_priority >= 5:
        score = 6 if combination_matched else 5
    else:
        score = 3

    score = min(8, score)

    if score >= 7:
        level = "high"
    elif score >= 4:
        level = "medium"
    else:
        level = "low"

    orientation_summary = _build_summary(category, matched_symptoms, temporal, archetypal, combination_matched)

    return {
        "level": level,
        "score": score,
        "orientation_summary": orientation_summary,
    }


def _build_summary(category, matched_symptoms, temporal, archetypal, combination_matched):
    CATEGORY_LABELS = {
        "orl_simple": "plainte ORL fréquente",
        "dermatologie_simple": "symptôme cutané courant",
        "digestif_simple": "trouble digestif courant",
        "fatigue_asthenie": "syndrome de fatigue",
        "musculo_squelettique": "plainte musculo-squelettique",
        "urinaire": "symptôme urinaire",
        "gynecologique_simple": "plainte gynécologique courante",
        "metabolique_hormonal_suspect": "tableau évocateur d'un déséquilibre hormonal ou métabolique",
        "sommeil_stress_anxiete": "troubles du sommeil ou anxiété",
        "general_vague": "symptômes non spécifiques",
    }
    label = CATEGORY_LABELS.get(category, category.replace("_", " "))
    syms = ", ".join(matched_symptoms[:3]) if matched_symptoms else ""
    if syms:
        summary = f"{syms}, compatible avec une {label} sans signe de gravité immédiate"
    else:
        summary = f"Tableau compatible avec une {label}"
    if temporal != "unknown":
        labels = {
            "acute":    "d'apparition récente",
            "subacute": "évoluant depuis quelques jours",
            "chronic":  "persistant depuis plusieurs semaines",
        }
        summary += f" — {labels.get(temporal, '')}"
    if combination_matched:
        summary += " (association de symptômes typique)"
    return summary + "."