# ClairDiag

Demo-система интеллектуальной диагностики: по симптомам подбирает вероятные диагнозы и оптимальный план анализов.

**Live:** https://clairdiag-production.up.railway.app/

---

## Что делает

Принимает список симптомов, возвращает:
- вероятные диагнозы с весовой вероятностью (макс. 75%)
- рекомендуемые анализы (базовый набор: NFS + CRP)
- дополнительные анализы по показаниям
- сравнение стандартного и оптимизированного пути в € (диапазон цен)
- объяснение результата простым языком
- уровень доверия: élevé / modéré / faible

---

## Как работает

Три слоя логики без AI:

```
симптом → диагноз → анализы
```

1. **Специфичность** — симптомы с меньшим числом диагнозов имеют больший вес
2. **Комбо-бонусы** — определённые сочетания симптомов усиливают диагноз
3. **Исключения** — несовместимые симптомы снижают вероятность диагноза

Вероятности — весовые, не клиническая статистика.
Система не выполняет реальную медицинскую диагностику.

---

## Запуск

```bash
docker-compose up --build
```

| URL | Описание |
|-----|----------|
| `http://localhost:8005/` | Demo-интерфейс |
| `http://localhost:8005/docs` | Swagger UI |

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
| GET | `/v1/scenarios` | Готовые сценарии |
| GET | `/v1/health` | Health check |

---

## Пример

Request:
```json
{"symptoms": ["fièvre", "toux", "fatigue"]}
```

Response:
```json
{
  "diagnoses": [
    {"name": "Grippe",    "probability": 0.75},
    {"name": "Bronchite", "probability": 0.51},
    {"name": "Rhinopharyngite", "probability": 0.47}
  ],
  "tests": {
    "required": ["CRP", "NFS"],
    "optional": ["PCR grippe", "Radiographie pulmonaire", "Scanner thoracique"]
  },
  "cost": {"required": 110, "optional": 510, "savings": 510},
  "explanation": "Les symptômes correspondent le plus probablement à une Grippe. Une Bronchite ne peut pas être totalement exclue. Pour une première évaluation, les analyses suivantes sont suffisantes : NFS et CRP.",
  "comparison": {
    "standard_cost": 620,
    "optimized_cost": 110,
    "savings": 510,
    "savings_multiplier": "~5.6x moins cher",
    "standard_range": "~405€ – 640€",
    "optimized_range": "~85€ – 150€",
    "savings_range": "~255€ – 555€",
    "cost_note": "Exemple basé sur un cas clinique courant — prix indicatifs (marché France / UE)"
  },
  "confidence_level": "élevé"
}
```

---

## Дисклеймер

Система не является медицинской рекомендацией и не заменяет врача.
Стоимость ориентировочная — средние рыночные цены (Франция / ЕС), для демонстрации ценности продукта.