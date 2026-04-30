"""
ClairDiag v1.1.0 — Feature Extractor (Stage 3)

Module: feature_extractor
Version: v1.0
Date: 2026-04-30

ROLE:
- Єдине джерело truth для abstract patterns (ABS-01..ABS-08)
- Бере output common_symptom_mapper + medical_normalizer + patient_context
- Продукує structured features dict з тегами що очікують ABS-патерни
- НЕ замінює mapper — є bridge поверх нього

INTÉGRATION dans core.py:
    from feature_extractor import extract_features

    # Після Step 1 (mapped = common_symptom_mapper)
    # Після Step 1b (norm_text вже є)
    features = extract_features(
        free_text=free_text,
        norm_text=norm_text,
        mapped=mapped,
        norm_tokens=norm,       # output normalize_to_medical_tokens
        patient_context=patient_context,
    )
    # Передати в pattern_evaluator замість run_pattern_engine (або після)

NE CASSE PAS:
- Module additif. Si extraction échoue → features vides → abstract patterns ne matchent pas
  → fallback to token layer (pattern_engine_v3). Pipeline intact.
"""

import re
from typing import Optional


# ============================================================
# 1. Symptom tag bridge
# Mapper tokens → ABS symptom tags
# ============================================================

# Mapping: medical_normalizer token → ABS symptom tag(s)
# Un token peut produire plusieurs tags ABS si pertinent
_TOKEN_TO_ABS: dict[str, list[str]] = {
    # Cardio
    "douleur_thoracique":             ["douleur_thoracique"],
    "douleur_thoracique_oppressive":  ["douleur_thoracique", "oppression_thoracique"],
    "oppression_thoracique":          ["oppression_thoracique"],
    "sueur_froide":                   ["sueurs_profuses"],
    "palpitations":                   ["palpitations"],
    "dyspnee":                        ["dyspnee"],
    "fatigue_intense":                ["fatigue_inhabituelle_aigue"],
    "fatigue":                        ["fatigue_inhabituelle_aigue"],
    "douleur_abdominale":             ["douleur_epigastrique"],  # atypique SCA
    "pyrosis":                        ["douleur_epigastrique"],
    "reflux_gastro_oesophagien":      ["douleur_epigastrique"],
    "dyspepsie":                      ["douleur_epigastrique"],

    # Neuro
    "cephalee":                       ["cephalee"],
    "cephalee_intense":               ["cephalee", "cephalee_intense"],
    "confusion":                      ["confusion"],
    "somnolence":                     ["somnolence"],
    "trouble_comportement":           ["trouble_comportement_recent"],
    "trouble_equilibre":              ["trouble_comportement_recent"],
    "vomissements":                   ["vomissements_centraux"],
    "nausees":                        ["vomissements_centraux"],  # signal indirect
    "faiblesse_membre":               ["faiblesse_unilaterale"],
    "trouble_parole":                 ["trouble_parole"],
    "asymetrie_faciale":              ["asymetrie_faciale"],
    "trouble_visuel":                 ["trouble_visuel_brutal"],

    # Infection / sepsis
    "fievre":                         ["fievre", "fievre_38_5_plus"],
    "frissons":                       ["frissons", "fievre"],
    "tachycardie":                    ["tachycardie"],
    "hypotension":                    ["hypotension"],
    "marbrures":                      ["marbrures"],
    "faiblesse_intense":              ["faiblesse_intense"],
    "malaise_general":                ["faiblesse_intense"],
    "myalgies":                       ["faiblesse_intense"],

    # Gynéco
    "douleur_pelvienne":              ["douleur_pelvienne", "douleur_abdominale_basse"],
    "amenorrhee_suspecte":            ["retard_regles"],
    "trouble_cycle":                  ["retard_regles"],
    "leucorrhees":                    ["metrorragies"],  # signal indirect gynéco

    # Dyspnée variants
    "toux":                           ["dyspnee"],  # toujours partiel
    "essoufflement":                  ["dyspnee", "essoufflement_progressif"],
    "orthopnee":                      ["essoufflement_progressif"],
    "douleur_mollet":                 ["douleur_pleuretique"],  # TVP → EP signal
    "douleur_membre_inferieur":       ["douleur_pleuretique"],

    # ORL (pour ABS non couvert — pas de mapping nécessaire)
    "rhinorrhee":                     [],
    "congestion_nasale":              [],
    "odynophagie":                    [],
    "eruption_cutanee":               [],
    "prurit":                         [],
}

