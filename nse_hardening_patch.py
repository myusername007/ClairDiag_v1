# ── NSE PARSER HARDENING PATCH ──────────────────────────────────────────────
# Додати ці алiаси до існуючого ALIASES dict в app/data/symptoms.py або nse.py
# Побутові французькі фрази → канонічні симптоми
#
# ІНСТРУКЦІЯ: знайти ALIASES = { ... } у вашому nse.py / symptoms.py
# і додати ці записи.

COLLOQUIAL_ALIASES_PATCH = {
    # Дихання
    "j'ai du mal à respirer":          "essoufflement",
    "j ai du mal a respirer":          "essoufflement",
    "du mal à respirer":               "essoufflement",
    "mal à respirer":                  "essoufflement",
    "j'arrive pas à respirer":         "essoufflement",
    "je respire mal":                  "essoufflement",
    "respiration difficile":           "essoufflement",
    "souffle court":                   "essoufflement",
    "j'en ai le souffle coupé":        "essoufflement",

    # Brûlure
    "ça me brûle ici":                 "douleur thoracique",
    "ça brûle":                        "brûlures d'estomac",
    "ça me brûle l'estomac":           "brûlures d'estomac",
    "brûlure dans la gorge":           "brûlures d'estomac",
    "brûlure remontante":              "brûlures d'estomac",
    "ça brûle quand j'avale":          "douleur à la déglutition",

    # Cœur / palpitations
    "mon cœur bat vite":               "palpitations",
    "mon coeur bat vite":              "palpitations",
    "mon cœur bat fort":               "palpitations",
    "coeur qui s'emballe":             "palpitations",
    "cœur qui s'emballe":              "palpitations",
    "j'ai le cœur qui bat":            "palpitations",
    "cœur irrégulier":                 "palpitations",
    "mon cœur fait des bonds":         "palpitations",

    # Jambes / œdèmes
    "j'ai les jambes gonflées":        "œdèmes des membres inférieurs",
    "jambes qui gonflent":             "œdèmes des membres inférieurs",
    "chevilles gonflées":              "œdèmes des membres inférieurs",
    "pieds gonflés":                   "œdèmes des membres inférieurs",
    "jambes lourdes gonflées":         "œdèmes des membres inférieurs",

    # Sang dans crachats
    "je crache du sang":               "hémoptysie",
    "crachats avec du sang":           "hémoptysie",
    "sang dans les crachats":          "hémoptysie",
    "je crache du sang rouge":         "hémoptysie",

    # Après manger
    "ça revient après manger":         "brûlures d'estomac",
    "après les repas ça brûle":        "brûlures d'estomac",
    "mal après manger":                "douleur abdominale",
    "douleurs après les repas":        "douleur abdominale",
    "ventre qui fait mal après manger":"douleur abdominale",
    "ballonnements après manger":      "ballonnements",

    # Durée / chronicité
    "j'ai mal depuis des semaines":    "douleur chronique",
    "ça dure depuis des semaines":     "douleur chronique",
    "depuis plusieurs semaines":       "douleur chronique",
    "ça n'arrête pas":                 "douleur chronique",
    "depuis longtemps":                "douleur chronique",

    # Toux / gorge
    "je tousse tout le temps":         "toux",
    "toux qui n'arrête pas":           "toux persistante",
    "j'arrête pas de tousser":         "toux persistante",
    "gorge qui gratte":                "irritation de la gorge",
    "j'ai du mal à avaler":            "douleur à la déglutition",

    # Fièvre
    "j'ai chaud":                      "fièvre",
    "je brûle":                        "fièvre",
    "j'ai de la température":          "fièvre",
    "température élevée":              "fièvre",

    # Fatigue
    "je suis épuisé":                  "fatigue",
    "je suis à bout":                  "fatigue",
    "pas d'énergie":                   "fatigue",
    "sans force":                      "fatigue",
    "complètement vidé":               "fatigue",

    # Tête
    "j'ai mal à la tête":              "céphalées",
    "mal de tête":                     "céphalées",
    "migraine":                        "céphalées",
    "tête qui tourne":                 "vertiges",
    "je tourne de l'oeil":             "vertiges",

    # Douleur thoracique
    "douleur dans la poitrine":        "douleur thoracique",
    "mal à la poitrine":               "douleur thoracique",
    "douleur au milieu de la poitrine":"douleur thoracique",
    "oppression thoracique":           "douleur thoracique",
    "serrement dans la poitrine":      "douleur thoracique",
}