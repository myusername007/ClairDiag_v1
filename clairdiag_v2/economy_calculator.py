"""
ClairDiag v3 — Real-time Economy Calculator

Module: 02_economy_realtime
Version: v1.0
Date: 2026-04-30

Hook: після Stage 5 (output build) в core.py
Additif uniquement — ne modifie pas la logique d'orientation.
Si JSON manquant → economic_value = None, pas d'erreur.
"""

import json
from pathlib import Path
from typing import Optional

# Chemin par défaut — relatif à ce fichier
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "data" / "economy_tariffs_fr_v1.json"


# ── 1. Loader ─────────────────────────────────────────────────────────────────

class EconomyConfig:
    """Charge le référentiel tarifs FR au démarrage."""

    def __init__(self, config_path: Path = _DEFAULT_CONFIG_PATH):
        with open(config_path, encoding="utf-8") as f:
            self.config = json.load(f)
        self.consultations = self.config["consultation_costs"]
        self.exams = self.config["examens_costs"]
        self.pathways = self.config["pathway_templates"]
        self.system_costs = self.config["system_costs_for_society"]


# Singleton chargé une fois au démarrage (gracieux si fichier absent)
_economy_config: Optional[EconomyConfig] = None

def get_economy_config(config_path: Path = _DEFAULT_CONFIG_PATH) -> Optional[EconomyConfig]:
    global _economy_config
    if _economy_config is None:
        try:
            _economy_config = EconomyConfig(config_path)
        except Exception:
            _economy_config = None
    return _economy_config


# ── 2. Lookup helpers ─────────────────────────────────────────────────────────

def get_item_cost(config: EconomyConfig, item_key: str) -> Optional[dict]:
    if item_key in config.consultations:
        item = config.consultations[item_key]
    elif item_key in config.exams:
        item = config.exams[item_key]
    else:
        return None

    delai_jours = 0.0
    if "delai_moyen_jours" in item:
        delai_jours = item["delai_moyen_jours"]
    elif "delai_moyen_heures" in item:
        delai_jours = item["delai_moyen_heures"] / 24
    elif "delai_moyen_minutes" in item:
        delai_jours = item["delai_moyen_minutes"] / (24 * 60)

    return {
        "tarif_brut": item.get("tarif_brut", 0.0),
        "reste_a_charge_avant_mutuelle": item.get("reste_a_charge_avant_mutuelle", 0.0),
        "reste_a_charge_avec_mutuelle_basique": item.get("reste_a_charge_avec_mutuelle_basique", 0.0),
        "delai_jours": delai_jours,
        "note": item.get("note", ""),
    }


# ── 3. Pathway calculator ─────────────────────────────────────────────────────

def calculate_pathway_cost(config: EconomyConfig, pathway_key: str) -> Optional[dict]:
    pathway = config.pathways.get(pathway_key)
    if not pathway:
        return None

    total_brut = 0.0
    total_avant_mutuelle = 0.0
    total_avec_mutuelle = 0.0
    items_detail = []

    for step in pathway["steps"]:
        item_key = step["item"]
        n = step["n"]
        cost = get_item_cost(config, item_key)
        if cost is None:
            continue
        total_brut += cost["tarif_brut"] * n
        total_avant_mutuelle += cost["reste_a_charge_avant_mutuelle"] * n
        total_avec_mutuelle += cost["reste_a_charge_avec_mutuelle_basique"] * n
        items_detail.append({
            "item": item_key,
            "n": n,
            "tarif_brut_unitaire": cost["tarif_brut"],
            "tarif_brut_total": cost["tarif_brut"] * n,
            "reste_a_charge_avec_mutuelle": cost["reste_a_charge_avec_mutuelle_basique"] * n,
        })

    return {
        "label": pathway.get("label", pathway_key),
        "tarif_brut_total": round(total_brut, 2),
        "reste_a_charge_avant_mutuelle_total": round(total_avant_mutuelle, 2),
        "reste_a_charge_avec_mutuelle_total": round(total_avec_mutuelle, 2),
        "delai_jours_estimatif": pathway.get("delai_jours_estimatif", 0),
        "items_detail": items_detail,
        "note": pathway.get("note", ""),
    }