# Mapping: common_symptom_mapper patient_expression → ABS symptom tags
# Pour les expressions capturées par mapper mais pas par normalizer
_MAPPER_CAT_TO_ABS: dict[str, list[str]] = {
    "urinaire":                       [],
    "ORL_simple":                     [],
    "dermatologie_simple":            [],
    "digestif_simple":                ["douleur_epigastrique"],
    "fatigue_asthenie":               ["fatigue_inhabituelle_aigue"],
    "musculo_squelettique":           [],
    "gynecologique_simple":           ["douleur_pelvienne", "douleur_abdominale_basse"],
    "sommeil_stress_anxiete_non_urgent": [],
    "metabolique_hormonal_suspect":   [],
    "general_vague":                  [],
}


def _map_tokens_to_abs_symptoms(norm_tokens: list[str]) -> list[str]:
    """Traduit les tokens normalizer en symptom tags ABS."""
    result = set()
    for token in norm_tokens:
        for abs_tag in _TOKEN_TO_ABS.get(token, []):
            result.add(abs_tag)
    return list(result)


# ============================================================
# 2. Risk factors extraction
# ============================================================

# Expressions → risk_factor tag
_RISK_FACTOR_PATTERNS: list[tuple[list[str], str]] = [
    (["tabac", "fume", "fumeur", "fumeuse", "cigarette"], "tabac_actif"),
    (["ancien fumeur", "ancienne fumeuse", "arrêté de fumer", "ex-fumeur"], "tabac_sevre"),
    (["hypertension", "tension artérielle", "hypertendu", "hypertendus", "hta"], "HTA"),
    (["diabète", "diabétique", "glycémie"], "diabete"),
    (["cholestérol", "dyslipidémie", "hypercholestérol"], "dyslipidemie"),
    (["obèse", "obésité", "surpoids important"], "obesite"),
    (["pilule", "contraceptif oral", "contraceptive", "cop", "oestro-progestatif"], "COP"),
    (["opéré", "opération récente", "chirurgie récente", "post-op", "intervention récente"], "post_op_recent"),
    (["alité", "immobilisé", "immobilisation", "plâtre", "long trajet", "avion long"], "immobilisation_recente"),
    (["cancer", "tumeur", "oncologie", "néoplasie"], "cancer_actif"),
    (["chimiothérapie", "chimio", "immunothérapie", "thérapie ciblée"], "chimio_active"),
    (["voyage long", "long courrier", "retour de voyage"], "voyage_long"),
    (["phlébite", "thrombose", "tvp", "embolie pulmonaire antérieure", "atcd ep"], "atcd_TVP_EP"),
    (["asthme", "asthmatique"], "asthme"),
    (["bpco", "bronchite chronique", "emphysème"], "BPCO"),
    (["anticoagulant", "xarelto", "eliquis", "pradaxa", "coumadine", "warfarine",
      "sintrom", "previscan", "aod", "avk", "héparine"], "anticoagulation_AOD_AVK"),
    (["anti-inflammatoire", "ains", "ibuprofène", "naproxène", "diclofénac",
      "kétoprofène", "celebrex"], "AINS_chronique"),
    (["alcool", "alcoolique", "boit beaucoup"], "alcool_chronique"),
    (["ulcère", "gastrite chronique"], "atcd_ulcere"),
    (["fibrillation auriculaire", "fa ", "arythmie"], "FA_connue"),
    (["immunodéprimé", "immunosuppresseur", "greffe", "vih", "sida"], "immunodepression"),
    (["migraine", "migraineux", "migraineuse"], "migraine_connue"),
    (["antécédent familial cardiaque", "père infarctus", "mère infarctus",
      "famille cardiaque", "mort subite famille"], "atcd_familial_cv_precoce"),
    (["artérite", "aomi", "artériopathie"], "AOMI"),
]


