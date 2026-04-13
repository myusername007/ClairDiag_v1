# ── Données symptômes — source unique ───────────────────────────────────────
# Toute la logique de pondération est ici. Ne pas dupliquer ailleurs.

# Liens : symptôme → diagnostics avec poids
SYMPTOM_DIAGNOSES: dict[str, dict[str, float]] = {
    "fièvre":                {"Grippe": 1.20, "Rhinopharyngite": 1.05, "Bronchite": 0.50, "Angine": 0.40, "Pneumonie": 0.60, "Méningite": 0.50},
    "toux":                  {"Bronchite": 0.88, "Rhinopharyngite": 0.90, "Grippe": 0.85, "Allergie": 0.50, "Pneumonie": 0.70},
    "rhinorrhée":            {"Rhinopharyngite": 1.80, "Grippe": 1.10, "Allergie": 1.00},
    "céphalées":             {"Grippe": 1.30, "Rhinopharyngite": 1.05, "Hypertension": 0.80, "Méningite": 0.50, "AVC": 0.30},
    "mal de gorge":          {"Rhinopharyngite": 1.60, "Angine": 1.80, "Grippe": 1.00},
    "essoufflement":         {"Bronchite": 0.90, "Asthme": 1.26, "Insuffisance cardiaque": 1.10, "Pneumonie": 0.80},
    "douleur thoracique":    {"Pneumonie": 1.00, "Bronchite": 0.70, "Angor": 1.60, "Embolie pulmonaire": 0.35, "RGO": 0.70},
    "fatigue":               {"Grippe": 1.00, "Rhinopharyngite": 0.90, "Anémie": 0.40, "Angine": 0.25},
    "perte d'appétit":       {"Grippe": 0.80, "Gastrite": 0.90},
    "nausées":               {"Gastrite": 1.80, "Grippe": 1.00},
    "éternuements":          {"Allergie": 0.8, "Rhinopharyngite": 0.4},
    "irritation de la gorge":{"Allergie": 0.7},
    # ── Nouveaux symptômes — v2.2 ──────────────────────────────────────────
    "sifflement":            {"Asthme": 0.85, "Bronchite": 0.30},
    "palpitations":          {"Trouble du rythme": 1.50, "Angor": 1.20, "Hypertension": 0.50},
    "courbatures":           {"Grippe": 0.80, "Rhinopharyngite": 0.30},
    "œdèmes":               {"Insuffisance cardiaque": 1.0, "Angor": 0.20},
    # ── Nouveaux symptômes cardiaques — v2.3 ──────────────────────────────
    "symptomes nocturnes":   {"Insuffisance cardiaque": 0.90},
    "sueurs nocturnes":      {"Insuffisance cardiaque": 0.70, "Lymphome": 0.40},
    "dyspnée progressive":   {"Insuffisance cardiaque": 0.80, "Asthme": 0.30},
    # malaise: poids réduits — un malaise isolé n'est pas urgence
    # URGENCE seulement via combo (malaise + douleur thoracique, malaise + syncope)
    "malaise":               {"Trouble du rythme": 0.40, "Angor": 0.20},
    # ── Symptômes digestifs chroniques — v2.3 ─────────────────────────────
    "ballonnements":         {"SII": 3.0},  # signal pur SII
    "douleur chronique":     {"SII": 1.0},  # signal pur SII
    "diarrhée":              {"SII": 4.50, "Gastrite": 0.80, "Dysbiose": 1.20, "Clostridioides difficile": 1.00, "Infection intestinale": 0.80},
    "bruits intestinaux":    {"SII": 0.65, "Dysbiose": 0.50, "Gastrite": 0.20, "Clostridioides difficile": 0.40, "Infection intestinale": 0.35},
    "Clostridioides difficile": {},
    "Infection intestinale":  {},
    "douleur épigastrique":  {"Gastrite": 0.85, "SII": 0.30},
    "douleur abdominale":    {"SII": 5.00, "Gastrite": 1.00},
    "alternance transit":    {"SII": 2.80},
    "douleurs abdominales chroniques": {"SII": 1.0},
    "reflux acide":          {"RGO": 1.0},  # signal pur RGO
    "régurgitation":         {"RGO": 0.90},
    "remontée acide":        {"RGO": 1.0},
    "brûlure rétrosternale": {"RGO": 1.0},  # signal pur RGO
    "après repas":           {"RGO": 1.10, "Gastrite": 0.90},
    "constipation":          {"SII": 2.50, "Dysbiose": 1.20, "Gastrite": 0.50},
    "constipation chronique":{"SII": 3.0},
    "chronique":             {"SII": 0.80, "Gastrite": 0.05},
    # ── Irradiation cardiaque — signal SCA direct ────────────────────────
    "irradiation bras gauche": {"Angor": 2.00, "Infarctus du myocarde": 2.50},
    "irradiation machoire":    {"Angor": 1.80, "Infarctus du myocarde": 2.00},
    "irradiation epaule":      {"Angor": 1.20},
    # ── Red flag symptoms (RFE) ────────────────────────────────────────────
    "cyanose":               {"Pneumonie": 0.9, "Angor": 0.8},
    "syncope":               {"Angor": 0.9, "Hypertension": 0.5},
    "hémoptysie":            {"Pneumonie": 0.8, "Bronchite": 0.5},
    "douleur thoracique intense": {"Angor": 0.95},
    "paralysie":             {"Hypertension": 0.70, "AVC": 1.80},
    "vertiges":              {"Hypertension": 0.50, "Anémie": 0.40, "Trouble du rythme": 0.30, "AVC": 0.40},
    "œdèmes des membres inférieurs": {"Insuffisance cardiaque": 1.0, "Angor": 0.20},
    # ── Nouveaux symptômes — urgences non-cardiaques ───────────────────────
    "raideur nuque":         {"Méningite": 2.50},
    "photophobie":           {"Méningite": 1.80, "Grippe": 0.30},
    "trouble parole":        {"AVC": 2.50, "Hypertension": 0.40},
    "purpura":               {"Méningite": 2.00},
    "hématémèse":            {"Gastrite": 0.80},            # urgence digestive haute — RFE gère l'exit
    "anaphylaxie":           {"Allergie": 2.50},            # réaction allergique sévère
    # ── Œdème / rétention — v2.4 ──────────────────────────────────────────────
    # gonflement SANS gorge/respiration = œdème périphérique (NON urgence)
    # urgence anaphylaxie gérée exclusivement par RFE (gorge + respir combo)
    "gonflement jambes":        {"Insuffisance cardiaque": 0.80, "Angor": 0.10},
    "gonflement visage":        {"Allergie": 0.60},
    "œdème périphérique":       {"Insuffisance cardiaque": 0.70},
    "rétention hydrique":       {"Insuffisance cardiaque": 0.60},
    "prise de poids rapide":    {"Insuffisance cardiaque": 0.50},
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
    "poitrine":                  "douleur thoracique",
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
    "jambes gonflées":           "gonflement jambes",
    "chevilles gonflées":        "gonflement jambes",
    "pieds gonflés":             "gonflement jambes",
    "jambes enflées":            "gonflement jambes",
    "gonflement des jambes":     "gonflement jambes",
    "gonflement des chevilles":  "gonflement jambes",
    "visage gonflé":             "gonflement visage",
    "visage enflé":              "gonflement visage",
    "gonflement du visage":      "gonflement visage",
    "œdème":                     "œdème périphérique",
    "oedeme":                    "œdème périphérique",
    "rétention d'eau":           "rétention hydrique",
    "retention d'eau":           "rétention hydrique",
    "prise de poids rapide":     "prise de poids rapide",
    "j'ai pris du poids":        "prise de poids rapide",
    "grossi rapidement":         "prise de poids rapide",
    "malaise":                   "malaise",
    "syncope vagale":            "malaise",
    "bizarre":                   "malaise",
    "je me sens bizarre":        "malaise",
    "pas bien":                  "malaise",
    "pas très bien":             "malaise",
    "pas top":                   "malaise",
    "je me sens pas bien":       "malaise",
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
    # ── Méningite ─────────────────────────────────────────────────────────────
    "nuque raide":               "raideur nuque",
    "raideur de nuque":          "raideur nuque",
    "cou raide":                 "raideur nuque",
    "raideur du cou":            "raideur nuque",
    "nuque bloquée":             "raideur nuque",
    "photophobie":               "photophobie",
    "sensible à la lumière":     "photophobie",
    "lumière douloureuse":       "photophobie",
    "pétéchies":                 "purpura",
    "pétéchie":                  "purpura",
    "taches rouges peau":        "purpura",
    # ── AVC ───────────────────────────────────────────────────────────────────
    "difficultés à parler":      "trouble parole",
    "du mal à parler":           "trouble parole",
    "je parle mal":              "trouble parole",
    "parole difficile":          "trouble parole",
    "je n'arrive plus à parler": "trouble parole",
    "mots qui viennent pas":     "trouble parole",
    "je bafouille":              "trouble parole",
    "dysarthrie":                "trouble parole",
    "aphasie":                   "trouble parole",
    # ── Anaphylaxie / œdème de Quincke ────────────────────────────────────────
    "gonflement gorge":          "anaphylaxie",
    "gorge qui gonfle":          "anaphylaxie",
    "gorge enflée":              "anaphylaxie",
    "réaction allergique":       "anaphylaxie",
    "choc anaphylactique":       "anaphylaxie",
    # ── Hématémèse ────────────────────────────────────────────────────────────
    "vomissement de sang":       "hématémèse",
    "vomit du sang":             "hématémèse",
    "je vomis du sang":          "hématémèse",
    "sang dans les vomissements":"hématémèse",
    # ── Œdème jambe (singulier manquant) ──────────────────────────────────────
    "jambe gonflée":             "œdèmes",
    "jambe qui gonfle":          "œdèmes",
    "une jambe gonflée":         "œdèmes",
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
    # Semantic fallback bridge — маппінг виходів _normalize_segment → SYMPTOM_DIAGNOSES
    "douleur abdominale post-prandiale": "après repas",
    "douleur nocturne":                "symptomes nocturnes",
    "douleur matinale":                "douleur abdominale",
    "douleur dorsale":                 "douleur abdominale",
    "douleur à l'effort":              "douleur thoracique",
    "céphalée":                        "céphalées",
    "mal au ventre":                   "douleur abdominale",
    "mal ventre":                      "douleur abdominale",
    "ventre":                          "douleur abdominale",
    "gargouille":                      "bruits intestinaux",
    "gargouillement":                  "bruits intestinaux",
    "ça gargouille":                   "bruits intestinaux",
    "bizarre":                         "malaise",
    "pas bien":                        "malaise",
    "pas très bien":                   "malaise",
    "je me sens mal":                  "malaise",
    "depuis antibiotiques":            "diarrhée",
    "post antibiotiques":              "diarrhée",
    "après antibiotiques":             "diarrhée",
    "antibiotiques":                   "diarrhée",
    "côté droit":                      "douleur abdominale",
    "côté gauche":                     "douleur abdominale",
    "cote droit":                      "douleur abdominale",
    "cote gauche":                     "douleur abdominale",
    "allongée":                        "symptomes nocturnes",
    "allongé":                         "symptomes nocturnes",
    "verre d'eau":                     "douleur abdominale",
    "petit repas":                     "après repas",
    "chaque repas":                    "après repas",
    "après chaque":                    "après repas",
    "douleurs musculaires":            "courbatures",
    "frissons":                        "fièvre",
    "vomissements":                    "nausées",
    "diarrhée":                        "diarrhée",
    "constipation":                    "constipation",
    "constipé":                        "constipation",
    "je suis constipé":               "constipation",
    "pas de selles":                   "constipation",
    "selles difficiles":               "constipation",
    "constipation chronique":          "constipation chronique",
    "bruits intestinaux":              "bruits intestinaux",
    "sueurs nocturnes":                "sueurs nocturnes",
    "perte de connaissance":           "syncope",
}

