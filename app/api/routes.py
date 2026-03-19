from fastapi import APIRouter
from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.logic.engine import analyze

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse, summary="Analyze symptoms")
def analyze_symptoms(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Приймає список симптомів, повертає:
    - вірогідні діагнози
    - необхідні та опціональні аналізи
    - приблизну вартість
    """
    return analyze(request.symptoms)
