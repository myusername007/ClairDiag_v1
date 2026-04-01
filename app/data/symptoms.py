# ── Données symptômes — source unique ───────────────────────────────────────
# Toute la logique de pondération est ici. Ne pas dupliquer ailleurs.

# Liens : symptôme → diagnostics avec poids
SYMPTOM_DIAGNOSES: dict[str, dict[str, float]] = {
    "fièvre":                {"Grippe": 0.8, "Rhinopharyngite": 0.7, "Bronchite": 0.20, "Pneumonie": 0.3, "Angine": 0.15},
    "toux":                  {"Bronchite": 0.8, "Rhinopharyngite": 0.6, "Grippe": 0.5, "Pneumonie": 0.4, "Allergie": 0.3},
    "rhinorrhée":            {"Rhinopharyngite": 0.9, "Grippe": 0.6, "Allergie": 0.5},
    "céphalées":             {"Grippe": 0.7, "Rhinopharyngite": 0.5, "Hypertension": 0.4},
    "mal de gorge":          {"Rhinopharyngite": 0.8, "Angine": 0.9, "Grippe": 0.5},
    "essoufflement":         {"Pneumonie": 0.8, "Bronchite": 0.45, "Asthme": 0.7, "Angor": 0.4},
    "douleur thoracique":    {"Pneumonie": 0.6, "Bronchite": 0.4, "Angor": 0.8},
    "fatigue":               {"Grippe": 0.6, "Rhinopharyngite": 0.5, "Anémie": 0.30, "Angine": 0.15, "Pneumonie": 0.4},
    "perte d'appétit":       {"Grippe": 0.4, "Gastrite": 0.6, "Anémie": 0.4},
    "nausées":               {"Gastrite": 0.8, "Grippe": 0.3},
    "éternuements":          {"Allergie": 0.8, "Rhinopharyngite": 0.4},
    "irritation de la gorge":{"Allergie": 0.7},
    # ── Nouveaux symptômes — v2.2 ──────────────────────────────────────────
    "sifflement":            {"Asthme": 0.85, "Bronchite": 0.30},
    "palpitations":          {"Angor": 0.70, "Hypertension": 0.40},
    "courbatures":           {"Grippe": 0.80, "Rhinopharyngite": 0.30},
    "œdèmes":               {"Angor": 0.50},
    # ── Red flag symptoms (RFE) ────────────────────────────────────────────
    "cyanose":               {"Pneumonie": 0.9, "Angor": 0.8},
    "syncope":               {"Angor": 0.9, "Hypertension": 0.5},
    "hémoptysie":            {"Pneumonie": 0.8, "Bronchite": 0.5},
    "douleur thoracique intense": {"Angor": 0.95},
    "paralysie":             {"Hypertension": 0.7},
}

# Alias de saisie libre → symptôme canonique
ALIASES: dict[str, str] = {
    "température":               "fièvre",
    "température élevée":        "fièvre",
    "de la fièvre":              "fièvre",
    "j'ai de la fièvre":         "fièvre",
    "toux sèche":                "toux",
    "toux grasse":               "toux",
    "je tousse":                 "toux",
    "nez qui coule":             "rhinorrhée",
    "écoulement nasal":          "rhinorrhée",
    "nez bouché":                "rhinorrhée",
    "maux de tête":              "céphalées",
    "mal à la tête":             "céphalées",
    "migraine":                  "céphalées",
    "gorge":                     "mal de gorge",
    "douleur en avalant":        "mal de gorge",
    "déglutition douloureuse":   "mal de gorge",
    "essoufflé":                 "essoufflement",
    "souffle court":             "essoufflement",
    "manque de souffle":         "essoufflement",
    "gêne respiratoire":         "essoufflement",
    "douleur au thorax":         "douleur thoracique",
    "douleur à la poitrine":     "douleur thoracique",
    "mal à la poitrine":         "douleur thoracique",
    "fatigué":                   "fatigue",
    "épuisement":                "fatigue",
    "asthénie":                  "fatigue",
    "pas d'appétit":             "perte d'appétit",
    "anorexie":                  "perte d'appétit",
    "nausée":                    "nausées",
    "envie de vomir":            "nausées",
    "éternuement":               "éternuements",
    "gorge qui gratte":          "irritation de la gorge",
    "irritation gorge":          "irritation de la gorge",
    # ── Nouveaux alias — v2.2 ─────────────────────────────────────────────
    "sifflements":               "sifflement",
    "respiration sifflante":     "sifflement",
    "palpitation":               "palpitations",
    "cœur qui bat vite":         "palpitations",
    "battements rapides":        "palpitations",
    "courbature":                "courbatures",
    "douleurs musculaires":      "courbatures",
    "jambes gonflées":           "œdèmes",
    "chevilles gonflées":        "œdèmes",
    "pieds gonflés":             "œdèmes",
    "malaise":                   "fatigue",
    # ── Red flags ─────────────────────────────────────────────────────────
    "bleu":                      "cyanose",
    "lèvres bleues":             "cyanose",
    "perte de connaissance":     "syncope",
    "évanouissement":            "syncope",
    "sang dans les crachats":    "hémoptysie",
    "crachats sanglants":        "hémoptysie",
    "crachat de sang":           "hémoptysie",
    "douleur intense poitrine":  "douleur thoracique intense",
    "paralysé":                  "paralysie",
    "bras paralysé":             "paralysie",
}

