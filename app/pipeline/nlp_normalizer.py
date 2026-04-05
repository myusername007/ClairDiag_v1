# ── NLP Normalizer — ClairDiag ───────────────────────────────────────────────
import re
from rapidfuzz import process, fuzz

KNOWN_SYMPTOMS: list[str] = [
    "douleur abdominale", "nausées", "fatigue", "fièvre", "toux",
    "essoufflement", "douleur thoracique", "céphalées", "rhinorrhée",
    "perte d'appétit", "frissons", "mal de gorge", "éternuements",
    "vomissements", "diarrhée", "vertiges", "douleur musculaire",
    "irritation de la gorge", "palpitations", "sueurs nocturnes",
    "perte de connaissance",
]

SYNONYMS: dict[str, str] = {
    # douleur abdominale
    "j'ai mal au ventre":           "douleur abdominale",
    "mal au ventre":                "douleur abdominale",
    "ça me retourne le ventre":     "douleur abdominale",
    "retourne le ventre":           "douleur abdominale",
    "estomac en vrac":              "douleur abdominale",
    "ventre en vrac":               "douleur abdominale",
    "ventre chelou":                "douleur abdominale",
    "mal au bide":                  "douleur abdominale",
    "douleur au ventre":            "douleur abdominale",
    "crampes au ventre":            "douleur abdominale",
    "crampes abdominales":          "douleur abdominale",
    "douleur abdominale":           "douleur abdominale",
    "mal ventre":                   "douleur abdominale",
    "mal o ventre":                 "douleur abdominale",
    "mal o vantr":                  "douleur abdominale",
    "jai mal o ventre":             "douleur abdominale",
    "pas bien ventre":              "douleur abdominale",
    # nausées
    "j'ai envie de vomir":          "nausées",
    "envie de vomir":               "nausées",
    "envie vomir":                  "nausées",
    "envi de vomir":                "nausées",
    "envi vomir":                   "nausées",
    "envie de gerber":              "nausées",
    "jai la gerbe":                 "nausées",
    "la gerbe":                     "nausées",
    "barbouillé":                   "nausées",
    "barbouille":                   "nausées",
    "haut le coeur":                "nausées",
    "mal au coeur":                 "nausées",
    "nausée":                       "nausées",
    "nausé":                        "nausées",
    "envi gerbé":                   "nausées",
    "gerbé":                        "nausées",
    "gerber":                       "nausées",
    "gerbe":                        "nausées",
    # fatigue
    "je suis épuisé":               "fatigue",
    "je suis cassé":                "fatigue",
    "je suis crevé":                "fatigue",
    "je suis ko":                   "fatigue",
    "j'suis ko":                    "fatigue",
    "suis ko":                      "fatigue",
    "ko total":                     "fatigue",
    "k.o.":                         "fatigue",
    "épuisé":                       "fatigue",
    "épuisée":                      "fatigue",
    "fatigué":                      "fatigue",
    "fatiguée":                     "fatigue",
    "crevé":                        "fatigue",
    "crevée":                       "fatigue",
    "cassé":                        "fatigue",
    "cassée":                       "fatigue",
    "faible":                       "fatigue",
    "sans énergie":                 "fatigue",
    "asthénie":                     "fatigue",
    "fatig":                        "fatigue",
    # fièvre
    "j'ai de la fièvre":            "fièvre",
    "j'ai de la temperature":       "fièvre",
    "je fais de la fièvre":         "fièvre",
    "de la température":            "fièvre",
    "température élevée":           "fièvre",
    "chaud froid":                  "fièvre",
    "j'ai chaud froid":             "fièvre",
    "j'ai chaud et froid":          "fièvre",
    "frissons":                     "fièvre",
    "j'ai mal partout et chaud":    "fièvre",
    "fievre":                       "fièvre",
    "fiavr":                        "fièvre",
    # toux
    "je tousse":                    "toux",
    "tousse":                       "toux",
    "toux sèche":                   "toux",
    "toux grasse":                  "toux",
    "toux persistante":             "toux",
    # essoufflement
    "j'arrive plus à respirer":     "essoufflement",
    "j'arrive pas à respirer":      "essoufflement",
    "j'arrive pas bien à respirer": "essoufflement",
    "j'arrive pas respirer":        "essoufflement",
    "arrive pas respirer":          "essoufflement",
    "du mal à respirer":            "essoufflement",
    "du mal a respirer":            "essoufflement",
    "difficulté à respirer":        "essoufflement",
    "difficile de respirer":        "essoufflement",
    "souffle court":                "essoufflement",
    "manque de souffle":            "essoufflement",
    "je souffle mal":               "essoufflement",
    "souffle mal":                  "essoufflement",
    "respire mal":                  "essoufflement",
    "essoufflé":                    "essoufflement",
    "essoufflée":                   "essoufflement",
    "dyspnée":                      "essoufflement",
    # douleur thoracique
    "douleur à la poitrine":        "douleur thoracique",
    "douleur au thorax":            "douleur thoracique",
    "mal dans la poitrine":         "douleur thoracique",
    "mal à la poitrine":            "douleur thoracique",
    "mal poitrine":                 "douleur thoracique",
    "poitrine qui serre":           "douleur thoracique",
    "poitrine serrée":              "douleur thoracique",
    "la poitrine serrée":           "douleur thoracique",
    "oppression thoracique":        "douleur thoracique",
    "douleur poitrine":             "douleur thoracique",
    "mal là poitrine":              "douleur thoracique",
    "genre j'ai mal là poitrine":   "douleur thoracique",
    "j'ai mal là poitrine":         "douleur thoracique",
    # céphalées
    "maux de tête":                 "céphalées",
    "mal à la tête":                "céphalées",
    "mal de tête":                  "céphalées",
    "tête qui fait mal":            "céphalées",
    "migraine":                     "céphalées",
    "tete mal":                     "céphalées",
    # rhinorrhée
    "nez qui coule":                "rhinorrhée",
    "nez coule":                    "rhinorrhée",
    "nez bouché":                   "rhinorrhée",
    "écoulement nasal":             "rhinorrhée",
    # mal de gorge — ТІЛЬКИ з явним словом "mal" перед "gorge"
    "gorge douloureuse":            "mal de gorge",
    "gorge en feu":                 "mal de gorge",
    "mal à la gorge":               "mal de gorge",
    "douleur en avalant":           "mal de gorge",
    "déglutition douloureuse":      "mal de gorge",
    # irritation de la gorge — ТІЛЬКИ з "irite/irrité/gratte"
    "gorge qui gratte":             "irritation de la gorge",
    "gorge irritée":                "irritation de la gorge",
    "irritation gorge":             "irritation de la gorge",
    "gorge irite":                  "irritation de la gorge",
    "gorge irité":                  "irritation de la gorge",
    # palpitations
    "mon coeur s'emballe":          "palpitations",
    "mon coeur bat vite":           "palpitations",
    "mon coeur part en vrille":     "palpitations",
    "coeur qui s'emballe":          "palpitations",
    "coeur qui bat vite":           "palpitations",
    "coeur qui tape fort":          "palpitations",
    "coeur part en vrille":         "palpitations",
    "coeur bat vite":               "palpitations",
    "coeur rapide":                 "palpitations",
    "battements rapides":           "palpitations",
    "palpitations":                 "palpitations",
    # perte de connaissance
    "je suis tombé dans les pommes": "perte de connaissance",
    "tombé dans les pommes":        "perte de connaissance",
    "j'ai perdu connaissance":      "perte de connaissance",
    "perdu connaissance":           "perte de connaissance",
    # douleur musculaire
    "courbatures":                  "douleur musculaire",
    "courbaturé":                   "douleur musculaire",
    "douleurs musculaires":         "douleur musculaire",
    "douleur musculaire":           "douleur musculaire",
    "tout le corps fait mal":       "douleur musculaire",
    "mal partout":                  "douleur musculaire",
    "j'ai mal partout":             "douleur musculaire",
    # perte d'appétit
    "perte d'appétit":              "perte d'appétit",
    "pas d'appétit":                "perte d'appétit",
    "je ne mange plus":             "perte d'appétit",
    "plus faim":                    "perte d'appétit",
    "pa manger":                    "perte d'appétit",
    "pas manger":                   "perte d'appétit",
    # vertiges
    "tête qui tourne":              "vertiges",
    "la tête tourne":               "vertiges",
    "vertiges":                     "vertiges",
    "vertige":                      "vertiges",
    # sueurs
    "sueurs nocturnes":             "sueurs nocturnes",
    "je transpire beaucoup":        "sueurs nocturnes",
    # éternuements
    "éternuements":                 "éternuements",
    "éternuement":                  "éternuements",
}