# Bonus de combinaisons de symptômes
COMBO_BONUSES: list[tuple[frozenset[str], dict[str, float]]] = [
    (frozenset({"fièvre", "toux", "essoufflement"}),                        {"Pneumonie": 0.65, "Bronchite": -0.20}),
    (frozenset({"toux", "essoufflement"}),                                   {"Bronchite": 0.15, "Asthme": 0.15}),
    (frozenset({"rhinorrhée", "éternuements", "irritation de la gorge"}),    {"Allergie": 0.35}),
    (frozenset({"mal de gorge", "fièvre"}),                                  {"Angine": 0.20}),
    (frozenset({"douleur thoracique", "essoufflement"}),                     {"Angor": 0.34, "Pneumonie": 0.15}),
    (frozenset({"fièvre", "céphalées", "fatigue"}),                          {"Grippe": 0.20}),
    (frozenset({"nausées", "perte d'appétit"}),                              {"Gastrite": 0.20}),
    (frozenset({"diarrhée", "douleur abdominale"}),                           {"SII": 0.20, "Gastrite": 0.15}),
    (frozenset({"constipation", "douleur abdominale"}),                       {"SII": 0.45, "Gastrite": 0.20}),
    (frozenset({"constipation", "après repas"}),                              {"SII": 0.30, "Gastrite": 0.35}),
    (frozenset({"constipation", "douleur abdominale", "après repas"}),        {"SII": 0.55, "Gastrite": 0.25}),
    (frozenset({"diarrhée", "bruits intestinaux"}),                           {"SII": 0.25, "Dysbiose": 0.20}),
    (frozenset({"diarrhée", "douleur abdominale", "bruits intestinaux"}),      {"Clostridioides difficile": 0.25, "Dysbiose": 0.15}),
    (frozenset({"fatigue", "perte d'appétit"}),                              {"Anémie": 0.15}),
    # ── Nouveaux combos — v2.2 ────────────────────────────────────────────
    (frozenset({"sifflement", "essoufflement"}),                             {"Asthme": 0.30, "Bronchite": 0.10}),
    (frozenset({"sifflement", "toux"}),                                      {"Asthme": 0.20, "Bronchite": 0.05}),
    (frozenset({"fièvre", "courbatures", "fatigue"}),                        {"Grippe": 0.25}),
    # Pneumonie strong signal: fièvre + toux + douleur thoracique
    (frozenset({"fièvre", "toux", "douleur thoracique"}),                    {"Pneumonie": 0.20}),
    (frozenset({"œdèmes", "essoufflement"}),                                {"Insuffisance cardiaque": 0.40, "Angor": 0.10}),
    # ── Nouveaux combos — v2.3 ────────────────────────────────────────────
    # Triage cardiaque — triade douleur thoracique + essoufflement + palpitations
    # Boost EP/arythmie/Angor, pénalise Asthme/Bronchite (non-cardiaque)
    (frozenset({"essoufflement", "douleur thoracique", "palpitations"}), {
        "Embolie pulmonaire": 0.45, "Trouble du rythme": 0.35, "Angor": 0.30,
        "Asthme": -0.40, "Bronchite": -0.30,
    }),
    # Embolie boost supplémentaire onset brutal — dépasse Angor
    (frozenset({"essoufflement", "douleur thoracique"}), {
        "Embolie pulmonaire": 0.20, "Angor": 0.15,
    }),
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
    # Insuffisance cardiaque nocturne (essoufflement requis — seule "nuit" ne suffit pas)
    (frozenset({"symptomes nocturnes", "essoufflement"}),                      {"Insuffisance cardiaque": 0.45}),
    # ── SCA / Infarctus — irradiation combos ─────────────────────────────────
    (frozenset({"douleur thoracique", "irradiation bras gauche"}),             {"Angor": 0.80, "Infarctus du myocarde": 0.60}),
    (frozenset({"douleur thoracique", "irradiation machoire"}),                {"Angor": 0.70, "Infarctus du myocarde": 0.50}),
    (frozenset({"douleur thoracique", "irradiation bras gauche", "essoufflement"}), {"Infarctus du myocarde": 0.80, "Angor": 0.40}),
    # ── Digestif nocturne — inhibe cardiac si pas d'essoufflement ────────────
    # symptomes nocturnes + douleur abdominale SANS essoufflement → pas de boost IC
    (frozenset({"symptomes nocturnes", "douleur abdominale"}),                 {"Insuffisance cardiaque": -0.60, "SII": 0.20, "Gastrite": 0.20}),
    # ── Méningite — triade classique ─────────────────────────────────────────
    (frozenset({"raideur nuque", "fièvre"}),                                   {"Méningite": 0.60}),
    (frozenset({"raideur nuque", "photophobie"}),                              {"Méningite": 0.40}),
    (frozenset({"raideur nuque", "fièvre", "céphalées"}),                      {"Méningite": 0.80}),
    # ── AVC — déficits neurologiques multiples ────────────────────────────────
    (frozenset({"trouble parole", "paralysie"}),                               {"AVC": 0.50}),
    (frozenset({"trouble parole", "vertiges"}),                                {"AVC": 0.30}),
]