def _extract_risk_factors(norm_text: str, patient_context: dict) -> list[str]:
    """Extrait les risk factors depuis free_text + patient_context."""
    result = set()

    # Depuis patient_context structuré
    ctx_rf = patient_context.get("risk_factors") or []
    if isinstance(ctx_rf, list):
        result.update(ctx_rf)

    ctx_conditions = patient_context.get("conditions") or []
    if isinstance(ctx_conditions, list):
        result.update(ctx_conditions)

    # Depuis free_text (regex/keyword)
    for keywords, tag in _RISK_FACTOR_PATTERNS:
        if any(kw in norm_text for kw in keywords):
            result.add(tag)

    return list(result)


# ============================================================
# 3. Demographics extraction
# ============================================================

def _extract_demographics(patient_context: dict, norm_text: str) -> dict:
    """Extrait age, sex, pregnancy depuis patient_context + free_text."""
    age = patient_context.get("age")
    sex = patient_context.get("sex") or patient_context.get("genre")

    # Sex inference depuis free_text si manquant
    if not sex:
        if any(w in norm_text for w in ["enceinte", "grossesse", "règles", "règle",
                                         "gynéco", "utérus", "ovaires"]):
            sex = "F"
        elif any(w in norm_text for w in ["prostate", "testicule"]):
            sex = "M"

    # Pregnancy
    pregnancy_status = patient_context.get("pregnancy_status")
    pregnancy_trimester = patient_context.get("pregnancy_trimester")

    if not pregnancy_status:
        if any(w in norm_text for w in ["enceinte", "grossesse", "3ème trimestre",
                                         "3e trimestre", "8 mois", "9 mois"]):
            pregnancy_status = "pregnant"
        elif any(w in norm_text for w in ["post-partum", "accouchement récent",
                                           "viens d'accoucher", "accouchée"]):
            pregnancy_status = "post_partum_6w"

    return {
        "age": age,
        "sex": sex,
        "pregnancy_status": pregnancy_status,
        "pregnancy_trimester": pregnancy_trimester,
    }


# ============================================================
# 4. Temporal extraction
# ============================================================

def _extract_temporal(norm_text: str, mapped: dict) -> dict:
    """Extrait temporal features depuis mapper output + free_text."""

    # onset_speed
    onset_speed = None
    brutal_markers = [
        "d'un coup", "brutalement", "soudainement", "soudain",
        "en quelques secondes", "en quelques minutes", "comme un coup",
        "coup de tonnerre", "tout d'un coup", "instantanément",
    ]
    rapid_markers = ["rapidement", "vite", "depuis ce matin", "depuis hier soir"]
    progressive_markers = [
        "progressivement", "petit à petit", "peu à peu",
        "depuis quelques jours", "depuis une semaine",
    ]
    chronic_markers = [
        "depuis plusieurs semaines", "depuis des mois", "depuis longtemps",
        "chronique", "depuis plus d'un mois",
    ]

    if any(m in norm_text for m in brutal_markers):
        onset_speed = "brutal"
    elif any(m in norm_text for m in rapid_markers):
        onset_speed = "rapid"
    elif any(m in norm_text for m in chronic_markers):
        onset_speed = "chronic"
    elif any(m in norm_text for m in progressive_markers):
        onset_speed = "progressive"

    # duration_days depuis mapper
    duration_days = mapped.get("duration_days")

    # evolution
    evolution = None
    if any(w in norm_text for w in ["s'aggrave", "de pire en pire", "empire", "aggravation"]):
        evolution = "worsening"
    elif any(w in norm_text for w in ["s'améliore", "mieux", "ça passe"]):
        evolution = "improving"
    elif any(w in norm_text for w in ["stable", "pareil", "même"]):
        evolution = "stable"

    return {
        "onset_speed": onset_speed,
        "duration_days": duration_days,
        "evolution": evolution,
    }


# ============================================================
# 5. Context flags extraction
# ============================================================