_SORTED_SYNONYM_KEYS: list[str] = sorted(SYNONYMS.keys(), key=len, reverse=True)

_NEGATION_RULES: list[tuple[str, str]] = [
    ("pas de fièvre",           "fièvre"),
    ("sans fièvre",             "fièvre"),
    ("pas de toux",             "toux"),
    ("sans toux",               "toux"),
    ("sans douleur thoracique", "douleur thoracique"),
    ("pas de nausée",           "nausées"),
    ("sans nausée",             "nausées"),
    ("pas de fièvre",           "frissons"),
]

_FUZZY_STOPWORDS: frozenset = frozenset({
    "mal", "pas", "les", "des", "de", "la", "le", "un", "une", "et", "ou",
    "que", "qui", "je", "tu", "il", "on", "du", "au", "en", "sur", "par",
    "matin", "soir", "nuit", "jour", "peu", "trop", "tout", "bien",
    "crois", "sais", "sens", "suis", "peur", "mais", "sans", "arrive",
    "gorge", "douleur", "vomir", "coule", "la gorge", "de la",
    "genre", "depuis", "trop", "chelou", "bizarre", "tout",
})

_FUZZY_THRESHOLD: int = 80
_FUZZY_MIN_LEN: int = 6
_FUZZY_THRESHOLD_SHORT: int = 88


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s'àâäéèêëïîôùûüç]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _apply_negations(text: str, found: list[str]) -> list[str]:
    to_remove: set[str] = set()
    for pattern, symptom in _NEGATION_RULES:
        if pattern in text:
            to_remove.add(symptom)
    return [s for s in found if s not in to_remove]


