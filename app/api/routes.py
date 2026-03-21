import logging
from fastapi import APIRouter, HTTPException
from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.logic.engine import analyze, DEMO_SCENARIOS

router = APIRouter()
logger = logging.getLogger("clairdiag")


@router.get("/health", summary="Проверка работоспособности")
def health():
    return {"status": "ok"}


@router.post("/analyze", response_model=AnalyzeResponse, summary="Анализ симптомов")
def analyze_symptoms(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Принимает список симптомов, возвращает:
    - вероятные диагнозы
    - необходимые и опциональные анализы
    - стоимость и потенциальную экономию
    - объяснение для человека
    - сравнение стандартного и оптимизированного пути
    """
    symptoms = [s.strip() for s in request.symptoms if s.strip()]
    logger.info(f"Запрос на анализ: {symptoms}")
    try:
        result = analyze(symptoms)
        logger.info(f"Результат: найдено {len(result.diagnoses)} диагнозов")
        return result
    except Exception as e:
        logger.error(f"Ошибка анализа: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка при анализе")


@router.get("/scenarios", summary="Список готовых сценариев для демо")
def get_scenarios() -> dict:
    """Возвращает готовые сценарии. Можно использовать как вход для POST /v1/analyze."""
    return {
        "scenarios": [
            {"name": name, "symptoms": symptoms}
            for name, symptoms in DEMO_SCENARIOS.items()
        ]
    }