_CONTEXT_FLAG_PATTERNS: list[tuple[list[str], str]] = [
    (["coup de tonnerre", "comme une explosion", "jamais eu aussi mal",
      "pire douleur de ma vie", "thunderclap"], "thunderclap"),
    (["pire de ma vie", "jamais ressenti ça", "douleur maximale",
      "10 sur 10", "10/10"], "pire_de_ma_vie"),
    (["chute", "tombé", "je suis tombé", "je suis tombée",
      "coup à la tête", "choc crânien"], "chute_recente"),
    (["ma migraine habituelle", "comme d'habitude", "typique pour moi",
      "ma céphalée habituelle", "c'est ma migraine"], "cephalee_typique_habitude"),
    (["différente de d'habitude", "pas comme mes migraines habituelles",
      "inhabituelle", "jamais eu ce type"], "cephalee_differente_habitude"),
    (["ventoline ne fait pas effet", "bronchodilatateur inefficace",
      "pompe ne fonctionne pas", "inhalateur inefficace"], "non_response_bronchodilatateur"),
    (["envie d'en finir", "plus envie de vivre", "je veux mourir",
      "me suicider", "suicide", "me tuer", "en finir avec la vie",
      "plus la force de vivre"], "ideation_suicidaire"),
    (["envie d'en finir"], "envie_d_en_finir"),
    (["plus envie de vivre", "plus la force de vivre"], "plus_envie_de_vivre"),
    (["me faire du mal", "m'automutiler", "intention de", "je vais le faire"], "intention_auto_destructive"),
    (["déficit résolu", "ça a disparu", "passé en quelques minutes",
      "transitoire"], "deficit_resolu_spontanement"),
]


def _extract_context_flags(norm_text: str) -> list[str]:
    """Extrait les context flags qualitatifs."""
    result = set()
    for keywords, flag in _CONTEXT_FLAG_PATTERNS:
        if any(kw in norm_text for kw in keywords):
            result.add(flag)
    return list(result)


# ============================================================
# 6. Minimization / Escalation / Self-diagnosis
# ============================================================

_MINIMIZATION_PATTERNS = [
    "mais ça va", "c'est rien", "rien de grave", "pas grand chose",
    "je pense que c'est rien", "probablement rien", "sûrement rien",
    "je veux pas m'inquiéter", "je veux pas exagérer",
]

_ESCALATION_PATTERNS = [
    "pire de ma vie", "jamais eu aussi mal", "insupportable",
    "je peux plus", "atroce", "intolérable", "extrêmement",
    "très intense", "vraiment fort",
]

_SELF_DIAGNOSIS_PATTERNS = [
    "c'est mon stress", "c'est mon anxiété", "c'est ma migraine",
    "c'est mon reflux", "c'est mon asthme", "c'est mon dos",
    "je sais que c'est", "je pense que c'est juste",
]


def _extract_minimization(norm_text: str) -> dict:
    detected = any(p in norm_text for p in _MINIMIZATION_PATTERNS)
    return {"detected": detected}


def _extract_escalation(norm_text: str) -> dict:
    detected = any(p in norm_text for p in _ESCALATION_PATTERNS)
    return {"detected": detected}


def _extract_self_diagnosis(norm_text: str) -> dict:
    markers = [p for p in _SELF_DIAGNOSIS_PATTERNS if p in norm_text]
    return {"markers": markers}


# ============================================================
# 7. Main entry point
# ============================================================

