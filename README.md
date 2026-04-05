# ClairDiag v2.3

Система интеллектуальной диагностики симптомов. Принимает свободный текст или список симптомов — возвращает вероятные диагнозы, оптимальный план анализов, экономический расчёт и полный клинический reasoning.

**Live:** https://clairdiagv1-production.up.railway.app/

---

## Что делает

- Понимает **любой текст** на французском: разговорный, с опечатками, argot (`mal au ventre`, `je suis KO`, `barbouillé`, `gerber`)
- Возвращает до 3 вероятных диагнозов с весовой вероятностью
- Рекомендует анализы по соотношению диагностическая ценность / стоимость
- Считает экономию vs стандартный путь в €
- Генерирует клинический reasoning, diagnostic tree, сценарии
- Expert Mode — полный разбор логики для врача / инвестора
- Детектирует red flags → экстренный алерт

---

## Архитектура — CORE v2.3 LOCKED

Модульный детерминированный pipeline из 10 шагов.

```
free text / symptoms
       │
       ▼
[NLP Normalizer]  — 120+ синонимов FR, fuzzy match, negation, typo
       │
       ▼
1.  NSE  — нормализация, алиасы → SYMPTOM_DIAGNOSES
2.  SCM  — компрессия до 5–12 ключевых симптомов
3.  RFE  — red flags (до scoring) → EMERGENCY если найдено
       │
       ▼
4.  BPU  — вероятностный scoring + combo bonuses + exclusions + incoherence_score
5.  RME  — уровень риска (urgency_level)
6.  TCE  — темпоральные корректировки (onset + duration)
7.  CRE  — медицинские правила (HAS-like)
8.  TCS  — пороги решения + composite confidence (4 компоненты)
9.  LME  — выбор анализов: score = diagnostic_value / cost, макс 3
10. SGL  — safety check: инкогеренция, противоречия, cap confidence
       │
       ▼
  AnalyzeResponse (30+ полей)
```

### Composite confidence

| Компонента | Вес | Описание |
|---|---|---|
| couverture | 35% | доля симптомов, покрытых топ-диагнозом |
| cohérence | 35% | разрыв top1 − top2 |
| qualité | 20% | количество симптомов |
| red_flag penalty | −10% | при наличии срочных симптомов |

Cap: ≤ 1 симптом → 0.35, ≤ 2 симптома → 0.55, gap < 0.10 → 0.55.

### Decision Engine 2.0

| Decision | Условие |
|---|---|
| `EMERGENCY` | red flag override |
| `URGENT_MEDICAL_REVIEW` | urgency élevé |
| `TESTS_REQUIRED` | TCS_2 |
| `MEDICAL_REVIEW` | TCS_3 / TCS_4 |
| `LOW_RISK_MONITOR` | TCS_1, низкий риск |

---

## Структура проекта

```
app/
├── data/
│   ├── symptoms.py          — SYMPTOM_DIAGNOSES, ALIASES, COMBO_BONUSES, EXCLUSIONS
│   └── tests.py             — TEST_CATALOG с diagnostic_value и стоимостью
├── models/
│   └── schemas.py           — Pydantic v2 схемы (30+ полей в AnalyzeResponse)
├── pipeline/
│   ├── nlp_normalizer.py    — NLP: 120+ синонимов, fuzzy, negation
│   ├── orchestrator.py      — оркестратор + все builder-функции
│   ├── nse.py               — шаг 1: парсер + алиасы
│   ├── scm.py               — шаг 2: компрессия
│   ├── rfe.py               — шаг 3: red flags
│   ├── bpu.py               — шаг 4: scoring + incoherence
│   ├── rme.py               — шаг 5: risk
│   ├── tce.py               — шаг 6: temporal
│   ├── cre.py               — шаг 7: medical rules
│   ├── tcs.py               — шаг 8: confidence + TCS level
│   ├── lme.py               — шаг 9: test selection
│   ├── sgl.py               — шаг 10: safety layer
│   ├── erl.py               — post-test re-evaluation
│   ├── session.py           — session store (TTL 30 min)
│   ├── cost_engine.py       — economic layer
│   └── request_logger.py    — structured request logging
└── api/
    └── routes.py            — FastAPI endpoints
frontend/
└── index.html               — UI (vanilla JS, no framework)
```

---

## Запуск

```bash
docker-compose up --build
```

| URL | |
|---|---|
| `http://localhost:8006/` | Demo UI |
| `http://localhost:8006/docs` | Swagger |
| `http://localhost:8006/v1/health` | Health check |

---

## Endpoints

| Метод | URL | Описание |
|---|---|---|
| POST | `/v1/analyze` | Анализ симптомов |
| POST | `/v1/parse-symptoms` | Детектировать симптомы в тексте |
| POST | `/v1/parse-confirm` | Детектировать + подтверждение |
| POST | `/v1/revaluate` | Post-test reasoning (после результатов анализов) |
| GET | `/v1/scenarios` | Готовые клинические сценарии |
| GET | `/v1/health` | Health check + версии |
| GET | `/v1/admin/debug` | Debug trace pipeline |

---

## Пример запроса