# Bonus de combinaisons de symptômes
COMBO_BONUSES: list[tuple[frozenset[str], dict[str, float]]] = [
    (frozenset({"fièvre", "toux", "essoufflement"}),                        {"Pneumonie": 0.32}),
    (frozenset({"toux", "essoufflement"}),                                   {"Bronchite": 0.15, "Asthme": 0.15}),
    (frozenset({"rhinorrhée", "éternuements", "irritation de la gorge"}),    {"Allergie": 0.35}),
    (frozenset({"mal de gorge", "fièvre"}),                                  {"Angine": 0.20}),
    (frozenset({"douleur thoracique", "essoufflement"}),                     {"Angor": 0.25, "Pneumonie": 0.15}),
    (frozenset({"fièvre", "céphalées", "fatigue"}),                          {"Grippe": 0.20}),
    (frozenset({"nausées", "perte d'appétit"}),                              {"Gastrite": 0.20}),
    (frozenset({"fatigue", "perte d'appétit"}),                              {"Anémie": 0.15}),
    # ── Nouveaux combos — v2.2 ────────────────────────────────────────────
    (frozenset({"sifflement", "essoufflement"}),                             {"Asthme": 0.30}),
    (frozenset({"sifflement", "toux"}),                                      {"Asthme": 0.20}),
    (frozenset({"fièvre", "courbatures", "fatigue"}),                        {"Grippe": 0.25}),
    # Pneumonie strong signal: fièvre + toux + douleur thoracique
    (frozenset({"fièvre", "toux", "douleur thoracique"}),                    {"Pneumonie": 0.20}),
    (frozenset({"œdèmes", "essoufflement"}),                                {"Angor": 0.20}),
]

# Symptômes incompatibles → pénalités
SYMPTOM_EXCLUSIONS: dict[str, dict[str, float]] = {
    "éternuements":           {"Pneumonie": 0.15, "Bronchite": 0.10, "Angor": 0.20},
    "irritation de la gorge": {"Grippe": 0.15, "Bronchite": 0.15, "Pneumonie": 0.20},
    "nausées":                {"Asthme": 0.15, "Allergie": 0.10},
    "rhinorrhée":             {"Angor": 0.20, "Gastrite": 0.15, "Angine": 0.15},
    "douleur thoracique":     {"Gastrite": 0.15, "Allergie": 0.15},
}

# Diagnostics nécessitant une attention urgente (utilisé par RME + urgency_level)
URGENT_DIAGNOSES: set[str] = {"Pneumonie", "Angor"}

# Article grammatical par diagnostic (pour _build_explanation)
DIAG_ARTICLE: dict[str, str] = {
    "Grippe": "une", "Rhinopharyngite": "une", "Bronchite": "une",
    "Pneumonie": "une", "Angine": "une", "Asthme": "un",
    "Hypertension": "une", "Gastrite": "une", "Anémie": "une",
    "Allergie": "une", "Angor": "un",
}

# Scénarios de démonstration
DEMO_SCENARIOS: dict[str, list[str]] = {
    "Rhume":      ["rhinorrhée", "mal de gorge", "fatigue"],
    "Grippe":     ["fièvre", "toux", "céphalées", "fatigue"],
    "Bronchite":  ["toux", "essoufflement", "douleur thoracique"],
    "Angine":     ["mal de gorge", "fièvre", "fatigue"],
    "Pneumonie":  ["fièvre", "toux", "essoufflement", "douleur thoracique"],
    "Allergie":   ["rhinorrhée", "éternuements", "irritation de la gorge"],
}