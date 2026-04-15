# ── NLP Normalizer — ClairDiag ───────────────────────────────────────────────
import re
from rapidfuzz import process, fuzz

KNOWN_SYMPTOMS: list[str] = [
    "douleur abdominale", "nausées", "fatigue", "fièvre", "toux",
    "essoufflement", "douleur thoracique", "céphalées", "rhinorrhée",
    "perte d'appétit", "frissons", "mal de gorge", "éternuements",
    "vomissements", "diarrhée", "vertiges", "douleur musculaire",
    "irritation de la gorge", "palpitations", "sueurs nocturnes",
    "perte de connaissance", "symptomes nocturnes",
    "ballonnements", "bruits intestinaux", "douleur épigastrique", "après repas",
    "irradiation bras gauche", "irradiation machoire", "irradiation epaule",
    # v2.4 — œdème / rétention
    "gonflement jambes", "gonflement visage", "œdème périphérique",
    "rétention hydrique", "prise de poids rapide",
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
    "fièvre 39":                    "fièvre élevée",
    "fièvre à 39":                  "fièvre élevée",
    "39 de fièvre":                 "fièvre élevée",
    "fièvre 38":                    "fièvre",
    "fièvre 38.5":                  "fièvre",
    "fièvre 38 5":                  "fièvre",
    "fièvre à 38":                  "fièvre",
    "fièvre à 38.5":                "fièvre",
    "38 de fièvre":                 "fièvre",
    "38.5 de fièvre":               "fièvre",
    "38 5 de fièvre":               "fièvre",
    "fièvre depuis":                "fièvre",
    "forte fièvre":                 "fièvre élevée",
    "grosse fièvre":                "fièvre élevée",
    "température élevée":           "fièvre",
    "chaud froid":                  "fièvre",
    "j'ai chaud froid":             "fièvre",
    "j'ai chaud et froid":          "fièvre",
    "frissons":                     "frissons",
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
    # Douleur légère / vague → symptôme distinct, pas douleur thoracique typique
    "douleur poitrine legere":      "douleur poitrine légère",
    "douleur poitrine légère":      "douleur poitrine légère",
    "douleur légère poitrine":      "douleur poitrine légère",
    "légère douleur poitrine":      "douleur poitrine légère",
    "vague douleur poitrine":       "douleur vague poitrine",
    "douleur vague poitrine":       "douleur vague poitrine",
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
    # mal de gorge
    "gorge douloureuse":            "mal de gorge",
    "gorge en feu":                 "mal de gorge",
    "mal à la gorge":               "mal de gorge",
    "douleur en avalant":           "mal de gorge",
    "déglutition douloureuse":      "mal de gorge",
    # irritation de la gorge
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
    # sueurs nocturnes — ТІЛЬКИ з явним sweating словом
    "sueurs nocturnes":             "sueurs nocturnes",
    "sueurs la nuit":               "sueurs nocturnes",
    "je transpire":                 "sueurs nocturnes",
    "transpiration excessive":      "sueurs nocturnes",
    "transpiration nocturne":       "sueurs nocturnes",
    "transpiration la nuit":        "sueurs nocturnes",
    "je transpire beaucoup":        "sueurs nocturnes",
    "je transpire la nuit":         "sueurs nocturnes",
    "transpire la nuit":            "sueurs nocturnes",
    "sueur nocturne":               "sueurs nocturnes",
    # symptomes nocturnes — douleur/aggravation la nuit, БЕЗ sweating
    "douleur la nuit":              "symptomes nocturnes",
    "douleur nocturne":             "symptomes nocturnes",
    "mal la nuit":                  "symptomes nocturnes",
    "symptômes la nuit":            "symptomes nocturnes",
    "symptomes la nuit":            "symptomes nocturnes",
    "aggravation nocturne":         "symptomes nocturnes",
    "ça empire la nuit":            "symptomes nocturnes",
    "empire la nuit":               "symptomes nocturnes",
    "pire la nuit":                 "symptomes nocturnes",
    "réveillé par la douleur":      "symptomes nocturnes",
    "reveille par la douleur":      "symptomes nocturnes",
    # ── Nouveaux alias digestifs — patch final ───────────────────────────
    "ventre gonflé":                "ballonnements",
    "ventre qui gonfle":            "ballonnements",
    "ballonnement":                 "ballonnements",
    "ventre qui gargouille":        "bruits intestinaux",
    "ventre qui fait du bruit":     "bruits intestinaux",
    "ça gargouille":                "bruits intestinaux",
    "brûlure estomac":              "douleur épigastrique",
    "brûlures estomac":             "douleur épigastrique",
    "brûlure à l estomac":          "douleur épigastrique",
    "diarrhée":                     "diarrhée",
    "diarrhee":                     "diarrhée",
    "diarrhées":                    "diarrhée",
    "selles liquides":              "diarrhée",
    "transit accéléré":             "diarrhée",
    "selles molles":                "diarrhée",
    "selle molle":                  "diarrhée",
    "va souvent au wc":             "diarrhée",
    "je vais souvent aux wc":       "diarrhée",
    "souvent aux toilettes":        "diarrhée",
    "après manger":                 "après repas",
    "apres manger":                 "après repas",
    "après avoir mangé":            "après repas",
    "apres avoir mange":            "après repas",
    "ça gargouille la nuit":        "symptomes nocturnes",
    "douleur après repas":          "douleur abdominale",
    "douleur post-prandiale":       "douleur abdominale",
    # éternuements
    "éternuements":                 "éternuements",
    "éternuement":                  "éternuements",
    # Anglais (patients bilingues)
    "stomach pain":                 "douleur abdominale",
    "stomach ache":                 "douleur abdominale",
    "belly pain":                   "douleur abdominale",
    "abdominal pain":               "douleur abdominale",
    "bloating":                     "ballonnements",
    "bloated":                      "ballonnements",
    "after eating":                 "après repas",
    "after meals":                  "après repas",
    "chest pain":                   "douleur thoracique",
    "shortness of breath":          "essoufflement",
    "fatigue":                      "fatigue",
    "fever":                        "fièvre",
    "cough":                        "toux",
    "nausea":                       "nausées",
    "diarrhea":                     "diarrhée",
    "diarrhoea":                    "diarrhée",
    "constipation":                 "constipation",
    "headache":                     "céphalées",
    "sore throat":                  "mal de gorge",
    # ── Irradiation cardiaque — SCA signal ───────────────────────────────
    "irradie dans le bras":         "irradiation bras gauche",
    "irradie bras gauche":          "irradiation bras gauche",
    "irradiation bras gauche":      "irradiation bras gauche",
    "irradiation dans le bras":     "irradiation bras gauche",
    "vers le bras gauche":          "irradiation bras gauche",
    "dans le bras gauche":          "irradiation bras gauche",
    "bras gauche":                  "irradiation bras gauche",
    "irradie dans la machoire":     "irradiation machoire",
    "irradiation machoire":         "irradiation machoire",
    "vers la machoire":             "irradiation machoire",
    "mâchoire":                     "irradiation machoire",
    "irradie epaule":               "irradiation epaule",
    "vers l epaule":                "irradiation epaule",
    "vomi":                         "nausées",
    "j'ai vomi":                    "nausées",
    "vomis":                        "nausées",
    "mal o ventr":                  "douleur abdominale",
    "mal au ventr":                 "douleur abdominale",
    # Répétitions (mal mal mal → mal au ventre)
    "mal mal":                      "douleur abdominale",
    "mal mal mal":                  "douleur abdominale",
    # Durée longue
    "depuis longtemps":             "chronique",
    "depuis très longtemps":        "chronique",
    "ça dure depuis longtemps":     "chronique",
    # ── Œdème / rétention / gonflement — v2.4 ────────────────────────────────
    # gonflement → par défaut NON urgence (œdème périphérique)
    # urgence anaphylaxie gérée par RFE (gorge + respir)
    "jambes gonflées":              "gonflement jambes",
    "chevilles gonflées":           "gonflement jambes",
    "pieds gonflés":                "gonflement jambes",
    "jambes enflées":               "gonflement jambes",
    "gonflement des jambes":        "gonflement jambes",
    "gonflement des chevilles":     "gonflement jambes",
    "jambe gonflée":                "gonflement jambes",
    "cheville gonflée":             "gonflement jambes",
    # gonflement seul → œdème périphérique par défaut (pas anaphylaxie)
    "gonflement":                   "gonflement jambes",
    "je gonfle":                    "gonflement jambes",
    "je suis gonflé":               "gonflement jambes",
    "enflé":                        "gonflement jambes",
    "enflée":                       "gonflement jambes",
    "gonflement visage":            "gonflement visage",
    "visage gonflé":                "gonflement visage",
    "visage enflé":                 "gonflement visage",
    "œdème":                        "œdème périphérique",
    "oedeme":                       "œdème périphérique",
    "oedème":                       "œdème périphérique",
    "rétention d'eau":              "rétention hydrique",
    "retention d'eau":              "rétention hydrique",
    "rétention hydrique":           "rétention hydrique",
    "je gonfle":                    "œdème périphérique",
    "je suis gonflé":               "œdème périphérique",
    "prise de poids rapide":        "prise de poids rapide",
    "j'ai pris du poids":           "prise de poids rapide",
    "j ai pris du poids":           "prise de poids rapide",
    "grossi rapidement":            "prise de poids rapide",
    "pris beaucoup de poids":       "prise de poids rapide",
}