```bash
# Свободный текст
curl -X POST /v1/parse-confirm \
  -d '{"text": "j'\''ai mal au ventre, envie de vomir et un peu de fièvre"}'

# Анализ симптомов
curl -X POST /v1/analyze \
  -d '{"symptoms": ["fièvre", "toux", "fatigue"], "onset": "brutal", "duration": "days"}'
```

## Пример ответа `/v1/analyze`

```json
{
  "diagnoses": [
    {"name": "Grippe", "probability": 0.46, "key_symptoms": ["fièvre","toux","fatigue"]},
    {"name": "Bronchite", "probability": 0.35, "key_symptoms": ["toux"]},
    {"name": "Rhinopharyngite", "probability": 0.31, "key_symptoms": ["fièvre","fatigue"]}
  ],
  "tests": {"required": ["CRP","NFS"], "optional": ["PCR grippe"]},
  "decision": "TESTS_REQUIRED",
  "confidence_level": "modéré",
  "urgency_level": "faible",
  "economics": {"standard_cost": 120, "optimized_cost": 75, "savings": 45},
  "clinical_reasoning": {
    "why_top1": "Grippe retenu car fièvre, toux, fatigue présentent une valeur diagnostique élevée (46%)",
    "test_strategy": "Priorité à CRP pour confirmer Grippe",
    "risk_logic": "Risque faible à modéré — Grippe sans signe de gravité immédiate"
  },
  "diagnostic_tree": [
    {"step": 1, "action": "CRP", "if_positive": "Radiographie pulmonaire si contexte respiratoire", "if_negative": "Profil infectieux peu probable"}
  ],
  "quality_gate": {"passed": true, "score": 0.97, "threshold": 0.97},
  "self_check": {"logic_consistent": true, "no_conflicts": true, "decision_valid": true},
  "trust_score": {"global_score": 0.72, "data_quality": 0.6, "model_confidence": 0.8},
  "stability": {"reproducible": true, "variance": 0.0},
  "trace_id": "87e56f416921900d",
  "is_valid_output": true
}
```

---

## NLP Normalizer

Понимает любой французский текст — включая разговорный, argot и опечатки.

```python
extract_symptoms("mal au ventre envie de vomir je suis KO")
# → ["douleur abdominale", "nausées", "fatigue"]

extract_symptoms("barbouillé depuis ce matin")
# → ["nausées"]

extract_symptoms("fiavr toux fatig")
# → ["fièvre", "toux", "fatigue"]
```

**Calibration: 55/55 (100%)** на трёх пакетах тест-кейсов (базовые / расширенные / ультра-хаотичные).

---

## API Response — полная структура

`AnalyzeResponse` содержит 30+ полей, сгруппированных в блоки:

| Блок | Поля |
|---|---|
| Core | `diagnoses`, `tests`, `explanation`, `decision` |
| Confidence | `confidence_level`, `tcs_level`, `urgency_level` |
| Safety | `emergency_flag`, `safety`, `do_not_miss`, `sgl_warnings` |
| Clinical | `clinical_reasoning`, `diagnostic_path`, `differential`, `test_details` |
| Economics | `economics`, `economic_impact` |
| NLP | `interpreted_symptoms`, `input_confidence` |
| Decision | `decision_logic`, `consistency_check`, `scenario_simulation` |
| Trust | `trust_score`, `edge_case_analysis`, `misdiagnosis_risk` |
| Absolute Mode | `quality_gate`, `self_check`, `stability`, `trace_id`, `is_valid_output` |
| Meta | `compliance`, `is_fallback`, `session_id`, `worsening_signs` |

---

## Absolute Mode (Quality Gate)

Каждый ответ проходит автоматическую валидацию:

```json
"quality_gate": {
  "passed": true,
  "score": 0.97,
  "threshold": 0.97,
  "block_reason": ""
}
```

**Self-check проверки:**
- `logic_consistent` — топ-диагноз поддержан хотя бы 1 симптомом
- `no_conflicts` — incoherence_score < 0.30
- `decision_valid` — decision соответствует risk profile
- `tests_relevant` — тесты имеют diagnostic_value для топ-диагноза
- `risk_aligned` — confidence не противоречит misdiagnosis_risk

**Anti-fake validation:**
- Высокая вероятность без поддерживающих симптомов → penalty
- Один симптом + confidence ≥ 0.75 → penalty
- Все вероятности одинаковые (degenerate output) → penalty

---

## Тесты

```bash
pytest tests/ -v

# Regression suite
python run_tests.py        # gold pack
python run_gold_30.py      # 30 gold cases
python test_pack1.py       # NLP calibration pack 1 (15 cases)
python test_pack2.py       # NLP calibration pack 2 (20 cases)
python test_pack3.py       # NLP calibration pack 3 (20 cases, chaotic)
```

---

## Версии

| Компонент | Версия |
|---|---|
| ENGINE | v2.3 |
| RULES | v1.2 |
| REGISTRY | v1.0 |
| CORE STATUS | LOCKED |
| VALIDATION BASELINE | H15_G30_F40_S100 |

---

## Дисклеймер

Система не является медицинской рекомендацией и не заменяет врача.  
При red flag симптомах — немедленно вызывайте скорую (15 / 112).  
Вероятности весовые, не клиническая статистика.  
Стоимость анализов ориентировочная — средние цены Франция / ЕС.