def extract_features(
    free_text: str,
    norm_text: str,
    mapped: dict,
    norm_tokens: dict,
    patient_context: Optional[dict] = None,
) -> dict:
    """
    Stage 3: Feature Extractor — single source of truth pour abstract patterns.

    Args:
        free_text:       texte original patient
        norm_text:       texte normalisé (output normalize_text())
        mapped:          output common_symptom_mapper()
        norm_tokens:     output normalize_to_medical_tokens() → {tokens, ...}
        patient_context: dict {age, sex, risk_factors, ...} ou None

    Returns:
        features dict conforme au contrat abstract patterns ABS-01..ABS-08
    """
    ctx = patient_context or {}
    tokens = norm_tokens.get("tokens", []) if isinstance(norm_tokens, dict) else []

    # Symptoms: bridge tokens → ABS tags + complément depuis free_text direct
    abs_symptoms = _map_tokens_to_abs_symptoms(tokens)

    # Complément direct depuis free_text pour symptômes pas capturés par normalizer
    _DIRECT_SYMPTOM_PATTERNS: list[tuple[list[str], str]] = [
        (["raideur nuque", "nuque raide", "nuque rigide"], "raideur_nuque"),
        (["purpura", "taches violettes", "taches rouges qui disparaissent pas",
          "pétéchies"], "purpura"),
        (["sang dans les crachats", "crachats sanglants", "hémoptysie"], "hemoptysie"),
        (["douleur côté à respirer", "douleur en inspirant",
          "pleurale", "flanc droit respirer"], "douleur_pleuretique"),
        (["confusion", "confus", "désorienté", "désorientée",
          "ne reconnaît plus", "perdu"], "confusion"),
        (["somnolent", "somnolente", "dort tout le temps",
          "difficile à réveiller"], "somnolence"),
        (["comportement bizarre", "comportement inhabituel",
          "plus le même", "changement comportement"], "trouble_comportement_recent"),
        (["ralentissement", "ralenti", "lenteur inhabituelle"], "ralentissement_psychomoteur"),
        (["marbrures", "peau marbrée", "livedo"], "marbrures"),
        (["hypotension", "tension basse", "pression basse"], "hypotension"),
        (["tachycardie", "coeur qui bat vite", "pouls rapide"], "tachycardie"),
        (["polypnée", "respiration rapide", "souffle court"], "polypnee"),
        (["oligurie", "n'urine plus", "urine très peu"], "oligurie"),
        (["fièvre", "de la fièvre", "température", "38", "39", "40"], "fievre"),
        (["frissons", "frisson"], "frissons"),
        (["39", "40", "41", "38.5", "38,5", "fièvre élevée",
          "forte fièvre"], "fievre_38_5_plus"),
        (["hypothermie", "très froid", "35 degrés"], "hypothermie"),
        (["retard de règles", "règles en retard", "pas mes règles",
          "absence de règles"], "retard_regles"),
        (["saignements", "métrorragies", "saignement entre les règles",
          "pertes sanglantes"], "metrorragies"),
        (["douleur en bas du ventre", "bas ventre", "hypogastre",
          "fosse iliaque"], "douleur_abdominale_basse"),
        (["faiblesse d'un côté", "bras gauche faible", "jambe droite faible",
          "hémiplégie", "hémiparésie"], "faiblesse_unilaterale"),
        (["trouble de la parole", "mal à parler", "dysarthrie",
          "aphasie", "bredouille"], "trouble_parole"),
        (["bouche de travers", "visage asymétrique", "sourire asymétrique",
          "paralysie faciale"], "asymetrie_faciale"),
        (["vision trouble", "double vision", "diplopie", "trou dans la vision",
          "scotome", "vision floue brutale"], "trouble_visuel_brutal"),
        (["essoufflé la nuit", "dort assis", "plusieurs oreillers",
          "orthopnée"], "essoufflement_progressif"),
    ]

    for keywords, abs_tag in _DIRECT_SYMPTOM_PATTERNS:
        if any(kw in norm_text for kw in keywords):
            if abs_tag not in abs_symptoms:
                abs_symptoms.append(abs_tag)

    return {
        "symptoms": list(set(abs_symptoms)),
        "temporal": _extract_temporal(norm_text, mapped),
        "demographics": _extract_demographics(ctx, norm_text),
        "risk_factors": _extract_risk_factors(norm_text, ctx),
        "minimization": _extract_minimization(norm_text),
        "escalation": _extract_escalation(norm_text),
        "self_diagnosis": _extract_self_diagnosis(norm_text),
        "context_flags": _extract_context_flags(norm_text),
        # Metadata pour debug
        "_source": {
            "norm_tokens_used": tokens,
            "mapper_category": mapped.get("category"),
        },
    }