# Слова що вказують на sweating (потрібні для sueurs nocturnes)
_SWEATING_WORDS: frozenset = frozenset({
    "sueur", "sueurs", "transpire", "transpiration", "moite", "mouillé",
    "trempé", "transpirer",
})

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
    "à la gorge", "tout j", "nez coule gorge", "coule gorge",
    "tout j'ai", "tout j'ai peur",
    # nocturne/nuit блокуємо у fuzzy — обробляється окремо
    "nocturne", "nuit", "nocturnes",
    "chose", "quelque", "cloche", "truc", "jsp", "jsuis",
    "tout quelque", "quelque chose", "chose cloche", "ca va pas",
    "va pas du", "pas du tout", "tout quelque chose", "quelque chose cloche",
})

_FUZZY_THRESHOLD: int = 80
_FUZZY_MIN_LEN: int = 8
_FUZZY_THRESHOLD_SHORT: int = 88


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s'àâäéèêëïîôùûüç]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _has_sweating_word(text: str) -> bool:
    """Перевіряє чи є в тексті хоч одне sweating-слово."""
    words = set(text.split())
    return bool(words & _SWEATING_WORDS)


def _apply_nocturne_context(text: str, found: list[str]) -> list[str]:
    """
    Context filter для nocturne/nuit:
    - якщо є "nocturne"/"nuit" І є sweating-слово → sueurs nocturnes (вже в synonyms)
    - якщо є "nocturne"/"nuit" І немає sweating-слова → symptomes nocturnes
    Видаляємо false positive sueurs nocturnes якщо немає sweating-слова.
    """
    has_nocturne = bool(re.search(r'\b(nocturne|nocturnes|la nuit|de nuit)\b', text))
    if not has_nocturne:
        return found

    has_sweat = _has_sweating_word(text)

    result = list(found)

    # Якщо sueurs nocturnes потрапив БЕЗ sweating-слова → видалити
    if "sueurs nocturnes" in result and not has_sweat:
        result.remove("sueurs nocturnes")

    # Якщо nocturne БЕЗ sweating → додати symptomes nocturnes
    if not has_sweat and "symptomes nocturnes" not in result:
        result.append("symptomes nocturnes")

    return result


