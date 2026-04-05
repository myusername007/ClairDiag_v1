# ── NLP Normalizer — ClairDiag ───────────────────────────────────────────────
# Призначення: нормалізація вільного тексту → канонічні симптоми
# Підключати ДО parse_text() у routes.py
#
# extract_symptoms(user_input: str) -> list[str]
# Повертає [] якщо нічого не знайдено → обробляти як low_confidence_input

import re
from rapidfuzz import process, fuzz

# ── Канонічні симптоми (ядро системи) ────────────────────────────────────────
KNOWN_SYMPTOMS: list[str] = [
    "douleur abdominale",
    "nausées",
    "fatigue",
    "fièvre",
    "toux",
    "essoufflement",
    "douleur thoracique",
    "céphalées",
    "rhinorrhée",
    "perte d'appétit",
    "frissons",
    "mal de gorge",
    "éternuements",
    "vomissements",
    "diarrhée",
    "vertiges",
    "douleur musculaire",
    "irritation de la gorge",
    "palpitations",
    "sueurs nocturnes",
]

# ── Синоніми (побутові фрази → канонічний симптом) ────────────────────────────
# Пріоритет над fuzzy-match; збіг підрядком
SYNONYMS: dict[str, str] = {
    # ventre / abdomen
    "mal au ventre":          "douleur abdominale",
    "mal ventre":             "douleur abdominale",
    "ventre fait mal":        "douleur abdominale",
    "ventre qui fait mal":    "douleur abdominale",
    "j'ai mal au ventre":     "douleur abdominale",
    "douleur estomac":        "douleur abdominale",
    "douleur au ventre":      "douleur abdominale",
    "crampes abdominales":    "douleur abdominale",
    "crampes au ventre":      "douleur abdominale",
    "estomac douloureux":     "douleur abdominale",

    # nausées
    "envie vomir":            "nausées",
    "envie de vomir":         "nausées",
    "vomir":                  "nausées",
    "vomis":                  "nausées",
    "coeur qui lève":         "nausées",
    "coeur soulève":          "nausées",
    "haut le coeur":          "nausées",
    "mal au coeur":           "nausées",
    "je vomis":               "nausées",

    # fatigue
    "faible":                 "fatigue",
    "fatigué":                "fatigue",
    "fatiguée":               "fatigue",
    "crevé":                  "fatigue",
    "crevée":                 "fatigue",
    "épuisé":                 "fatigue",
    "épuisée":                "fatigue",
    "sans énergie":           "fatigue",
    "pas d'énergie":          "fatigue",
    "plus d'énergie":         "fatigue",
    "je n'ai plus de forces": "fatigue",
    "asthénie":               "fatigue",

    # fièvre
    "de la température":      "fièvre",
    "j'ai de la fièvre":      "fièvre",
    "j'ai de la temperature": "fièvre",
    "température élevée":     "fièvre",
    "je fais de la fièvre":   "fièvre",
    "brûlant":                "fièvre",
    "brûlante":               "fièvre",
    "frissons":               "fièvre",

    # toux
    "je tousse":              "toux",
    "tousse":                 "toux",
    "toux sèche":             "toux",
    "toux grasse":            "toux",
    "toux productive":        "toux",
    "toux persistante":       "toux",

    # essoufflement
    "essoufflé":              "essoufflement",
    "essoufflée":             "essoufflement",
    "du mal à respirer":      "essoufflement",
    "du mal a respirer":      "essoufflement",
    "difficulté à respirer":  "essoufflement",
    "difficile de respirer":  "essoufflement",
    "souffle court":          "essoufflement",
    "manque de souffle":      "essoufflement",
    "respiration difficile":  "essoufflement",
    "halète":                 "essoufflement",
    "dyspnée":                "essoufflement",

    # douleur thoracique
    "mal à la poitrine":      "douleur thoracique",
    "mal poitrine":           "douleur thoracique",
    "douleur poitrine":       "douleur thoracique",
    "douleur au thorax":      "douleur thoracique",
    "douleur à la poitrine":  "douleur thoracique",
    "poitrine qui serre":     "douleur thoracique",
    "oppression thoracique":  "douleur thoracique",
    "serrement poitrine":     "douleur thoracique",
    "serrement dans la poitrine": "douleur thoracique",

    # céphalées
    "maux de tête":           "céphalées",
    "mal à la tête":          "céphalées",
    "mal de tête":            "céphalées",
    "tête qui fait mal":      "céphalées",
    "migraine":               "céphalées",
    "vertiges":               "vertiges",
    "vertige":                "vertiges",
    "tête qui tourne":        "vertiges",
    "la tête tourne":         "vertiges",

    # rhinorrhée / nez
    "nez qui coule":          "rhinorrhée",
    "nez bouché":             "rhinorrhée",
    "écoulement nasal":       "rhinorrhée",
    "je me mouche":           "rhinorrhée",
    "nez qui coule beaucoup": "rhinorrhée",

    # gorge
    "gorge qui fait mal":     "mal de gorge",
    "mal à la gorge":         "mal de gorge",
    "gorge douloureuse":      "mal de gorge",
    "douleur en avalant":     "mal de gorge",
    "déglutition douloureuse":"mal de gorge",
    "gorge irritée":          "irritation de la gorge",
    "gorge qui gratte":       "irritation de la gorge",
    "irritation gorge":       "irritation de la gorge",

    # perte d'appétit
    "pas faim":               "perte d'appétit",
    "plus faim":              "perte d'appétit",
    "pas d'appétit":          "perte d'appétit",
    "je mange plus":          "perte d'appétit",
    "je ne mange plus":       "perte d'appétit",
    "perte de l'appétit":     "perte d'appétit",

    # diarrhée
    "diarrhée":               "diarrhée",
    "selles liquides":        "diarrhée",
    "selles molles":          "diarrhée",

    # vomissements
    "vomissements":           "vomissements",
    "j'ai vomi":              "vomissements",
    "je vomis beaucoup":      "vomissements",

    # douleur musculaire
    "douleur musculaire":     "douleur musculaire",
    "muscles qui font mal":   "douleur musculaire",
    "courbatures":            "douleur musculaire",
    "douleurs musculaires":   "douleur musculaire",
    "tout le corps fait mal": "douleur musculaire",

    # palpitations
    "coeur qui bat vite":     "palpitations",
    "coeur qui s'emballe":    "palpitations",
    "battements rapides":     "palpitations",
    "palpitations":           "palpitations",

    # sueurs
    "sueurs":                 "sueurs nocturnes",
    "sueurs nocturnes":       "sueurs nocturnes",
    "je transpire beaucoup":  "sueurs nocturnes",
    "transpiration excessive":"sueurs nocturnes",
}