def _apply_synonyms(text: str) -> list[str]:
    found: list[str] = []
    for key in _SORTED_SYNONYM_KEYS:
        if key in text:
            canonical = SYNONYMS[key]
            if canonical not in found:
                found.append(canonical)
    return found


def _fuzzy_match(text: str, already_found: set[str]) -> list[str]:
    results: list[str] = []
    words = text.split()
    candidates: list[str] = words[:]
    for i in range(len(words) - 1):
        candidates.append(words[i] + " " + words[i + 1])
    for i in range(len(words) - 2):
        candidates.append(words[i] + " " + words[i + 1] + " " + words[i + 2])

    for cand in candidates:
        if len(cand) < _FUZZY_MIN_LEN or cand in _FUZZY_STOPWORDS:
            continue
        threshold = _FUZZY_THRESHOLD_SHORT if len(cand) <= 7 else _FUZZY_THRESHOLD
        match_result = process.extractOne(cand, KNOWN_SYMPTOMS, scorer=fuzz.partial_ratio)
        if match_result is None:
            continue
        match, score, _ = match_result
        if score >= threshold and match not in already_found and match not in results:
            results.append(match)

    return results


def extract_symptoms(user_input: str) -> list[str]:
    if not user_input or not user_input.strip():
        return []
    text = _normalize_text(user_input)
    synonym_hits = _apply_synonyms(text)
    already = set(synonym_hits)
    fuzzy_hits = _fuzzy_match(text, already)
    combined = synonym_hits + fuzzy_hits
    return _apply_negations(text, combined)