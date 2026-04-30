"""
ClairDiag v3 — Local Healthcare Directory Engine

Module: local_directory_engine
Version: v1.0
Date: 2026-04-30

DIFFERENTIATEUR UNIQUE — aucun concurrent ne fait de routing commune-level.
Pivot pour entrée public sector France (mairie, ARS PACA).

PRINCIPE:
1. Patient saisit sa commune (code postal + nom)
2. ClairDiag oriente vers ressources LOCALES précises:
   - Médecin traitant le plus disponible
   - Maison de santé sans RDV
   - SOS Médecins ligne directe locale
   - Hôpital d'urgences le plus proche
3. Si commune pas dans annuaire → fallback national (ressources génériques)

INTÉGRATION:
- Hook après stage 5 (output build) du pipeline v3
- Si patient_context contient code_postal → enrichir réponse avec local_resources
- Si pas de code_postal → fallback ressources nationales

NE CASSE PAS la régression:
- Module additif, ne change pas l'orientation
- Si JSON manquant → local_resources = None, jamais d'erreur

EXTENSIBILITÉ:
- Pour ajouter une commune: ajouter une entrée dans communes/ du JSON
- Format INSEE-based pour intégration future CPAM / ARS
"""

import json
import math
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

# CONFIG_PATH: JSON est dans data/ au même niveau que le module
CONFIG_PATH = Path(__file__).parent / "data" / "local_directory_v1.json"


# ============================================================
# 1. Config loader
# ============================================================

class LocalDirectoryConfig:
    """Charge l'annuaire local au démarrage."""

    def __init__(self, config_path: Path = CONFIG_PATH):
        with open(config_path, encoding="utf-8") as f:
            self.config = json.load(f)
        self.communes = self.config["communes"]
        self.fallback = self.config["fallback_national"]


# ============================================================
# 2. Helpers
# ============================================================

