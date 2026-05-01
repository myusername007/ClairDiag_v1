"""
ClairDiag v3 — Care Pathway Engine
Module: care_pathway_engine
Version: v1.0

Charger care_pathway_rules_v1.json (20 catégories médicales) et enrichir
le response v3 avec orientation structurée (specialists, exams, urgency,
warning signs, patient message).

INTEGRATION dans core.py:
    from care_pathway_engine import enrich_with_care_pathway
    # Après local_directory hook, avant return:
    final_response = enrich_with_care_pathway(
        final_response, free_text=free_text, patient_context=patient_context
    )

STRUCTURE du v3_response (core.py):
    response["clinical"]["category"]     — catégorie détectée par pipeline
    response["triage"]["urgency"]        — urgency du pipeline
    response["triage"]["urgent_message"] — si urgence déjà détectée
    response["care_pathway"]             — AJOUTÉ par ce module

NE CASSE PAS:
    - JSON manquant → fallback gracieux, response inchangé
    - Category inconnue → applicable=False, pas de crash
    - Champs uniquement AJOUTÉS, jamais supprimés/modifiés
    - try/except dans core.py protège le pipeline principal

REGRESSION:
    90/90 + 49/50 + tests adversariaux doivent passer sans modification.
"""

import json
import logging
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).parent / "data" / "care_pathway_rules_v1.json"
logger = logging.getLogger(__name__)


# ============================================================
# 1. Loader — singleton pattern
# ============================================================

class CarePathwayConfig:
    """
    Charge les règles d'orientation au démarrage.
    Singleton — un seul chargement par process.
    """

    _instance = None

    def __new__(cls, config_path: Path = CONFIG_PATH):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize(config_path)
        return cls._instance

    def _initialize(self, config_path: Path):
        try:
            with open(config_path, encoding="utf-8") as f:
                self.config = json.load(f)
            self.rules_by_category = {
                r["category_id"]: r for r in self.config["rules"]
            }
            self.global_rules = self.config["global_rules"]
            self.loaded_count = len(self.rules_by_category)
            logger.info(
                f"CarePathwayConfig loaded: {self.loaded_count} categories"
            )
        except FileNotFoundError:
            logger.error(f"care_pathway_rules_v1.json not found at {config_path}")
            self.config = None
            self.rules_by_category = {}
            self.global_rules = {}
            self.loaded_count = 0
        except json.JSONDecodeError as e:
            logger.error(f"care_pathway_rules_v1.json invalid JSON: {e}")
            self.config = None
            self.rules_by_category = {}
            self.global_rules = {}
            self.loaded_count = 0

    def is_available(self) -> bool:
        return self.config is not None and self.loaded_count > 0

    def get_rule(self, category_id: str) -> Optional[dict]:
        return self.rules_by_category.get(category_id)


# ============================================================
# 2. Category mapping — pipeline names → JSON category_ids
# ============================================================

# Maps від category names що використовує core.py → JSON category_ids
# Розширити якщо з'являться нові category names в pipeline
_CATEGORY_MAPPING = {
    # Точні імена з common_symptom_mapping (через loader.py)
    "ORL_simple":                       "ORL",
    "ORL":                              "ORL",
    "dermatologie_simple":              "dermatologie",
    "dermatologie":                     "dermatologie",
    "digestif_simple":                  "digestif",
    "digestif":                         "digestif",
    "gynecologique_simple":             "gynecologique",
    "gynecologique":                    "gynecologique",
    "metabolique_hormonal_suspect":     "metabolique_endocrino",
    "metabolique_endocrino":            "metabolique_endocrino",
    "sommeil_stress_anxiete_non_urgent":"sommeil_stress",
    "sommeil_stress":                   "sommeil_stress",
    "general_vague_non_specifique":     "douleur_generale_vague",
    "general_vague":                    "douleur_generale_vague",
    "douleur_generale_vague":           "douleur_generale_vague",
    "musculo_squelettique":             "musculo_squelettique",
    "fatigue_asthenie":                 "fatigue_asthenie",
    "urinaire":                         "urinaire",
    "cardio":                           "cardio",
    "cardiologique":                    "cardio",
    "neuro":                            "neuro",
    "neurologique":                     "neuro",
    "respiratoire":                     "respiratoire",
    "psychiatrie_suicide":              "psychiatrie_suicide",
    "allergie":                         "allergie",
    "infection_fievre":                 "infection_fievre",
    "trauma":                           "trauma",
    "grossesse":                        "grossesse",
    "pediatrie":                        "pediatrie",
    "pied_talon_cheville":              "pied_talon_cheville",
    # red_flag géré séparément par pipeline — pas de care_pathway ici
    "red_flag_detected":                None,
}


