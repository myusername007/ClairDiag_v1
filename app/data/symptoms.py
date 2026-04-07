# ── Données symptômes — source unique ───────────────────────────────────────
# Toute la logique de pondération est ici. Ne pas dupliquer ailleurs.

# Liens : symptôme → diagnostics avec poids
SYMPTOM_DIAGNOSES: dict[str, dict[str, float]] = {
    "fièvre":                {"Grippe": 0.60, "Rhinopharyngite": 0.55, "Bronchite": 0.20, "Pneumonie": 0.35, "Angine": 0.15},
    "toux":                  {"Bronchite": 0.8, "Rhinopharyngite": 0.6, "Grippe": 0.5, "Pneumonie": 0.4, "Allergie": 0.3},
    "rhinorrhée":            {"Rhinopharyngite": 0.9, "Grippe": 0.6, "Allergie": 0.5},
    "céphalées":             {"Grippe": 0.7, "Rhinopharyngite": 0.5, "Hypertension": 0.4},
    "mal de gorge":          {"Rhinopharyngite": 0.8, "Angine": 0.9, "Grippe": 0.5},
    "essoufflement":         {"Pneumonie": 0.8, "Bronchite": 0.45, "Asthme": 0.7, "Angor": 0.4, "Embolie pulmonaire": 0.30, "Insuffisance cardiaque": 0.50},
    "douleur thoracique":    {"Pneumonie": 0.6, "Bronchite": 0.4, "Angor": 0.8, "Embolie pulmonaire": 0.25, "RGO": 0.30},
    "fatigue":               {"Grippe": 0.6, "Rhinopharyngite": 0.5, "Anémie": 0.30, "Angine": 0.15, "Pneumonie": 0.4},
    "perte d'appétit":       {"Grippe": 0.4, "Gastrite": 0.6, "Anémie": 0.4},
    "nausées":               {"Gastrite": 0.8, "Grippe": 0.3},
    "éternuements":          {"Allergie": 0.8, "Rhinopharyngite": 0.4},
    "irritation de la gorge":{"Allergie": 0.7},
    # ── Nouveaux symptômes — v2.2 ──────────────────────────────────────────
    "sifflement":            {"Asthme": 0.85, "Bronchite": 0.30},
    "palpitations":          {"Trouble du rythme": 0.90, "Angor": 0.40, "Hypertension": 0.20},
    "courbatures":           {"Grippe": 0.80, "Rhinopharyngite": 0.30},
    "œdèmes":               {"Insuffisance cardiaque": 1.0, "Angor": 0.20},
    # ── Nouveaux symptômes cardiaques — v2.3 ──────────────────────────────
    "symptomes nocturnes":   {"Insuffisance cardiaque": 0.90},
    "sueurs nocturnes":      {"Insuffisance cardiaque": 0.70, "Lymphome": 0.40},
    "dyspnée progressive":   {"Insuffisance cardiaque": 0.80, "Asthme": 0.30},
    "malaise":               {"Trouble du rythme": 0.60, "Angor": 0.30},
    # ── Symptômes digestifs chroniques — v2.3 ─────────────────────────────
    "ballonnements":         {"SII": 1.0},  # signal pur SII
    "douleur chronique":     {"SII": 1.0},  # signal pur SII
    "diarrhée":              {"SII": 0.70, "Gastrite": 0.30, "Dysbiose": 0.60, "Clostridioides difficile": 0.55, "Infection intestinale": 0.45},
    "bruits intestinaux":    {"SII": 0.65, "Dysbiose": 0.50, "Gastrite": 0.20, "Clostridioides difficile": 0.40, "Infection intestinale": 0.35},
    "Clostridioides difficile": {},
    "Infection intestinale":  {},
    "douleur épigastrique":  {"Gastrite": 0.85, "SII": 0.30},
    "douleur abdominale":    {"SII": 0.80, "Gastrite": 0.35},
    "alternance transit":    {"SII": 0.90},
    "douleurs abdominales chroniques": {"SII": 1.0},
    "reflux acide":          {"RGO": 1.0},  # signal pur RGO
    "régurgitation":         {"RGO": 0.90},
    "remontée acide":        {"RGO": 1.0},
    "brûlure rétrosternale": {"RGO": 1.0},  # signal pur RGO
    "après repas":           {"RGO": 0.80, "Gastrite": 0.15},
    "chronique":             {"SII": 0.80, "Gastrite": 0.05},
    # ── Red flag symptoms (RFE) ────────────────────────────────────────────
    "cyanose":               {"Pneumonie": 0.9, "Angor": 0.8},
    "syncope":               {"Angor": 0.9, "Hypertension": 0.5},
    "hémoptysie":            {"Pneumonie": 0.8, "Bronchite": 0.5},
    "douleur thoracique intense": {"Angor": 0.95},
    "paralysie":             {"Hypertension": 0.7},
    "vertiges":              {"Hypertension": 0.50, "Anémie": 0.40, "Trouble du rythme": 0.30},
    "œdèmes des membres inférieurs": {"Insuffisance cardiaque": 1.0, "Angor": 0.20},
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
    "malaise":                   "malaise",
    "syncope vagale":            "malaise",
    # ── Insuffisance cardiaque aliases ────────────────────────────────────
    "la nuit":                   "symptomes nocturnes",
    "la nuit essoufflement":     "symptomes nocturnes",
    "réveils nocturnes":         "symptomes nocturnes",
    "dyspnée progressive":       "dyspnée progressive",
    # ── RGO aliases ──────────────────────────────────────────────────────
    "reflux":                   "reflux acide",
    "remontées acides":         "reflux acide",
    "brûlures":                 "brûlure rétrosternale",
    "brûlure":                  "brûlure rétrosternale",
    "reflux":                   "reflux acide",
    "remontées acides":         "remontée acide",
    "remontée":                 "remontée acide",
    "régurgitations":          "régurgitation",
    "brûlure poitrine":         "brûlure rétrosternale",
    "après manger":             "après repas",
    "post-prandial":            "après repas",
    # ── SII / digestif aliases ────────────────────────────────────────────
    "douleurs abdominales":     "douleur abdominale",
    "douleurs abdominales chroniques": "douleurs abdominales chroniques",
    "alternance":               "alternance transit",
    "transit irrégulier":      "alternance transit",
    "douleur au ventre":        "douleur abdominale",
    "mal au ventre":            "douleur abdominale",
    "douleurs chroniques":      "douleur chronique",
    "depuis longtemps":         "chronique",
    "depuis des mois":          "chronique",
    "depuis des semaines":      "chronique",
    "ventre gonflé":             "ballonnements",
    "gaz":                       "ballonnements",
    "douleur chronique abdomen": "douleur chronique",
    "brûlures estomac":          "douleur épigastrique",
    "brûlures d'estomac":        "douleur épigastrique",
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
    # ── Parser hardening v2.3 — langage courant ───────────────────────────
    # Respiration
    "j'ai du mal à respirer":          "essoufflement",
    "j ai du mal a respirer":          "essoufflement",
    "du mal à respirer":               "essoufflement",
    "mal à respirer":                  "essoufflement",
    "j'arrive pas à respirer":         "essoufflement",
    "je respire mal":                  "essoufflement",
    "respiration difficile":           "essoufflement",
    "j'en ai le souffle coupé":        "essoufflement",
    # Palpitations
    "mon cœur bat vite":               "palpitations",
    "mon coeur bat vite":              "palpitations",
    "mon cœur bat fort":               "palpitations",
    "coeur qui s'emballe":             "palpitations",
    "cœur qui s'emballe":              "palpitations",
    "j'ai le cœur qui bat":            "palpitations",
    "cœur irrégulier":                 "palpitations",
    "mon cœur fait des bonds":         "palpitations",
    # Œdèmes
    "j'ai les jambes gonflées":        "œdèmes",
    "jambes qui gonflent":             "œdèmes",
    "œdèmes des membres inférieurs":   "œdèmes",
    # Hémoptysie
    "je crache du sang":               "hémoptysie",
    "crachats avec du sang":           "hémoptysie",
    "je crache du sang rouge":         "hémoptysie",
    # Brûlures / RGO
    "ça me brûle ici":                 "brûlure rétrosternale",
    "ça me brûle l'estomac":           "douleur épigastrique",
    "brûlure dans la gorge":           "brûlure rétrosternale",
    "brûlure remontante":              "brûlure rétrosternale",
    "ça brûle":                        "brûlure rétrosternale",
    # Post-prandial
    "ça revient après manger":         "après repas",
    "après les repas ça brûle":        "après repas",
    "mal après manger":                "douleur abdominale",
    "douleurs après les repas":        "douleur abdominale",
    "ventre qui fait mal après manger":"douleur abdominale",
    "ballonnements après manger":      "ballonnements",
    # Douleur chronique
    "j'ai mal depuis des semaines":    "douleur chronique",
    "ça dure depuis des semaines":     "douleur chronique",
    "depuis plusieurs semaines":       "chronique",
    "ça n'arrête pas":                 "douleur chronique",
    # Toux
    "je tousse tout le temps":         "toux",
    "toux qui n'arrête pas":           "toux",
    "j'arrête pas de tousser":         "toux",
    # Fièvre
    "j'ai chaud":                      "fièvre",
    "je brûle":                        "fièvre",
    "j'ai de la température":          "fièvre",
    # Fatigue
    "je suis épuisé":                  "fatigue",
    "je suis à bout":                  "fatigue",
    "pas d'énergie":                   "fatigue",
    "sans force":                      "fatigue",
    "complètement vidé":               "fatigue",
    # Céphalées / vertiges
    "j'ai mal à la tête":              "céphalées",
    "mal de crâne":                    "céphalées",
    "tête qui tourne":                 "vertiges",
    "je tourne de l'œil":              "vertiges",
    # Douleur thoracique
    "douleur dans la poitrine":        "douleur thoracique",
    "douleur au milieu de la poitrine":"douleur thoracique",
    "oppression thoracique":           "douleur thoracique",
    "serrement dans la poitrine":      "douleur thoracique",
    "douleur poitrine":                "douleur thoracique",
    # ── NLP Normalizer bridge — симптоми що normalizer повертає але NSE не знає ──
    # Без цього маппінгу normalizer знаходить симптом але pipeline його відкидає
    "douleur musculaire":              "courbatures",
    "douleurs musculaires":            "courbatures",
    "frissons":                        "fièvre",
    "vomissements":                    "nausées",
    "diarrhée":                        "diarrhée",
    "bruits intestinaux":              "bruits intestinaux",
    "sueurs nocturnes":                "sueurs nocturnes",
    "perte de connaissance":           "syncope",
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
    (frozenset({"diarrhée", "douleur abdominale"}),                           {"SII": 0.20, "Gastrite": 0.15}),
    (frozenset({"diarrhée", "bruits intestinaux"}),                           {"SII": 0.25, "Dysbiose": 0.20}),
    (frozenset({"diarrhée", "douleur abdominale", "bruits intestinaux"}),      {"Clostridioides difficile": 0.25, "Dysbiose": 0.15}),
    (frozenset({"fatigue", "perte d'appétit"}),                              {"Anémie": 0.15}),
    # ── Nouveaux combos — v2.2 ────────────────────────────────────────────
    (frozenset({"sifflement", "essoufflement"}),                             {"Asthme": 0.30}),
    (frozenset({"sifflement", "toux"}),                                      {"Asthme": 0.20}),
    (frozenset({"fièvre", "courbatures", "fatigue"}),                        {"Grippe": 0.25}),
    # Pneumonie strong signal: fièvre + toux + douleur thoracique
    (frozenset({"fièvre", "toux", "douleur thoracique"}),                    {"Pneumonie": 0.20}),
    (frozenset({"œdèmes", "essoufflement"}),                                {"Insuffisance cardiaque": 0.40, "Angor": 0.10}),
    # ── Nouveaux combos — v2.3 ────────────────────────────────────────────
    # Embolie pulmonaire — signal fort brutal
    (frozenset({"essoufflement", "douleur thoracique", "palpitations"}),      {"Embolie pulmonaire": 0.45}),  # Embolie — вимагає 3 симптоми
    # RGO combos
    (frozenset({"reflux acide", "brûlure rétrosternale"}),                      {"RGO": 0.70}),
    (frozenset({"brûlure rétrosternale", "après repas"}),                       {"RGO": 0.60}),
    (frozenset({"douleur thoracique", "après repas"}),                          {"RGO": 0.40, "Angor": -0.15}),
    (frozenset({"œdèmes", "fatigue", "essoufflement"}),                     {"Insuffisance cardiaque": 0.50}),
    (frozenset({"palpitations", "malaise"}),                                 {"Trouble du rythme": 0.40}),
    (frozenset({"palpitations", "fatigue"}),                                 {"Trouble du rythme": 0.20, "Anémie": 0.15}),
    (frozenset({"ballonnements", "douleur chronique"}),                      {"SII": 0.40}),
    (frozenset({"nausées", "douleur épigastrique"}),                         {"Gastrite": 0.30}),
    # SII chronic combos
    (frozenset({"ballonnements", "douleur chronique"}),                      {"SII": 0.70, "Gastrite": -0.20}),
    (frozenset({"ballonnements", "chronique"}),                              {"SII": 0.55, "Gastrite": -0.15}),
    (frozenset({"douleur abdominale", "ballonnements"}),                     {"SII": 0.55, "Gastrite": -0.10}),
    (frozenset({"douleurs abdominales chroniques", "ballonnements"}),           {"SII": 0.80, "Gastrite": -0.30}),
    # RGO triple combo
    (frozenset({"reflux acide", "brûlure rétrosternale", "après repas"}),   {"RGO": 0.80, "Angor": -0.30}),
    # Insuffisance cardiaque nocturne
    (frozenset({"symptomes nocturnes", "essoufflement"}),                      {"Insuffisance cardiaque": 0.45}),
]

