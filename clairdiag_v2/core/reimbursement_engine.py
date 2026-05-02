"""
ClairDiag v2.0 — ReimbursementEngine
core/reimbursement_engine.py

Calcule les données de remboursement depuis reimbursement_rules.json.
Contenu pending — interface définie.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ReimbursementEngine:
    """
    Calcule les estimations de remboursement Sécu/mutuelle.
    Rules: reimbursement_rules.json (content pending from client).
    """

    def __init__(self, reimbursement_rules: Optional[List[Dict]] = None):
        self._rules = reimbursement_rules or []
        logger.info(f"ReimbursementEngine: {len(self._rules)} rules (pending content)")

    def calculate(
        self,
        specialist: str,
        exams: List[str],
        patient_context: Optional[Dict] = None,
    ) -> Dict:
        """
        Calcule les coûts et remboursements estimés.

        Returns:
            {"total_estimated_cost_eur": float|None, "secu_coverage_pct": float|None,
             "items": [...], "note": str}
        """
        if not self._rules:
            return {
                "total_estimated_cost_eur": None,
                "secu_coverage_pct": None,
                "items": [],
                "note": "reimbursement_rules.json content pending",
            }
        # TODO: implement when JSON provided
        return {"total_estimated_cost_eur": None, "secu_coverage_pct": None, "items": []}

    def is_ready(self) -> bool:
        return len(self._rules) > 0