def _normalize_commune_key(code_postal: str, nom: str = None) -> Optional[str]:
    """
    Construit la clé de lookup pour une commune.
    Format: {code_postal}_{nom_normalise} ou juste {code_postal}
    """
    if not code_postal:
        return None
    if not nom:
        return code_postal
    nom_norm = nom.lower()
    nom_norm = nom_norm.replace(" ", "_").replace("-", "_").replace("'", "")
    # Supprimer accents ASCII-safe
    replacements = {
        "é": "e", "è": "e", "ê": "e", "à": "a", "â": "a",
        "ù": "u", "û": "u", "î": "i", "ô": "o", "ç": "c",
    }
    for src, dst in replacements.items():
        nom_norm = nom_norm.replace(src, dst)
    return f"{code_postal}_{nom_norm}"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance en km entre deux points géographiques."""
    R = 6371
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_code_postal(code_postal: str) -> Optional[str]:
    """Anonymise un code postal en gardant les 2 premiers chiffres (département)."""
    if not code_postal:
        return None
    return code_postal[:2] + "***"


# ============================================================
# 3. Lookup logic
# ============================================================

def lookup_commune(
    config: LocalDirectoryConfig,
    code_postal: str,
    nom: str = None,
) -> Optional[dict]:
    """
    Cherche une commune dans l'annuaire.
    Essaie d'abord code_postal + nom, puis code_postal seul.
    Retourne le dict commune complet, ou None si non trouvée.
    """
    if not code_postal:
        return None

    # Essai 1: clé complète (code_postal + nom)
    if nom:
        key = _normalize_commune_key(code_postal, nom)
        if key and key in config.communes:
            return config.communes[key]

    # Essai 2: clé code_postal seul
    key_cp = _normalize_commune_key(code_postal)
    if key_cp in config.communes:
        return config.communes[key_cp]

    # Essai 3: scan par champ code_postal (fallback robuste)
    for commune_data in config.communes.values():
        if commune_data.get("code_postal") == code_postal:
            return commune_data

    return None


def find_closest_specialists(commune: dict, specialite: str, n: int = 2) -> list:
    """
    Trouve les n spécialistes les plus proches pour une spécialité.
    Filtre par champ 'specialite', trie par distance_km.
    """
    specialists = commune.get("specialistes_proches", [])
    matching = [s for s in specialists if s.get("specialite") == specialite]
    matching_sorted = sorted(matching, key=lambda s: s.get("distance_km", 999))
    return matching_sorted[:n]


def find_available_medecin_traitant(
    commune: dict,
    accepting_new_patients: bool = True,
) -> Optional[dict]:
    """
    Trouve le médecin traitant le plus disponible.
    Filtre par accepte_nouveaux_patients si demandé.
    Trie par délai RDV croissant.
    """
    mts = commune.get("medecins_traitants", [])
    if accepting_new_patients:
        mts = [m for m in mts if m.get("accepte_nouveaux_patients", False)]
    if not mts:
        return None
    return sorted(mts, key=lambda m: m.get("delai_rdv_jours_typique", 999))[0]


# ============================================================
# 4. Main hook: enrich v3 response with local resources
# ============================================================

def enrich_with_local_resources(
    config: LocalDirectoryConfig,
    v3_response: dict,
    patient_context: dict,
) -> dict:
    """
    Hook principal: enrichit le v3_response avec ressources locales.

    Args:
        config: LocalDirectoryConfig instance
        v3_response: réponse complète de /v3/analyze (après _flatten)
        patient_context: doit contenir code_postal (et idéalement commune)

    Returns:
        Dict local_resources à ajouter au response.
        Jamais None — toujours fallback national si commune non trouvée.
    """
    code_postal = (patient_context or {}).get("code_postal")
    nom_commune = (patient_context or {}).get("commune")

    if not code_postal:
        return _fallback_national_resources(config, v3_response)

    commune = lookup_commune(config, code_postal, nom_commune)
    if not commune:
        return _fallback_national_resources(config, v3_response)

    # Support both flat (after _flatten) and nested triage
    urgency = (
        v3_response.get("urgency")
        or v3_response.get("final_triage")
        or (v3_response.get("triage") or {}).get("urgency")
        or "non_urgent"
    )

    # Specialist hint: from general_orientation or flat field
    general_orientation = v3_response.get("general_orientation") or {}
    specialist_hint = (
        (general_orientation.get("possible_specialist") if isinstance(general_orientation, dict) else None)
        or v3_response.get("specialist_hint")
    )

    resources = {
        "applicable": True,
        "commune_found": commune.get("nom"),
        "code_postal": code_postal,
        "ars": commune.get("ars"),
        "primary_recommendation": None,
        "alternatives": [],
        "urgences": commune.get("urgences"),
        "teleconsultation": commune.get("teleconsultation"),
    }

    if urgency == "urgent":
        resources["primary_recommendation"] = {
            "action": "Appelez immédiatement le 15 (SAMU)",
            "telephone": "15",
            "description": "Régulation médicale en urgence",
        }
        urgences_proches = commune.get("urgences", {}).get("urgences_hospitalieres_proches", [])
        resources["alternatives"] = [
            {
                "action": f"Urgences hospitalières — {h['nom']}",
                "adresse": h["adresse"],
                "duree_route_minutes": h.get("duree_route_minutes"),
            }
            for h in urgences_proches
        ]

    elif urgency in ("urgent_medical_review", "medical_urgent"):
        sos = commune.get("urgences", {}).get("sos_medecins")
        if sos:
            resources["primary_recommendation"] = {
                "action": "Appelez SOS Médecins pour consultation rapide",
                "telephone": sos.get("telephone"),
                "description": sos.get("description"),
                "delai_typique_minutes": sos.get("delai_typique_minutes"),
            }
        else:
            resources["primary_recommendation"] = {
                "action": "Téléconsultation disponible maintenant",
                "url": commune.get("teleconsultation", {}).get("doctolib"),
            }

    elif urgency == "medical_consultation":
        # Spécialiste si pertinent
        if specialist_hint:
            specialists = find_closest_specialists(commune, specialist_hint, n=2)
            if specialists:
                resources["primary_recommendation"] = {
                    "action": f"Consultation {specialist_hint}",
                    "specialiste_propose": specialists[0],
                    "alternatives": specialists[1:] if len(specialists) > 1 else [],
                }

        # Sinon médecin traitant disponible
        if not resources["primary_recommendation"]:
            mt = find_available_medecin_traitant(commune, accepting_new_patients=True)
            if mt:
                resources["primary_recommendation"] = {
                    "action": "Consultation médecin traitant",
                    "medecin_propose": mt,
                    "delai_jours": mt.get("delai_rdv_jours_typique"),
                }
            else:
                # Pas de MT acceptant nouveaux patients → MSP
                msps = commune.get("maisons_sante", [])
                if msps:
                    resources["primary_recommendation"] = {
                        "action": "Maison de santé pluriprofessionnelle",
                        "msp": msps[0],
                        "note": "Accueil possible sans RDV",
                    }

    else:  # non_urgent
        resources["primary_recommendation"] = {
            "action": "Auto-soin recommandé",
            "description": "Surveillance des symptômes, retour si aggravation",
        }
        msps = commune.get("maisons_sante", [])
        if msps:
            resources["alternatives"] = [{
                "action": "Si vous préférez consulter : Maison de santé locale",
                "msp": msps[0],
            }]

    return resources


def _fallback_national_resources(
    config: LocalDirectoryConfig,
    v3_response: dict,
) -> dict:
    """Fallback quand commune non identifiée: ressources nationales génériques."""
    urgency = (
        v3_response.get("urgency")
        or v3_response.get("final_triage")
        or "non_urgent"
    )

    if urgency == "urgent":
        primary = {
            "action": "Appelez le 15 (SAMU)",
            "telephone": config.fallback["samu"],
        }
    elif urgency in ("urgent_medical_review", "medical_urgent"):
        primary = {
            "action": "Appelez SOS Médecins",
            "telephone": config.fallback["sos_medecins_national"],
        }
    elif urgency == "medical_consultation":
        primary = {
            "action": "Téléconsultation ou consultation médecin traitant",
            "url": config.fallback["doctolib_national"],
            "ameli": config.fallback["ameli_trouver_medecin"],
        }
    else:
        primary = {
            "action": "Auto-soin, surveillance des symptômes",
        }

    return {
        "applicable": True,
        "commune_found": None,
        "fallback_used": True,
        "primary_recommendation": primary,
        "national_resources": config.fallback,
        "note": (
            "Annuaire local non disponible pour votre commune. "
            "Ressources nationales fournies."
        ),
    }


# ============================================================
# 5. Pilot mode — ARS-ready export wrapper
# ============================================================

def enrich_with_pilot_mode(
    config: LocalDirectoryConfig,
    v3_response: dict,
    patient_context: dict,
    region: str = "PACA",
    anonymized: bool = True,
) -> dict:
    """
    Wrapper requis par Roman pour export ARS-ready en mode pilot.

    Args:
        config: LocalDirectoryConfig instance
        v3_response: réponse v3 originale
        patient_context: contexte patient (avec code_postal)
        region: code région ARS (PACA, IDF, etc.)
        anonymized: si True, anonymise le code postal dans le log export

    Returns:
        Dict avec local_resources + pilot mode metadata
    """
    local = enrich_with_local_resources(config, v3_response, patient_context)

    code_postal = (patient_context or {}).get("code_postal")
    cp_export = _hash_code_postal(code_postal) if anonymized else code_postal

    general_orientation = v3_response.get("general_orientation") or {}
    category = (
        general_orientation.get("category")
        if isinstance(general_orientation, dict)
        else None
    ) or (v3_response.get("clinical") or {}).get("category")

    urgency = (
        v3_response.get("urgency")
        or v3_response.get("final_triage")
        or (v3_response.get("triage") or {}).get("urgency")
    )

    return {
        "pilot_mode": True,
        "region": region,
        "export_format": "ARS_ready",
        "anonymized": anonymized,
        "local_resources": local,
        "session_metadata": {
            "code_postal": cp_export,
            "category": category,
            "urgency": urgency,
            "red_flag_triggered": v3_response.get("red_flag_triggered", False),
            "timestamp": _now_iso(),
        },
    }