def _map_category(raw_category: Optional[str]) -> Optional[str]:
    """
    Convertit un category name du pipeline v3 → JSON category_id.
    Essaie d'abord le mapping exact, puis retourne tel quel
    (au cas où le category_id est déjà correct).
    """
    if not raw_category:
        return None
    mapped = _CATEGORY_MAPPING.get(raw_category)
    if mapped is not None:
        return mapped  # peut être None si red_flag_detected
    # Pas dans le mapping → essayer tel quel (category_id direct)
    return raw_category


# ============================================================
# 3. Category detection via triggers (fallback si pipeline vague)
# ============================================================

def detect_category_from_text(text: str, config: CarePathwayConfig) -> Optional[str]:
    """
    Si le pipeline n'a pas détecté de catégorie (general_vague),
    tente de détecter via les triggers du JSON.

    Logique:
    - Compter matches de triggers pour chaque catégorie
    - Retourner la catégorie avec le plus de matches (≥ 1)
    - Si 0 match → None (laisse le pipeline existant gérer)
    """
    if not config.is_available():
        return None

    text_lower = text.lower()
    best_match = None
    best_count = 0

    for category_id, rule in config.rules_by_category.items():
        triggers = rule.get("triggers", [])
        match_count = sum(1 for trig in triggers if trig.lower() in text_lower)
        if match_count > best_count:
            best_count = match_count
            best_match = category_id

    return best_match if best_count >= 1 else None


# ============================================================
# 4. Urgency matching depuis les urgency_rules JSON
# ============================================================

def match_urgency_level(rule: dict, free_text: str) -> Optional[str]:
    """
    Détermine le niveau d'urgence selon les urgency_rules du JSON.
    Vérifie urgent en premier (sécurité prime).
    """
    urgency_rules = rule.get("urgency_rules", {})
    text_lower = free_text.lower()

    for level in ["urgent", "medical_urgent", "consultation", "non_urgent"]:
        criteria = urgency_rules.get(level, [])
        if not criteria:
            continue
        for criterion in criteria:
            criterion_lower = criterion.lower()
            # Extraire mots significatifs (> 4 chars) pour éviter faux positifs
            keywords = [w for w in criterion_lower.split() if len(w) > 4]
            if keywords and any(kw in text_lower for kw in keywords[:3]):
                return level

    return None


# ============================================================
# 5. Specialist resolution — fallback doctrine enforcement
# ============================================================

def resolve_specialist(rule: dict, urgency_level: str, has_red_flag: bool = False) -> dict:
    """
    Sélectionne le spécialiste selon la fallback doctrine:
    1. Red flag → urgences (premier de primary)
    2. Sinon → primary specialist de la catégorie
    3. MT uniquement si fallback légitime (vague, fatigue, multi-systémique)
    """
    specialists = rule.get("specialists", {})
    primary = specialists.get("primary", [])
    secondary = specialists.get("secondary", [])
    fallback = specialists.get("fallback", [])

    if has_red_flag or urgency_level == "urgent":
        recommended = primary[0] if primary else "Urgences hospitalières / 15"
        return {
            "primary_recommended": recommended,
            "alternatives": primary[1:] if len(primary) > 1 else [],
            "fallback_if_unavailable": fallback,
            "rationale": "Red flag ou urgence — orientation prioritaire",
        }

    if primary:
        return {
            "primary_recommended": primary[0],
            "alternatives": primary[1:] + secondary,
            "fallback_if_unavailable": fallback,
            "rationale": "Spécialiste de première intention pour cette zone",
        }

    if fallback:
        return {
            "primary_recommended": fallback[0],
            "alternatives": fallback[1:],
            "fallback_if_unavailable": [],
            "rationale": "Fallback légitime (cas vague ou multi-systémique)",
        }

    return {
        "primary_recommended": "Consultation médicale",
        "alternatives": [],
        "fallback_if_unavailable": [],
        "rationale": "Aucune orientation spécifique disponible",
    }


# ============================================================
# 6. Minimum output guarantee
# ============================================================

def _enforce_minimum_output(care_pathway: dict) -> dict:
    """
    Garantit que les 5 champs minimaux sont présents et non vides.
    global_rules.minimum_output_guarantee du JSON.
    """
    if not care_pathway.get("urgency_level"):
        care_pathway["urgency_level"] = "consultation"

    if not care_pathway.get("exams") or not any(
        care_pathway["exams"].get(k)
        for k in ["first_line", "if_persistent", "if_red_flags"]
    ):
        care_pathway["exams"] = {
            "first_line": ["Examen clinique"],
            "if_persistent": [],
            "if_red_flags": [],
        }

    specialist = care_pathway.get("specialist", {})
    if not specialist.get("primary_recommended"):
        specialist["primary_recommended"] = "Médecin traitant pour orientation initiale"
    care_pathway["specialist"] = specialist

    if not care_pathway.get("warning_signs"):
        care_pathway["warning_signs"] = [
            "Aggravation des symptômes",
            "Apparition de fièvre",
            "Douleur intense ou inhabituelle",
        ]

    if not care_pathway.get("patient_message"):
        care_pathway["patient_message"] = (
            "Une consultation médicale est recommandée. "
            "Surveillez les signes d'aggravation et consultez en urgence si nécessaire."
        )

    return care_pathway


