from app.models.schemas import AnalyzeResponse, Comparison, Diagnosis, Tests, Cost

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
    "Грипп":       {"required": ["Общий анализ крови", "CRP"],            "optional": ["ПЦР на грипп"]},
    "ОРВИ":        {"required": ["Общий анализ крови"],                   "optional": ["Мазок из зева"]},
    "Бронхит":     {"required": ["Общий анализ крови", "CRP", "Рентген"], "optional": ["КТ грудной клетки"]},
    "Пневмония":   {"required": ["Общий анализ крови", "CRP", "Рентген"], "optional": ["КТ грудной клетки", "Посев мокроты"]},
    "Ангина":      {"required": ["Общий анализ крови", "Мазок из зева"],  "optional": ["АСЛ-О"]},
    "Астма":       {"required": ["Спирометрия", "Общий анализ крови"],    "optional": ["Аллергопробы"]},
    "Гипертония":  {"required": ["ЭКГ", "Общий анализ крови"],            "optional": ["УЗИ сердца"]},
    "Гастрит":     {"required": ["Общий анализ крови", "Хелиобактер"],    "optional": ["ФГДС"]},
    "Анемия":      {"required": ["Общий анализ крови", "Ферритин"],       "optional": ["Витамин B12"]},
    "Аллергия":    {"required": ["Общий анализ крови", "IgE общий"],      "optional": ["Аллергопробы"]},
    "Стенокардия": {"required": ["ЭКГ", "Тропонин", "CRP"],               "optional": ["УЗИ сердца", "Холтер"]},
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

# Объяснение зачем нужен каждый анализ
TEST_EXPLANATIONS: dict[str, str] = {
    "Общий анализ крови": "показывает воспаление и общее состояние иммунитета",
    "CRP":                "маркер острого воспаления — помогает оценить тяжесть инфекции",
    "ПЦР на грипп":       "точно подтверждает или исключает вирус гриппа",
    "Мазок из зева":      "выявляет бактериальную инфекцию горла",
    "Рентген":            "показывает состояние лёгких и бронхов",
    "КТ грудной клетки":  "детальный снимок лёгких при подозрении на осложнения",
    "Посев мокроты":      "определяет возбудителя и чувствительность к антибиотикам",
    "АСЛ-О":              "выявляет перенесённую стрептококковую инфекцию",
    "Спирометрия":        "оценивает функцию дыхания при подозрении на астму",
    "Аллергопробы":       "определяет конкретные аллергены",
    "ЭКГ":                "оценивает работу сердца",
    "УЗИ сердца":         "детальная картина состояния сердечной мышцы",
    "Хелиобактер":        "выявляет бактерию — основную причину гастрита",
    "ФГДС":               "визуальный осмотр слизистой желудка",
    "Ферритин":           "показывает запасы железа в организме",
    "Витамин B12":        "проверяет уровень витамина, дефицит которого вызывает анемию",
    "IgE общий":          "показывает общий уровень аллергических антител",
    "Тропонин":           "маркер повреждения сердечной мышцы",
    "Холтер":             "суточный мониторинг сердца",
}

# Готові сценарії для демо
DEMO_SCENARIOS: dict[str, list[str]] = {
    "Простуда":  ["насморк", "боль в горле", "слабость"],
    "Грипп":     ["температура", "кашель", "головная боль", "слабость"],
    "Бронхит":   ["кашель", "одышка", "боль в груди"],
}

# Максимально можливий скор кожного діагнозу (сума всіх ваг)
DIAGNOSIS_MAX_SCORES: dict[str, float] = {}
for _weights in SYMPTOM_DIAGNOSES.values():
    for _diag, _w in _weights.items():
        DIAGNOSIS_MAX_SCORES[_diag] = DIAGNOSIS_MAX_SCORES.get(_diag, 0) + _w

