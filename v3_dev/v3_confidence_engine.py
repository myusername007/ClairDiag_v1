"""
ClairDiag v3 — Confidence Engine v3.0.2

Калібрований барем згідно §9.3 зовнішньої spec.
Плафон 8/10 без urgent trigger.

Барем:
  urgent trigger                    → high, 9
  general_vague                     → low, 2
  1 expr + priority ≥ 5             → medium, 5
  ≥ 2 expr                          → medium, 6
  ≥ 3 expr або архетипальний паттерн → high, 7-8 (плафон 8)
  combination matched               → +1 (max 8)
  temporal відомий                  → +0 (вже враховано в patterns)
"""

from typing import Dict, List, Optional
from loader import ARCHETYPAL_PATTERNS


def _is_archetypal(category: str, matched_symptoms: List[str]) -> bool:
    """Перевіряє чи симптоми відповідають архетипальному паттерну."""
    patterns = ARCHETYPAL_PATTERNS.get(category, [])
    text_joined = " ".join(matched_symptoms).lower()
    for pattern in patterns:
        if len(pattern) == 1:
            # одне ключове слово — перевіряємо substring
            if pattern[0].lower() in text_joined:
                return True
        else:
            # всі елементи паттерну мають бути присутні
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
) -> Dict:

    if matched_symptoms is None:
        matched_symptoms = []

    # Urgent → окремий випадок
    if urgent_trigger:
        return {
            "level": "high",
            "score": 9,
            "orientation_summary": "Signaux d'urgence détectés — évaluation médicale immédiate requise.",
        }

    # Немає категорії
    if not category:
        return {
            "level": "low",
            "score": 2,
            "orientation_summary": "Symptômes non identifiés — consultation médecin traitant recommandée.",
        }

    # general_vague → low завжди
    if category in ("general_vague", "general_vague_non_specifique"):
        return {
            "level": "low",
            "score": 2,
            "orientation_summary": "Symptômes non spécifiques — consultation médecin traitant pour préciser.",
        }

    # Барем §9.3
    archetypal = _is_archetypal(category, matched_symptoms)

    if category_matches >= 3 or archetypal:
        score = 8 if not combination_matched else 8  # плафон 8
        level = "high"
    elif category_matches >= 2:
        score = 7 if combination_matched else 6
        level = "medium" if score < 7 else "high"
    elif category_matches == 1 and category_priority >= 5:
        score = 6 if combination_matched else 5
        level = "medium"
    else:
        score = 3
        level = "low"

    # Плафон 8 без urgent
    score = min(8, score)

    if score >= 7:
        level = "high"
    elif score >= 4:
        level = "medium"
    else:
        level = "low"

    # Будуємо orientation_summary — людський текст замість технічних reasons
    orientation_summary = _build_summary(
        category, matched_symptoms, temporal, archetypal, combination_matched
    )

    return {
        "level": level,
        "score": score,
        "orientation_summary": orientation_summary,
    }


def _build_summary(
    category: str,
    matched_symptoms: List[str],
    temporal: str,
    archetypal: bool,
    combination_matched: bool,
) -> str:
    """Будує людський текст замість технічних reasons."""

    # Базовий опис категорії
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

    parts = []

    if matched_symptoms:
        syms = ", ".join(matched_symptoms[:3])
        parts.append(f"{syms}")

    if parts:
        summary = f"{', '.join(parts)}, compatible avec une {label} sans signe de gravité immédiate"
    else:
        summary = f"Tableau compatible avec une {label}"

    if temporal != "unknown":
        temporal_labels = {
            "acute": "d'apparition récente",
            "subacute": "évoluant depuis quelques jours",
            "chronic": "persistant depuis plusieurs semaines",
        }
        summary += f" — {temporal_labels.get(temporal, '')}"

    if combination_matched:
        summary += " (association de symptômes typique)"

    return summary + "."