def _apply_negations(text: str, found: list[str]) -> list[str]:
    to_remove: set[str] = set()
    for pattern, symptom in _NEGATION_RULES:
        if pattern in text:
            to_remove.add(symptom)
    return [s for s in found if s not in to_remove]


def _apply_synonyms(text: str) -> tuple[list[str], dict[str, str]]:
    """
    Повертає (знайдені симптоми, trace: symptom → matched_key).
    """
    found: list[str] = []
    trace: dict[str, str] = {}
    for key in _SORTED_SYNONYM_KEYS:
        if key in text:
            canonical = SYNONYMS[key]
            if canonical not in found:
                found.append(canonical)
                trace[canonical] = key  # який саме ключ спрацював
    return found, trace


def _fuzzy_match(text: str, already_found: set[str]) -> tuple[list[str], dict[str, str]]:
    """
    Повертає (знайдені симптоми, trace: symptom → matched_word).
    """
    results: list[str] = []
    trace: dict[str, str] = {}
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
            trace[match] = cand  # яке слово/фраза спрацювало

    return results, trace


def _validate_symptoms(
    symptoms: list[str],
    synonym_trace: dict[str, str],
    fuzzy_trace: dict[str, str],
    original_text: str,
) -> list[str]:
    """
    Validation rule (патч п.6):
    Кожен симптом доданий NLP повинен бути traceable до вхідного слова.
    Якщо trace відсутній — симптом відхиляється.
    """
    valid = []
    for symptom in symptoms:
        if symptom in synonym_trace:
            # Перевіряємо що matched_key дійсно є в оригінальному тексті
            key = synonym_trace[symptom]
            if key in original_text:
                valid.append(symptom)
            # else: відхилено — ключ не знайдено в оригіналі (не повинно траплятись, але safe)
        elif symptom in fuzzy_trace:
            # fuzzy: matched_word повинне бути підрядком оригінального тексту
            word = fuzzy_trace[symptom]
            if word in original_text:
                valid.append(symptom)
            # else: відхилено
        elif symptom == "symptomes nocturnes":
            # symptomes nocturnes додається context filter — перевіряємо nocturne/nuit в тексті
            if re.search(r'\b(nocturne|nocturnes|la nuit|de nuit)\b', original_text):
                valid.append(symptom)
        else:
            # Симптом без trace — відхиляємо
            pass
    return valid