# Symptômes incompatibles → pénalités
SYMPTOM_EXCLUSIONS: dict[str, dict[str, float]] = {
    "éternuements":           {"Pneumonie": 0.15, "Bronchite": 0.10, "Angor": 0.20},
    "irritation de la gorge": {"Grippe": 0.15, "Bronchite": 0.15, "Pneumonie": 0.20},
    "nausées":                {"Asthme": 0.15, "Allergie": 0.20, "Embolie pulmonaire": 0.25, "Angor": 0.25},
    "rhinorrhée":             {"Angor": 0.20, "Gastrite": 0.15, "Angine": 0.15},
    "douleur thoracique":     {"Gastrite": 0.15, "Allergie": 0.15},
    "chronique":               {"Gastrite": 0.25, "Grippe": 0.20, "Rhinopharyngite": 0.15},
    "après repas":             {"Angor": 0.25},
    "régurgitation":           {"Angor": 0.20, "Pneumonie": 0.10},
    "remontée acide":          {"Angor": 0.25, "Pneumonie": 0.10},
    "reflux acide":            {"Angor": 0.15, "Pneumonie": 0.10},
}

# Diagnostics nécessitant une attention urgente (utilisé par RME + urgency_level)
URGENT_DIAGNOSES: set[str] = {"Pneumonie", "Angor", "Embolie pulmonaire", "Clostridioides difficile"}

# Article grammatical par diagnostic (pour _build_explanation)
DIAG_ARTICLE: dict[str, str] = {
    "Grippe": "une", "Rhinopharyngite": "une", "Bronchite": "une",
    "Pneumonie": "une", "Angine": "une", "Asthme": "un",
    "Hypertension": "une", "Gastrite": "une", "Anémie": "une",
    "Allergie": "une", "Angor": "un",
    "Insuffisance cardiaque": "une", "Embolie pulmonaire": "une", "RGO": "un",
    "Trouble du rythme": "un", "SII": "un",
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