"""
ClairDiag v2 — Medical Basis Layer (TASK #016)
Output enrichment for trust & regulatory positioning.

CONSTRAINTS:
- DO NOT touch probability engine / ranking / safety floor / scoring
- READ-ONLY overlay on output
- Uses static medical_basis.json
"""

from __future__ import annotations
import json
import os
from typing import Optional

# ── Load static file once at import ──────────────────────────────────────────

_BASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "medical_basis.json")

def _load_bases() -> dict:
    try:
        with open(_BASES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

_BASES: dict = _load_bases()


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def build_medical_basis(
    top_hypothesis: Optional[str],
    symptoms_normalized: list[str],
) -> dict:
    """
    Build medical_basis block for output enrichment.

    Always returns consistent structure:
    {
        "guideline_family": "...",
        "clinical_basis": "...",
        "coherence_level": "coherent_with_clinical_logic",
        "validation_status": "pending_physician_validation"
    }
    """
    entry = _BASES.get(top_hypothesis or "", _BASES.get("_default", {}))

    if not entry:
        entry = _BASES.get("_default", {})

    # clinical_basis: join list → short readable sentence
    raw_basis = entry.get("clinical_basis", [])
    if isinstance(raw_basis, list) and raw_basis:
        clinical_basis_str = " + ".join(raw_basis[:3])
    else:
        clinical_basis_str = "orientation basée sur symptômes présentés"

    return {
        "guideline_family":  entry.get("guideline_family", "general clinical practice"),
        "clinical_basis":    clinical_basis_str,
        "coherence_level":   "coherent_with_clinical_logic",
        "validation_status": "pending_physician_validation",
    }