def _is_vague_only(symptoms: list[str]) -> bool:
    """
    Retourne True si le seul symptôme détecté est un symptôme vague non-spécifique.
    Dans ce cas → insufficient_data (pas de diagnostic).
    """
    _VAGUE_SYMPTOMS: frozenset = frozenset({"malaise", "fatigue", "symptomes nocturnes"})
    return len(symptoms) == 1 and symptoms[0] in _VAGUE_SYMPTOMS


def _apply_digestif_nocturne_guard(text: str, found: list[str]) -> list[str]:
    """
    Si "la nuit" est présent AVEC un symptôme digestif (ventre, abdomen, estomac),
    supprimer symptomes_nocturnes — le contexte est digestif, pas cardiaque.
    """
    _DIGESTIF_WORDS: frozenset = frozenset({
        "ventre", "abdomen", "estomac", "digestion", "intestin",
        "bide", "intestinale", "digestif",
    })
    has_nocturne = bool(re.search(r'\b(la nuit|nocturne|nocturnes|de nuit)\b', text))
    if not has_nocturne:
        return found
    words = set(text.split())
    has_digestif = bool(words & _DIGESTIF_WORDS)
    if has_digestif and "symptomes nocturnes" in found:
        found = [s for s in found if s != "symptomes nocturnes"]
    return found


def extract_symptoms(user_input: str) -> list[str]:
    if not user_input or not user_input.strip():
        return []
    text = _normalize_text(user_input)

    synonym_hits, synonym_trace = _apply_synonyms(text)
    already = set(synonym_hits)
    fuzzy_hits, fuzzy_trace = _fuzzy_match(text, already)

    combined = synonym_hits + fuzzy_hits

    # Context filter: nocturne без sweating → symptomes nocturnes
    combined = _apply_nocturne_context(text, combined)

    # Digestif nocturne guard: "la nuit dans le ventre" → PAS cardiac
    combined = _apply_digestif_nocturne_guard(text, combined)

    # Validation: відхиляємо симптоми без trace
    combined = _validate_symptoms(combined, synonym_trace, fuzzy_trace, text)

    result = _apply_negations(text, combined)

    # Vague-only guard: si seulement malaise/fatigue → [] (insufficient_data)
    if _is_vague_only(result):
        return []

    return result