# ClairDiag

Система интеллектуальной диагностики: по симптомам подбирает вероятные диагнозы, оптимальный план анализов и оценивает экономию.

**Live:** https://clairdiagv1-production.up.railway.app/

---

## Что делает

Принимает список симптомов (+ опционально: характер появления и длительность), возвращает:

- вероятные диагнозы с весовой вероятностью (макс. 75%)
- рекомендуемые анализы — до 3, отобранных по соотношению диагностическая ценность / стоимость
- дополнительные анализы по показаниям
- сравнение стандартного и оптимизированного пути в €
- объяснение результата простым языком
- уровень доверия: `élevé / modéré / faible` (составной score)
- уровень решения: `fort / besoin_tests / incertain`
- предупреждения при противоречиях между симптомами
- экстренный флаг при red flag симптомах

---

## Архитектура — CORE v2

Модульный pipeline из 10 шагов. Порядок фиксирован — нарушать нельзя.

```
симптомы
    │
    ▼
1. NSE  — нормализация и разрешение алиасов
2. SCM  — компрессия до 5–12 ключевых симптомов
3. RFE  — проверка red flags (до scoring)
    │ EMERGENCY? → стоп, вернуть алерт
    ▼
4. BPU  — вероятностный scoring (специфичность + комбо + исключения)
           → также считает incoherence_score
5. RME  — оценка уровня риска
6. TCE  — темпоральные корректировки (onset + duration)
7. CRE  — медицинские правила (HAS-like)
8. TCS  — пороги решения + composite confidence
9. LME  — выбор анализов по score = value / cost, макс 3
10. SGL — финальная проверка: инкогеренция, противоречия, cap confidence
    │
    ▼
AnalyzeResponse
```

### Composite confidence (п.5 ТЗ)

Не просто процент — три компоненты:

| Компонента | Вес | Что измеряет |
|------------|-----|--------------|
| couverture | 40% | доля симптомов, покрытых топ-диагнозом |
| cohérence  | 35% | разрыв между топ и 2-м диагнозом |
| qualité    | 25% | количество предоставленных симптомов |

Ограничение: при ≤ 2 симптомах — cap 0.55.

### Incoherence Engine (п.6 ТЗ)

BPU накапливает `incoherence_score` из суммы пенальти несовместимых симптомов.
SGL использует score для снижения confidence и генерации предупреждений:

- `≥ 0.15` → warning
- `≥ 0.30` → снижение confidence на уровень

---

## Структура проекта

```
app/
├── data/
│   ├── symptoms.py       — словарь симптомов, алиасы, комбо-бонусы, исключения
│   └── tests.py          — каталог анализов с diagnostic_value и стоимостью
├── models/
│   └── schemas.py        — Pydantic-схемы запроса и ответа
├── pipeline/
│   ├── orchestrator.py   — оркестратор, запускает шаги по порядку
│   ├── nse.py            — шаг 1: парсер
│   ├── scm.py            — шаг 2: компрессия
│   ├── rfe.py            — шаг 3: red flags
│   ├── bpu.py            — шаг 4: scoring + incoherence
│   ├── rme.py            — шаг 5: risk module
│   ├── tce.py            — шаг 6: temporal logic
│   ├── cre.py            — шаг 7: medical rules
│   ├── tcs.py            — шаг 8: thresholds + composite confidence
│   ├── lme.py            — шаг 9: test selection
│   └── sgl.py            — шаг 10: safety layer
└── api/
    └── routes.py         — FastAPI endpoints
frontend/
└── index.html            — UI
```

---

## Запуск

```bash
docker-compose up --build
```

| URL | Описание |
|-----|----------|
| `http://localhost:8006/` | Demo-интерфейс |
| `http://localhost:8006/docs` | Swagger UI |

---

## Тесты

```bash
pip install -r requirements.txt
pytest tests/ -v
```

---

## Endpoints

| Метод | URL | Описание |
|-------|-----|----------|
| POST | `/v1/analyze` | Анализ симптомов |
| POST | `/v1/parse-symptoms` | Детектировать симптомы в свободном тексте |
| GET | `/v1/scenarios` | Готовые клинические сценарии |
| GET | `/v1/health` | Health check |

---

## Пример запроса / ответа

Request:
```json
{
  "symptoms": ["fièvre", "toux", "fatigue"],
  "onset": "brutal",
  "duration": "days"
}
```

Response:
```json
{
  "diagnoses": [
    {"name": "Grippe",         "probability": 0.75, "key_symptoms": ["fièvre", "toux", "fatigue"]},
    {"name": "Bronchite",      "probability": 0.51, "key_symptoms": ["toux"]},
    {"name": "Rhinopharyngite","probability": 0.43, "key_symptoms": ["fièvre", "fatigue"]}
  ],
  "tests": {
    "required": ["CRP", "NFS"],
    "optional": ["PCR grippe"]
  },
  "cost": {"required": 75, "optional": 30, "savings": 15},
  "explanation": "Les symptômes correspondent le plus probablement à une Grippe...",
  "comparison": {
    "standard_cost": 90,
    "optimized_cost": 75,
    "savings": 15,
    "savings_multiplier": "~1.2x moins cher"
  },
  "confidence_level": "modéré",
  "urgency_level": "faible",
  "tcs_level": "besoin_tests",
  "emergency_flag": false,
  "sgl_warnings": []
}
```

### Red flag пример

Request:
```json
{"symptoms": ["cyanose", "essoufflement"]}
```

Response:
```json
{
  "emergency_flag": true,
  "emergency_reason": "Cyanose détectée — appel du 15 (SAMU) immédiat requis.",
  "urgency_level": "élevé",
  "diagnoses": []
}
```

---

## Логика без AI

Система намеренно не использует ML. Вся логика — детерминированная и аудируемая:

- **Специфичность** — симптомы с меньшим числом диагнозов имеют больший вес
- **Комбо-бонусы** — определённые сочетания усиливают диагноз
- **Исключения** — несовместимые симптомы снижают вероятность
- **Медицинские правила** — `fièvre → infection+`, `sans fièvre → infection−` и др.
- **Темпоральная логика** — `brutal onset → буст острых патологий`

Вероятности — весовые, не клиническая статистика.

---

## Дисклеймер

Система не является медицинской рекомендацией и не заменяет врача.
При red flag симптомах (`cyanose`, `syncope` и др.) — немедленно вызывайте скорую.
Стоимость анализов ориентировочная — средние цены Франция / ЕС, для демонстрации оптимизации.