"""
ClairDiag v2 — Context Flags Layer (TASK #007)
Overlay layer: keyword detection → risk flags → clinical alerts.

⚠️ READ-ONLY overlay — does NOT touch:
   - probability engine
   - ranking / scoring / weights
   - safety floor
"""

from __future__ import annotations
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# DETECTION RULES: list of keywords → flag
# ──────────────────────────────────────────────────────────────────────────────

_RULES: list[tuple[list[str], str]] = [
    # AOD / Anticoagulants → risque hémorragique
    (["aod", "anticoagulant", "anticoagulants", "apixaban", "rivaroxaban",
      "dabigatran", "warfarine", "heparine", "xarelto", "eliquis"], "risk_bleeding"),

    # Cancer / Oncologie → risque thrombotique
    (["cancer", "oncologie", "tumeur", "tumeurs", "chimio",
      "chimiotherapie", "radiotherapie", "metastase", "leucemie",
      "lymphome"], "risk_thrombosis"),

    # Voyage / Immobilisation → risque thrombotique
    (["avion", "voyage", "long trajet", "long-courrier",
      "immobilisation prolongee", "alitement", "trajet long"], "risk_thrombosis"),

    # Trauma / Chute → risque traumatique
    (["chute", "traumatisme", "trauma", "coup", "blessure",
      "accident", "fracture", "contusion"], "risk_trauma"),

    # Grossesse → risque spécifique grossesse
    (["grossesse", "enceinte", "gestante", "trimestre",
      "accouchement", "post-partum", "postpartum"], "risk_pregnancy"),

    # Immunodépression → risque infectieux
    (["immunodepression", "immunodeprime", "immunosupprime",
      "immunosuppression", "greffe", "vih", "sida", "corticoides",
      "biotherapie", "neutropenie"], "risk_infection"),
]

# ──────────────────────────────────────────────────────────────────────────────
# ALERT BASE LABELS
# ──────────────────────────────────────────────────────────────────────────────

_ALERT_LABELS: dict[str, str] = {
    "risk_bleeding":   "Risque hémorragique",
    "risk_thrombosis": "Risque de thrombose / TVP",
    "risk_trauma":     "Contexte traumatique à risque",
    "risk_pregnancy":  "Contexte grossesse",
    "risk_infection":  "Risque infectieux élevé",
}

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase + strip accents for robust matching."""
    text = text.lower()
    for src, dst in {
        'é':'e','è':'e','ê':'e','ë':'e',
        'à':'a','â':'a','ä':'a',
        'î':'i','ï':'i',
        'ô':'o','ö':'o',
        'ù':'u','û':'u','ü':'u',
        'ç':'c','œ':'oe','æ':'ae',
    }.items():
        text = text.replace(src, dst)
    return text


def _detect_flags(text_norm: str) -> dict[str, list[str]]:
    """Returns {flag: [matched_keywords]} for every rule that fires."""
    flag_matches: dict[str, list[str]] = {}
    for keywords, flag in _RULES:
        hits = [kw for kw in keywords if _normalize(kw) in text_norm]
        if hits:
            flag_matches.setdefault(flag, []).extend(hits)
    return flag_matches


def _build_alert(flag: str, matched_keywords: list[str]) -> str:
    """
    Dynamic alert with matched context in parentheses.
    e.g. "Risque hémorragique (AOD + chute)"
    """
    base = _ALERT_LABELS.get(flag, flag)
    kws  = matched_keywords[:2]  # max 2 for readability
    kw_str = " + ".join(
        k.upper() if len(k) <= 4 else k.capitalize()
        for k in kws
    )
    return f"{base} ({kw_str})"


# ──────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ──────────────────────────────────────────────────────────────────────────────

def detect_context_flags(context_text: Optional[str]) -> dict:
    """
    Detect clinical risk flags from raw context text.

    Args:
        context_text: free-text patient context (anamnesis, framing, notes).
                      None or empty → returns empty lists, no crash.

    Returns:
        {
            "context_flags":  ["risk_bleeding", "risk_thrombosis"],
            "context_alerts": [
                "Risque hémorragique (AOD + chute)",
                "Risque de thrombose / TVP (Voyage + cancer)"
            ]
        }
    """
    if not context_text or not context_text.strip():
        return {"context_flags": [], "context_alerts": []}

    text_norm    = _normalize(context_text)
    flag_matches = _detect_flags(text_norm)

    return {
        "context_flags":  list(flag_matches.keys()),
        "context_alerts": [
            _build_alert(flag, kws)
            for flag, kws in flag_matches.items()
        ],
    }