# Абсолютний поріг: діагноз потрапляє у відповідь якщо покриття ≥ 15%
PROBABILITY_THRESHOLD = 0.15


def _build_explanation(symptoms: list[str], diagnoses: list[Diagnosis], required_tests: list[str]) -> str:
    if not diagnoses:
        return "По указанным симптомам диагноз определить не удалось. Обратитесь к врачу."

    top = diagnoses[0]
    symptom_str = ", ".join(f"«{s}»" for s in symptoms[:4])

    explanation = (
        f"По симптомам {symptom_str} наиболее вероятен {top.name} "
        f"(вероятность {int(top.probability * 100)}%). "
    )

    if len(diagnoses) > 1:
        others = ", ".join(d.name for d in diagnoses[1:3])
        explanation += f"Также рассматриваем: {others}. "

    reasons = [
        f"{t} — {TEST_EXPLANATIONS[t]}"
        for t in required_tests[:3]
        if t in TEST_EXPLANATIONS
    ]
    if reasons:
        explanation += "Ключевые анализы: " + "; ".join(reasons) + "."

    return explanation


def analyze(symptoms: list[str]) -> AnalyzeResponse:
    # 1. Збираємо вірогідності діагнозів
    scores: dict[str, float] = {}
    for symptom in symptoms:
        symptom_lower = symptom.lower().strip()
        for diag, weight in SYMPTOM_DIAGNOSES.get(symptom_lower, {}).items():
            scores[diag] = scores.get(diag, 0) + weight

    empty_comparison = Comparison(
        standard_tests=[], standard_cost=0,
        optimized_tests=[], optimized_cost=0,
        savings=0,
        savings_multiplier='—',
    )

    if not scores:
        return AnalyzeResponse(
            diagnoses=[],
            tests=Tests(required=[], optional=[]),
            cost=Cost(required=0, optional=0, savings=0),
            explanation="По указанным симптомам диагноз определить не удалось. Обратитесь к врачу.",
            comparison=empty_comparison,
        )

    # 2. Нормалізуємо по максимальному скору — топ діагноз завжди 1.0
    max_score = max(scores.values())
    diagnoses = sorted(
        [
            Diagnosis(name=name, probability=round(score / max_score, 2))
            for name, score in scores.items()
            if score / max_score >= PROBABILITY_THRESHOLD
        ],
        key=lambda d: d.probability,
        reverse=True,
    )[:3]

    # 3. Збираємо аналізи по топ-3 діагнозах
    required_set: set[str] = set()
    optional_set: set[str] = set()

    for diag in diagnoses[:3]:
        tests = DIAGNOSIS_TESTS.get(diag.name, {})
        required_set.update(tests.get("required", []))
        optional_set.update(tests.get("optional", []))

    optional_set -= required_set  # optional не дублює required

    # 4. Порівняння: стандарт = всі аналізи, оптимізований = тільки required
    standard_set = required_set | optional_set
    standard_cost = sum(TEST_COSTS.get(t, 0) for t in standard_set)
    optimized_cost = sum(TEST_COSTS.get(t, 0) for t in required_set)
    optional_cost = sum(TEST_COSTS.get(t, 0) for t in optional_set)

    required_list = sorted(required_set)
    optional_list = sorted(optional_set)

    return AnalyzeResponse(
        diagnoses=diagnoses,
        tests=Tests(required=required_list, optional=optional_list),
        cost=Cost(
            required=optimized_cost,
            optional=optional_cost,
            savings=optional_cost,
        ),
        explanation=_build_explanation(symptoms, diagnoses, required_list),
        comparison=Comparison(
            standard_tests=sorted(standard_set),
            standard_cost=standard_cost,
            optimized_tests=required_list,
            optimized_cost=optimized_cost,
            savings=standard_cost - optimized_cost,
            savings_multiplier=f"~{round(standard_cost / optimized_cost, 1)}x дешевле" if optimized_cost > 0 else "—",
        ),
    )