# ============================================================
# 7. Main hook — enrich v3 response
# ============================================================

def enrich_with_care_pathway(
    v3_response: dict,
    free_text: str = "",
    patient_context: Optional[dict] = None,
    config: Optional["CarePathwayConfig"] = None,
) -> dict:
    """
    Hook principal: enrichit le response v3 avec care_pathway.

    Lit la catégorie depuis v3_response["clinical"]["category"]
    (structure réelle de core.py), avec fallback sur text triggers.

    Args:
        v3_response:    response complet du pipeline v3
        free_text:      texte original du patient (pour fallback detection)
        patient_context: contexte patient (age, sex, etc.)
        config:         instance CarePathwayConfig (défaut: singleton)

    Returns:
        v3_response enrichi avec champ "care_pathway"

    Ne modifie jamais les champs existants — ADDITIVE uniquement.
    """
    if config is None:
        config = CarePathwayConfig()

    if not config.is_available():
        v3_response["care_pathway"] = {
            "applicable": False,
            "reason": "care_pathway_rules_v1.json non disponible",
        }
        return v3_response

    if patient_context is None:
        patient_context = {}

    # 1. Récupérer category depuis structure réelle de core.py
    #    Priorité: clinical.category > general_orientation.category > racine
    raw_category = (
        v3_response.get("clinical", {}).get("category")
        or v3_response.get("general_orientation", {}).get("category")
        or v3_response.get("category")
        or v3_response.get("category_refined_to")
    )

    # 2. Mapper vers JSON category_id
    json_category_id = _map_category(raw_category)

    # 3. Si vague ou non détectée → tenter détection via triggers texte
    vague_categories = {
        "general_vague", "general_vague_non_specifique", "douleur_generale_vague", None
    }
    if json_category_id in vague_categories and free_text:
        detected = detect_category_from_text(free_text, config)
        if detected and detected != "douleur_generale_vague":
            json_category_id = detected
            logger.debug(f"care_pathway: text fallback detected '{detected}' from '{raw_category}'")

    # 4. Cas spéciaux — category mappée à None (red_flag, etc.)
    if json_category_id is None:
        v3_response["care_pathway"] = {
            "applicable": False,
            "reason": "Catégorie non applicable au care_pathway (red flag ou cas spécial)",
        }
        return v3_response

    # 5. Lookup rule
    rule = config.get_rule(json_category_id)
    if not rule:
        v3_response["care_pathway"] = {
            "applicable": False,
            "reason": f"Catégorie '{json_category_id}' absente du JSON (mapping à étendre?)",
        }
        return v3_response

    # 6. Urgency: pipeline d'abord, puis match JSON, puis défaut safe
    pipeline_urgency = (
        v3_response.get("triage", {}).get("urgency")
        or v3_response.get("final_triage")
        or v3_response.get("urgency_level")
    )
    urgency_level = pipeline_urgency or match_urgency_level(rule, free_text) or "consultation"

    # 7. Red flag check depuis triage layer
    triage = v3_response.get("triage", {})
    has_red_flag = (
        triage.get("urgency") in ("urgent", "medical_urgent")
        or bool(triage.get("urgent_message"))
        or v3_response.get("red_flag_triggered", False)
    )

    # 8. Résoudre spécialiste
    specialist_info = resolve_specialist(rule, urgency_level, has_red_flag)

    # 9. Construire care_pathway
    care_pathway = {
        "applicable": True,
        "matched_category": json_category_id,
        "source_category": raw_category,          # debug: catégorie originale pipeline
        "urgency_level": urgency_level,
        "specialist": specialist_info,
        "exams": rule.get("exams", {}),
        "warning_signs": rule.get("warning_signs", []),
        "patient_message": rule.get("patient_message", ""),
        "economic_logic": rule.get("economic_logic", ""),
        "time_gain_logic": rule.get("time_gain_logic", ""),
    }

    # 10. Override flag pour psychiatrie_suicide
    if rule.get("override_all_other_logic"):
        care_pathway["override_all_other_logic"] = True

    # 11. Minimum output guarantee
    care_pathway = _enforce_minimum_output(care_pathway)

    v3_response["care_pathway"] = care_pathway
    return v3_response


# ============================================================
# 8. Public API (façade)
# ============================================================

def get_engine() -> CarePathwayConfig:
    """Singleton accessor — à utiliser au démarrage du backend."""
    return CarePathwayConfig()


def enrich(
    v3_response: dict,
    free_text: str = "",
    patient_context: Optional[dict] = None,
) -> dict:
    """Façade simplifiée pour intégration dans core.py."""
    return enrich_with_care_pathway(v3_response, free_text, patient_context)