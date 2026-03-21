from app.models.schemas import AnalyzeResponse, Comparison, Diagnosis, Tests, Cost

# Зв'язки: симптом → діагнози з вагою
SYMPTOM_DIAGNOSES: dict[str, dict[str, float]] = {
    "температура":      {"Грипп": 0.8, "ОРВИ": 0.7, "Бронхит": 0.4, "Пневмония": 0.3, "Ангина": 0.5},
    "кашель":           {"Бронхит": 0.8, "ОРВИ": 0.6, "Грипп": 0.5, "Пневмония": 0.4, "Аллергия": 0.3},
    "насморк":          {"ОРВИ": 0.9, "Грипп": 0.6, "Аллергия": 0.5},
    "головная боль":    {"Грипп": 0.7, "ОРВИ": 0.5, "Гипертония": 0.4},
    "боль в горле":     {"ОРВИ": 0.8, "Ангина": 0.9, "Грипп": 0.5},
    "одышка":           {"Пневмония": 0.8, "Бронхит": 0.6, "Астма": 0.7, "Стенокардия": 0.4},
    "боль в груди":     {"Пневмония": 0.6, "Бронхит": 0.4, "Стенокардия": 0.8},
    "слабость":         {"Грипп": 0.6, "ОРВИ": 0.5, "Анемия": 0.5, "Ангина": 0.4, "Пневмония": 0.4},
    "потеря аппетита":  {"Грипп": 0.4, "Гастрит": 0.6, "Анемия": 0.4},
    "тошнота":          {"Гастрит": 0.8, "Грипп": 0.3},
    "чихание":          {"Аллергия": 0.8, "ОРВИ": 0.4},
    "зуд в горле":      {"Аллергия": 0.7},
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

# Референсні ціни (€, середній ринок Франція / ЄС, для демо)
TEST_COSTS: dict[str, int] = {
    "Общий анализ крови": 20,
    "CRP":                15,
    "ПЦР на грипп":       40,
    "Мазок из зева":      25,
    "Рентген":            80,
    "КТ грудной клетки":  200,
    "Посев мокроты":      45,
    "АСЛ-О":              20,
    "Спирометрия":        60,
    "Аллергопробы":       90,
    "ЭКГ":                40,
    "УЗИ сердца":         85,
    "Хелиобактер":        35,
    "ФГДС":               120,
    "Ферритин":           25,
    "Витамин B12":        25,
    "IgE общий":          35,
    "Тропонин":           25,
    "Холтер":             80,
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
    "Ангина":    ["боль в горле", "температура", "слабость"],
    "Пневмония": ["температура", "кашель", "одышка", "боль в груди"],
    "Аллергия":  ["насморк", "чихание", "зуд в горле"],
}

# ── Слой 1: специфичность симптомов ────────────────────────────────────────
# Симптом, указывающий на меньше диагнозов, несёт больше информации.
# Шкала: n=1 → ×1.40 | n=2 → ×1.30 | n=3 → ×1.20 | n=4 → ×1.10 | n=5 → ×1.00
_MAX_DIAG_COUNT = max(len(w) for w in SYMPTOM_DIAGNOSES.values())


def _specificity(n: int) -> float:
    return 1.0 + 0.5 * max(0.0, 1.0 - n / _MAX_DIAG_COUNT)


# Pre-compute max possible score per diagnosis (с учётом специфичности)
DIAGNOSIS_MAX_SCORES: dict[str, float] = {}
for _sym, _weights in SYMPTOM_DIAGNOSES.items():
    _f = _specificity(len(_weights))
    for _diag, _w in _weights.items():
        DIAGNOSIS_MAX_SCORES[_diag] = DIAGNOSIS_MAX_SCORES.get(_diag, 0) + _w * _f

# Минимальный знаменатель — защита от завышенных % у диагнозов с малой базой
_MIN_DENOM = 2.0

# Порог включения диагноза в ответ
PROBABILITY_THRESHOLD = 0.15


# ── Слой 2: бонусы комбинаций ───────────────────────────────────────────────
# Определённые сочетания симптомов диагностически сильнее их суммы.
# Бонус применяется только если диагноз уже обнаружен по базовым весам.
COMBO_BONUSES: list[tuple[frozenset[str], dict[str, float]]] = [
    (frozenset({"температура", "кашель", "одышка"}),           {"Пневмония": 0.25}),
    (frozenset({"кашель", "одышка"}),                          {"Бронхит": 0.15, "Астма": 0.15}),
    (frozenset({"насморк", "чихание", "зуд в горле"}),         {"Аллергия": 0.35}),
    (frozenset({"боль в горле", "температура"}),               {"Ангина": 0.20}),
    (frozenset({"боль в груди", "одышка"}),                    {"Стенокардия": 0.25, "Пневмония": 0.15}),
    (frozenset({"температура", "головная боль", "слабость"}),  {"Грипп": 0.20}),
    (frozenset({"тошнота", "потеря аппетита"}),                {"Гастрит": 0.20}),
    (frozenset({"слабость", "потеря аппетита"}),               {"Анемия": 0.15}),
]


# ── Слой 3: исключающие признаки ────────────────────────────────────────────
# Некоторые симптомы снижают вероятность несовместимых диагнозов.
SYMPTOM_EXCLUSIONS: dict[str, dict[str, float]] = {
    "чихание":      {"Пневмония": 0.15, "Бронхит": 0.10, "Стенокардия": 0.20},
    "зуд в горле":  {"Грипп": 0.15, "Бронхит": 0.15, "Пневмония": 0.20},
    "тошнота":      {"Астма": 0.15, "Аллергия": 0.10},
    "насморк":      {"Стенокардия": 0.20, "Гастрит": 0.15},
    "боль в груди": {"Гастрит": 0.15, "Аллергия": 0.15},
}


# ── Explanation ─────────────────────────────────────────────────────────────
def _build_explanation(symptoms: list[str], diagnoses: list[Diagnosis], required_tests: list[str]) -> str:
    if not diagnoses:
        return "Недостаточно симптомов для определения диагноза. Попробуйте добавить больше или обратитесь к врачу."

    top = diagnoses[0]
    pct = int(top.probability * 100)

    if pct >= 65:
        start = f"Скорее всего это {top.name}."
    elif pct >= 40:
        start = f"Вероятнее всего — {top.name}."
    else:
        start = f"Возможно, это {top.name}, но симптомов пока недостаточно."

    alt = f" Также нельзя исключить {diagnoses[1].name}." if len(diagnoses) > 1 else ""

    first_two = [t for t in required_tests[:2] if t in TEST_EXPLANATIONS]
    tests_hint = ""
    if first_two:
        joined = " и ".join(f"{t} — {TEST_EXPLANATIONS[t]}" for t in first_two)
        tests_hint = f" Для первичной проверки достаточно: {joined}."

    return start + alt + tests_hint


# ── Основная функция ─────────────────────────────────────────────────────────
def analyze(symptoms: list[str]) -> AnalyzeResponse:
    symptom_set = {s.lower().strip() for s in symptoms}

    empty_comparison = Comparison(
        standard_tests=[], standard_cost=0,
        optimized_tests=[], optimized_cost=0,
        savings=0, savings_multiplier="—",
    )

    # Слой 1 — базовый скор с учётом специфичности симптома
    raw: dict[str, float] = {}
    for sym in symptom_set:
        weights = SYMPTOM_DIAGNOSES.get(sym, {})
        factor = _specificity(len(weights)) if weights else 1.0
        for diag, weight in weights.items():
            raw[diag] = raw.get(diag, 0) + weight * factor

    if not raw:
        return AnalyzeResponse(
            diagnoses=[],
            tests=Tests(required=[], optional=[]),
            cost=Cost(required=0, optional=0, savings=0),
            explanation="По указанным симптомам диагноз определить не удалось. Обратитесь к врачу.",
            comparison=empty_comparison,
        )

    # Нормализация: какую долю максимально возможных улик мы собрали?
    probs: dict[str, float] = {
        name: min(score / max(DIAGNOSIS_MAX_SCORES[name], _MIN_DENOM), 1.0)
        for name, score in raw.items()
    }

    # Слой 2 — бонусы комбинаций (только усиливают уже найденные диагнозы)
    for combo, bonuses in COMBO_BONUSES:
        if combo.issubset(symptom_set):
            for diag, bonus in bonuses.items():
                if diag in probs:
                    probs[diag] = min(1.0, probs[diag] + bonus)

    # Слой 3 — штрафы за несовместимые симптомы
    for sym in symptom_set:
        for diag, penalty in SYMPTOM_EXCLUSIONS.get(sym, {}).items():
            if diag in probs:
                probs[diag] = max(0.0, probs[diag] - penalty)

    # Финальный кап: вероятность не превышает 75% — честнее для demo
    _MAX_PROB = 0.75
    probs = {name: min(prob, _MAX_PROB) for name, prob in probs.items()}

    # Фильтрация, сортировка, топ-3
    diagnoses = sorted(
        [
            Diagnosis(name=name, probability=round(prob, 2))
            for name, prob in probs.items()
            if prob >= PROBABILITY_THRESHOLD
        ],
        key=lambda d: d.probability,
        reverse=True,
    )[:3]

    # Сбор анализов по топ-3 диагнозам
    # Базовый набор первичной проверки — всегда в required (если присутствует)
    BASE_REQUIRED = {"Общий анализ крови", "CRP"}

    all_tests: set[str] = set()
    for diag in diagnoses:
        tests = DIAGNOSIS_TESTS.get(diag.name, {})
        all_tests.update(tests.get("required", []))
        all_tests.update(tests.get("optional", []))

    # required = только базовые анализы из тех, что вообще показаны
    # optional = всё остальное
    required_set = all_tests & BASE_REQUIRED
    optional_set = all_tests - BASE_REQUIRED

    standard_set   = all_tests
    standard_cost  = sum(TEST_COSTS.get(t, 0) for t in standard_set)
    optimized_cost = sum(TEST_COSTS.get(t, 0) for t in required_set)
    optional_cost  = sum(TEST_COSTS.get(t, 0) for t in optional_set)
    required_list  = sorted(required_set)
    optional_list  = sorted(optional_set)

    return AnalyzeResponse(
        diagnoses=diagnoses,
        tests=Tests(required=required_list, optional=optional_list),
        cost=Cost(required=optimized_cost, optional=optional_cost, savings=optional_cost),
        explanation=_build_explanation(list(symptom_set), diagnoses, required_list),
        comparison=Comparison(
            standard_tests=sorted(standard_set),
            standard_cost=standard_cost,
            optimized_tests=required_list,
            optimized_cost=optimized_cost,
            savings=standard_cost - optimized_cost,
            savings_multiplier=(
                f"~{round(standard_cost / optimized_cost, 1)}x дешевле"
                if optimized_cost > 0 else "—"
            ),
        ),
    )