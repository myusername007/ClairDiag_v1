"""
ClairDiag v2.0 — ReimbursementEngine (S8)
core/reimbursement_engine.py

Calcule l'économie réalisée via reimbursement_rules.json.
Compare pathway optimal vs suboptimal pour une catégorie.
Retourne EconomicData avec consultations_avoided, savings, out_of_pocket.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EconomicData:
    category: str
    pathway_optimal_id: str
    pathway_suboptimal_id: str
    optimal_total_eur: float
    suboptimal_total_eur: float
    consultations_avoided: int
    tests_avoided: List[str]
    estimated_savings_eur: float
    patient_out_of_pocket_optimal_eur: float
    patient_out_of_pocket_suboptimal_eur: float
    confidence: str  # "low" | "medium" | "high"
    audit_trail: List[str] = field(default_factory=list)


def _compute_pathway_cost(
    pathway: Dict,
    exam_tariffs: Dict,
    consult_tariffs: Dict,
) -> tuple[float, float, List[str]]:
    """
    Calcule le coût total et la part patient d'un pathway.
    Retourne (total_eur, patient_eur, items_detail).
    """
    total = 0.0
    patient = 0.0
    detail = []

    for item in pathway.get("items", []):
        key = item["key"]
        n = item.get("n", 1)
        item_type = item["type"]

        tariff_data = None
        if item_type == "exam":
            tariff_data = exam_tariffs.get(key)
        elif item_type == "consultation":
            tariff_data = consult_tariffs.get(key)

        if not tariff_data:
            detail.append(f"MISSING_TARIFF:{key}")
            continue

        tariff = tariff_data.get("tariff_eur", 0.0)
        secu_pct = tariff_data.get("secu_pct", 70) / 100
        oop = tariff_data.get("patient_out_of_pocket_eur")
        if oop is None:
            oop = tariff * (1 - secu_pct)

        total += tariff * n
        patient += oop * n
        detail.append(f"{key}×{n}: {tariff*n:.2f}€ (patient: {oop*n:.2f}€)")

    return round(total, 2), round(patient, 2), detail


class ReimbursementEngine:
    """
    Calcule l'économie réalisée par rapport au pathway suboptimal.

    Usage:
        economy = engine.estimate("cardio", ["ECG", "Echographie_cardiaque"])
        # economy.estimated_savings_eur = 234.5
    """

    def __init__(self, reimbursement_rules: Optional[Dict] = None):
        if not reimbursement_rules:
            self._exam_tariffs = {}
            self._consult_tariffs = {}
            self._pathways = []
            logger.warning("ReimbursementEngine: no rules provided")
            return

        self._exam_tariffs = reimbursement_rules.get("exam_tariffs", {})
        self._consult_tariffs = reimbursement_rules.get("consultation_tariffs", {})
        self._pathways = reimbursement_rules.get("pathways", [])

        # Index: category -> {optimal: pathway, suboptimal: pathway}
        self._category_index: Dict[str, Dict] = {}
        for p in self._pathways:
            cat = p["category"]
            pid = p["pathway_id"]
            if cat not in self._category_index:
                self._category_index[cat] = {}
            if "suboptimal" in pid:
                self._category_index[cat]["suboptimal"] = p
            else:
                self._category_index[cat]["optimal"] = p

        logger.info(
            f"ReimbursementEngine: {len(self._exam_tariffs)} exam tariffs, "
            f"{len(self._consult_tariffs)} consult tariffs, "
            f"{len(self._category_index)} categories"
        )

    def estimate(
        self,
        pathway_category: str,
        proposed_exams: Optional[List[str]] = None,
    ) -> Optional[EconomicData]:
        """
        Calcule l'économie pour une catégorie.

        Returns None si aucun pathway défini pour cette catégorie.
        """
        paths = self._category_index.get(pathway_category)
        if not paths:
            logger.debug(f"No pathway for category: {pathway_category}")
            return None

        optimal = paths.get("optimal")
        suboptimal = paths.get("suboptimal")

        if not optimal or not suboptimal:
            logger.debug(f"Missing optimal or suboptimal for: {pathway_category}")
            return None

        opt_total, opt_patient, opt_detail = _compute_pathway_cost(
            optimal, self._exam_tariffs, self._consult_tariffs
        )
        sub_total, sub_patient, sub_detail = _compute_pathway_cost(
            suboptimal, self._exam_tariffs, self._consult_tariffs
        )

        savings = round(sub_total - opt_total, 2)

        # Tests évités = items suboptimal non présents dans optimal
        opt_keys = {i["key"] for i in optimal.get("items", [])}
        sub_keys = {i["key"] for i in suboptimal.get("items", [])}
        tests_avoided = list(sub_keys - opt_keys)

        # Consultations évitées = count consult suboptimal - count consult optimal
        opt_consults = sum(i.get("n", 1) for i in optimal.get("items", []) if i["type"] == "consultation")
        sub_consults = sum(i.get("n", 1) for i in suboptimal.get("items", []) if i["type"] == "consultation")
        consultations_avoided = max(0, sub_consults - opt_consults)

        # Confidence basée sur la présence des tarifs
        missing = [d for d in opt_detail + sub_detail if "MISSING_TARIFF" in d]
        if not missing:
            confidence = "high"
        elif len(missing) <= 2:
            confidence = "medium"
        else:
            confidence = "low"

        audit = [
            f"optimal: {opt_total}€ (patient: {opt_patient}€)",
            f"suboptimal: {sub_total}€ (patient: {sub_patient}€)",
            f"savings: {savings}€",
        ] + missing

        return EconomicData(
            category=pathway_category,
            pathway_optimal_id=optimal["pathway_id"],
            pathway_suboptimal_id=suboptimal["pathway_id"],
            optimal_total_eur=opt_total,
            suboptimal_total_eur=sub_total,
            consultations_avoided=consultations_avoided,
            tests_avoided=tests_avoided,
            estimated_savings_eur=savings,
            patient_out_of_pocket_optimal_eur=opt_patient,
            patient_out_of_pocket_suboptimal_eur=sub_patient,
            confidence=confidence,
            audit_trail=audit,
        )

    def get_exam_tariff(self, exam_key: str) -> Optional[Dict]:
        return self._exam_tariffs.get(exam_key)

    def get_consult_tariff(self, consult_key: str) -> Optional[Dict]:
        return self._consult_tariffs.get(consult_key)

    def is_ready(self) -> bool:
        return len(self._category_index) > 0

    def available_categories(self) -> List[str]:
        return list(self._category_index.keys())