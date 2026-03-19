from app.models.schemas import AnalyzeResponse, Diagnosis, Tests, Cost

# Зв'язки: симптом → діагнози з вагою 
SYMPTOM_DIAGNOSES: dict[str, dict[str, float]] = {
    "температура":      {"Грипп": 0.8, "ОРВИ": 0.7, "Бронхит": 0.4, "Пневмония": 0.3},
    "кашель":           {"Бронхит": 0.8, "ОРВИ": 0.6, "Грипп": 0.5, "Пневмония": 0.4},
    "насморк":          {"ОРВИ": 0.9, "Грипп": 0.6, "Аллергия": 0.4},
    "головная боль":    {"Грипп": 0.7, "ОРВИ": 0.5, "Гипертония": 0.4},
    "боль в горле":     {"ОРВИ": 0.8, "Ангина": 0.9, "Грипп": 0.5},
    "одышка":           {"Пневмония": 0.8, "Бронхит": 0.6, "Астма": 0.7},
    "боль в груди":     {"Пневмония": 0.6, "Бронхит": 0.4, "Стенокардия": 0.5},
    "слабость":         {"Грипп": 0.6, "ОРВИ": 0.5, "Анемия": 0.5},
    "потеря аппетита":  {"Грипп": 0.4, "Гастрит": 0.6, "Анемия": 0.4},
    "тошнота":          {"Гастрит": 0.8, "Грипп": 0.3},
}

# Зв'язки: діагноз → аналізи 
DIAGNOSIS_TESTS: dict[str, dict[str, list[str]]] = {
    "Грипп":       {"required": ["Общий анализ крови", "CRP"],           "optional": ["ПЦР на грипп"]},
    "ОРВИ":        {"required": ["Общий анализ крови"],                  "optional": ["Мазок из зева"]},
    "Бронхит":     {"required": ["Общий анализ крови", "CRP", "Рентген"], "optional": ["КТ грудной клетки"]},
    "Пневмония":   {"required": ["Общий анализ крови", "CRP", "Рентген"], "optional": ["КТ грудной клетки", "Посев мокроты"]},
    "Ангина":      {"required": ["Общий анализ крови", "Мазок из зева"],  "optional": ["АСЛ-О"]},
    "Астма":       {"required": ["Спирометрия", "Общий анализ крови"],   "optional": ["Аллергопробы"]},
    "Гипертония":  {"required": ["ЭКГ", "Общий анализ крови"],           "optional": ["УЗИ сердца"]},
    "Гастрит":     {"required": ["Общий анализ крови", "Хелиобактер"],   "optional": ["ФГДС"]},
    "Анемия":      {"required": ["Общий анализ крови", "Ферритин"],      "optional": ["Витамин B12"]},
    "Аллергия":    {"required": ["Общий анализ крови", "IgE общий"],     "optional": ["Аллергопробы"]},
    "Стенокардия": {"required": ["ЭКГ", "Тропонин", "CRP"],              "optional": ["УЗИ сердца", "Холтер"]},
}

# Вартість аналізів (грн) 
TEST_COSTS: dict[str, int] = {
    "Общий анализ крови": 80,
    "CRP":                120,
    "ПЦР на грипп":       350,
    "Мазок из зева":      150,
    "Рентген":            200,
    "КТ грудной клетки":  800,
    "Посев мокроты":      250,
    "АСЛ-О":              120,
    "Спирометрия":        300,
    "Аллергопробы":       500,
    "ЭКГ":                150,
    "УЗИ сердца":         500,
    "Хелиобактер":        180,
    "ФГДС":               600,
    "Ферритин":           140,
    "Витамин B12":        160,
    "IgE общий":          200,
    "Тропонин":           300,
    "Холтер":             400,
}

# діагнози нижче 0.35 не потрапляють у відповідь
PROBABILITY_THRESHOLD = 0.35


def analyze(symptoms: list[str]) -> AnalyzeResponse:
    # 1. Збираємо вірогідності діагнозів
    scores: dict[str, float] = {}
    for symptom in symptoms:
        symptom_lower = symptom.lower().strip()
        for diag, weight in SYMPTOM_DIAGNOSES.get(symptom_lower, {}).items():
            scores[diag] = min(1.0, scores.get(diag, 0) + weight)

    if not scores:
        return AnalyzeResponse(
            diagnoses=[],
            tests=Tests(required=[], optional=[]),
            cost=Cost(required=0, optional=0, savings=0),
        )

    # 2. Нормалізуємо і фільтруємо
    max_score = max(scores.values())
    diagnoses = sorted(
        [
            Diagnosis(name=name, probability=round(min(score / max_score, 1.0), 2))
            for name, score in scores.items()
            if score / max_score >= PROBABILITY_THRESHOLD
        ],
        key=lambda d: d.probability,
        reverse=True,
    )

    # 3. Збираємо аналізи по топ-3 діагнозах
    required_set: set[str] = set()
    optional_set: set[str] = set()

    for diag in diagnoses[:3]:
        tests = DIAGNOSIS_TESTS.get(diag.name, {})
        required_set.update(tests.get("required", []))
        optional_set.update(tests.get("optional", []))

    optional_set -= required_set  # optional не дублює required

    # 4. Рахуємо вартість
    required_cost = sum(TEST_COSTS.get(t, 0) for t in required_set)
    optional_cost = sum(TEST_COSTS.get(t, 0) for t in optional_set)

    return AnalyzeResponse(
        diagnoses=diagnoses,
        tests=Tests(required=sorted(required_set), optional=sorted(optional_set)),
        cost=Cost(
            required=required_cost,
            optional=optional_cost,
            savings=optional_cost,
        ),
    )