# Сортуємо ключі за довжиною (довші спочатку) — щоб "mal au ventre" ≫ "mal"
_SORTED_SYNONYM_KEYS: list[str] = sorted(SYNONYMS.keys(), key=len, reverse=True)

# Fuzzy threshold
_FUZZY_THRESHOLD: int = 82


def _normalize_text(text: str) -> str:
    """Нижній регістр + видалити пунктуацію."""
    text = text.lower()
    text = re.sub(r"[^\w\s'àâäéèêëïîôùûüç]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _apply_synonyms(text: str) -> tuple[str, list[str]]:
    """
    Шукає синоніми підрядком (довші спочатку).
    Повертає (збагачений текст, список знайдених канонічних симптомів).
    """
    found: list[str] = []
    for key in _SORTED_SYNONYM_KEYS:
        if key in text:
            canonical = SYNONYMS[key]
            if canonical not in found:
                found.append(canonical)
            # Додаємо канонічне ім'я в текст щоб fuzzy теж його підхопив
            text = text + " " + canonical
    return text, found


def _fuzzy_match(text: str, already_found: set[str]) -> list[str]:
    """
    Fuzzy-матч по окремих словах і біграмах для тих симптомів,
    яких ще не знайшли синонімами.
    """
    results: list[str] = []
    words = text.split()

    # Перевіряємо одиночні слова та біграми
    candidates: list[str] = words[:]
    for i in range(len(words) - 1):
        candidates.append(words[i] + " " + words[i + 1])

    for candidate in candidates:
        if len(candidate) < 3:
            continue
        match_result = process.extractOne(
            candidate,
            KNOWN_SYMPTOMS,
            scorer=fuzz.partial_ratio,
        )
        if match_result is None:
            continue
        match, score, _ = match_result
        if score >= _FUZZY_THRESHOLD and match not in already_found and match not in results:
            results.append(match)

    return results


def extract_symptoms(user_input: str) -> list[str]:
    """
    Головна функція.
    Вхід: довільний текст французькою (або мікс мов).
    Вихід: список канонічних симптомів.
    Порожній список = low_confidence_input.
    """
    if not user_input or not user_input.strip():
        return []

    text = _normalize_text(user_input)
    text_enriched, synonym_hits = _apply_synonyms(text)
    already = set(synonym_hits)
    fuzzy_hits = _fuzzy_match(text_enriched, already)

    combined = synonym_hits + [h for h in fuzzy_hits if h not in already]
    return combined


# ── Самотест ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cases = [
        ("mal au ventre envie vomir faible",
         ["douleur abdominale", "nausées", "fatigue"]),
        ("je tousse et j'ai de la fièvre depuis hier",
         ["toux", "fièvre"]),
        ("essoufflé mal à la poitrine",
         ["essoufflement", "douleur thoracique"]),
        ("maux de tête nez qui coule éternuements",
         ["céphalées", "rhinorrhée", "éternuements"]),
        ("",
         []),
    ]
    ok = 0
    for text, expected in cases:
        result = extract_symptoms(text)
        result_set = set(result)
        exp_set = set(expected)
        passed = exp_set.issubset(result_set)
        status = "✓" if passed else "✗"
        print(f"{status} '{text[:40]}' → {result}")
        if passed:
            ok += 1
    print(f"\n{ok}/{len(cases)} tests passed")