def compare_pathways(config: EconomyConfig, optimal_key: str, suboptimal_key: str) -> Optional[dict]:
    optimal = calculate_pathway_cost(config, optimal_key)
    suboptimal = calculate_pathway_cost(config, suboptimal_key)
    if not optimal or not suboptimal:
        return None

    economy_patient = round(
        suboptimal["reste_a_charge_avec_mutuelle_total"]
        - optimal["reste_a_charge_avec_mutuelle_total"], 2
    )
    economy_societe = round(
        suboptimal["tarif_brut_total"] - optimal["tarif_brut_total"], 2
    )
    time_saved = round(
        suboptimal["delai_jours_estimatif"] - optimal["delai_jours_estimatif"], 1
    )
    summary = (
        f"Le parcours recommandé économise {economy_patient}€ pour vous, "
        f"{economy_societe}€ pour le système de santé, "
        f"et fait gagner {time_saved} jours."
    )
    return {
        "optimal": optimal,
        "suboptimal": suboptimal,
        "economy_patient_eur": economy_patient,
        "economy_societe_eur": economy_societe,
        "time_saved_days": time_saved,
        "summary": summary,
    }


# ── 4. Category → pathway map ─────────────────────────────────────────────────

_CATEGORY_TO_PATHWAY = {
    "fatigue_asthenie": ("fatigue_chronique_optimal", "fatigue_chronique_suboptimal"),
    "urinaire": ("cystite_simple_femme_optimal", "cystite_simple_femme_suboptimal"),
    "orl_simple": ("rhume_banal_optimal", "rhume_banal_suboptimal"),
}

_CONSULT_KEYWORDS = {
    "medecin_traitant", "specialiste", "teleconsultation", "sos_medecins", "urgences",
}

def _is_consult(item_key: str) -> bool:
    return any(k in item_key for k in _CONSULT_KEYWORDS)


# ── 5. Main hook ──────────────────────────────────────────────────────────────

def estimate_economic_value(
    config: EconomyConfig,
    v3_response: dict,
) -> Optional[dict]:
    """
    Hook principal à appeler après Stage 5 dans core.py.

    Args:
        config: EconomyConfig instance
        v3_response: réponse complète de /v3/analyze

    Returns:
        Dict economic_value à ajouter au response, ou None si pas applicable.
    """
    # Extraire category depuis le format multi-layer de v3
    clinical = v3_response.get("clinical", {})
    category = clinical.get("category") if clinical else None
    if not category:
        # fallback pour tests directs
        category = v3_response.get("general_orientation", {}).get("category")
    if not category:
        return None

    pathway_pair = _CATEGORY_TO_PATHWAY.get(category)
    if not pathway_pair:
        return None

    optimal_key, suboptimal_key = pathway_pair
    comparison = compare_pathways(config, optimal_key, suboptimal_key)
    if not comparison:
        return None

    optimal_steps = comparison["optimal"]["items_detail"]
    suboptimal_steps = comparison["suboptimal"]["items_detail"]

    consultations_avoided = max(
        0,
        sum(s["n"] for s in suboptimal_steps if _is_consult(s["item"]))
        - sum(s["n"] for s in optimal_steps if _is_consult(s["item"]))
    )
    tests_avoided = sorted(
        {s["item"] for s in suboptimal_steps if not _is_consult(s["item"])}
        - {s["item"] for s in optimal_steps if not _is_consult(s["item"])}
    )

    econ = comparison["economy_societe_eur"]
    confidence_label = "high" if econ >= 100 else ("medium" if econ >= 30 else "low")

    return {
        "applicable": True,
        "category": category,
        # Roman's required fields
        "consultations_avoided": consultations_avoided,
        "tests_avoided": tests_avoided,
        "estimated_savings_eur": econ,
        "confidence": confidence_label,
        # Champs enrichis
        "economy_patient_eur": comparison["economy_patient_eur"],
        "economy_societe_eur": econ,
        "time_saved_days": comparison["time_saved_days"],
        "patient_summary": comparison["summary"],
        "_internal_detail": {
            "optimal_pathway": comparison["optimal"]["label"],
            "suboptimal_pathway": comparison["suboptimal"]["label"],
            "optimal_cost_total_societe": comparison["optimal"]["tarif_brut_total"],
            "suboptimal_cost_total_societe": comparison["suboptimal"]["tarif_brut_total"],
        },
    }