# Symptômes incompatibles → pénalités
SYMPTOM_EXCLUSIONS: dict[str, dict[str, float]] = {
    "éternuements":           {"Pneumonie": 0.15, "Bronchite": 0.10, "Angor": 0.20},
    "irritation de la gorge": {"Grippe": 0.15, "Bronchite": 0.15, "Pneumonie": 0.20},
    "nausées":                {"Asthme": 0.15, "Allergie": 0.20, "Embolie pulmonaire": 0.25, "Angor": 0.25},
    "rhinorrhée":             {"Angor": 0.20, "Gastrite": 0.15, "Angine": 0.15},
    "toux":                   {"Angine": 0.20},
    "fièvre":                 {"Asthme": 0.25},
    # fatigue sans mal de gorge → Angine peu probable
    "fatigue":                {"Angine": 0.30},
    "douleur thoracique":     {"Gastrite": 0.15, "Allergie": 0.15},
    "chronique":               {"Gastrite": 0.25, "Grippe": 0.20, "Rhinopharyngite": 0.15},
    "après repas":             {"Angor": 0.25},
    "régurgitation":           {"Angor": 0.20, "Pneumonie": 0.10},
    "remontée acide":          {"Angor": 0.25, "Pneumonie": 0.10},
    "reflux acide":            {"Angor": 0.15, "Pneumonie": 0.10},
    "douleur abdominale":      {"Insuffisance cardiaque": 0.20, "Angor": 0.15},
    "symptomes nocturnes":     {},  # neutral — cardiac boost only via combo avec essoufflement
}

# Diagnostics nécessitant une attention urgente (utilisé par RME + urgency_level)
URGENT_DIAGNOSES: set[str] = {"Pneumonie", "Angor", "Embolie pulmonaire", "Clostridioides difficile", "Infarctus du myocarde", "Méningite", "AVC", "Anaphylaxie"}

# Article grammatical par diagnostic (pour _build_explanation)
DIAG_ARTICLE: dict[str, str] = {
    "Grippe": "une", "Rhinopharyngite": "une", "Bronchite": "une",
    "Pneumonie": "une", "Angine": "une", "Asthme": "un",
    "Hypertension": "une", "Gastrite": "une", "Anémie": "une",
    "Allergie": "une", "Angor": "un",
    "Insuffisance cardiaque": "une", "Embolie pulmonaire": "une", "RGO": "un",
    "Trouble du rythme": "un", "SII": "un", "Infarctus du myocarde": "un",
    "Méningite": "une", "AVC": "un", "Anaphylaxie": "une",
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

# ── Classification des symptômes — v2.4 ───────────────────────────────────────
# Utilisé par TriageGate pour valider les décisions d'urgence

SYMPTOM_CATEGORIES: dict[str, str] = {
    # RED FLAGS — dangereux isolément ou en combo
    "douleur thoracique":         "RED_FLAG",
    "douleur thoracique intense": "RED_FLAG",
    "irradiation bras gauche":    "RED_FLAG",
    "irradiation machoire":       "RED_FLAG",
    "détresse respiratoire":      "RED_FLAG",
    "syncope":                    "RED_FLAG",
    "perte de connaissance":      "RED_FLAG",
    "hématémèse":                 "RED_FLAG",
    "paralysie":                  "RED_FLAG",
    "trouble parole":             "RED_FLAG",
    "cyanose":                    "RED_FLAG",
    "anaphylaxie":                "RED_FLAG",
    "raideur nuque":              "RED_FLAG",
    "purpura":                    "RED_FLAG",
    # NON RED FLAGS — symptômes ordinaires
    "fatigue":                    "NON_RED_FLAG",
    "gonflement jambes":          "NON_RED_FLAG",
    "gonflement visage":          "NON_RED_FLAG",
    "œdème périphérique":         "NON_RED_FLAG",
    "rétention hydrique":         "NON_RED_FLAG",
    "prise de poids rapide":      "NON_RED_FLAG",
    "ballonnements":              "NON_RED_FLAG",
    "diarrhée":                   "NON_RED_FLAG",
    "nausées":                    "NON_RED_FLAG",
    "malaise":                    "NON_RED_FLAG",
    "vertiges":                   "NON_RED_FLAG",
    "palpitations":               "NON_RED_FLAG",
    "douleur abdominale":         "NON_RED_FLAG",
    # CONTEXT — модификаторы
    "après repas":                "CONTEXT",
    "symptomes nocturnes":        "CONTEXT",
    "chronique":                  "CONTEXT",
    "douleur chronique":          "CONTEXT",
}

# ── FORBIDDEN OUTPUTS — règles de filtrage par profil clinique ────────────────
# Format : profil → diagnostics interdits dans la réponse finale
# Utilisé par TriageGate._check_forbidden_outputs()

FORBIDDEN_OUTPUTS: dict[str, list[str]] = {
    # Input vague (1 symptôme non-spécifique) → interdire tout diagnostic grave
    "vague_input": [
        "Infarctus du myocarde", "Pneumonie", "Embolie pulmonaire",
        "Méningite", "AVC",
    ],
    # Profil digestif simple → interdire pathologies cardio-pulmonaires graves
    "digestif_simple": [
        "Embolie pulmonaire", "Infarctus du myocarde",
    ],
    # Fatigue seule → interdire toute urgence
    "fatigue_seule": [
        "Infarctus du myocarde", "Pneumonie", "Embolie pulmonaire",
        "Méningite", "AVC", "Angor",
    ],
}