import logging
from fastapi import APIRouter, HTTPException
from app.models.schemas import AnalyzeRequest, AnalyzeResponse, ParseSymptomsRequest
from app.pipeline.nse import parse_text
import app.pipeline as pipeline_module
from app.data.symptoms import DEMO_SCENARIOS

router = APIRouter()
logger = logging.getLogger("clairdiag")


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_symptoms(request: AnalyzeRequest) -> AnalyzeResponse:
    symptoms_clean = [s.strip() for s in request.symptoms if s.strip()]
    logger.info(f"Analyse: {symptoms_clean} | onset={request.onset} | duration={request.duration}")
    try:
        result = pipeline_module.run(
            AnalyzeRequest(symptoms=symptoms_clean, onset=request.onset, duration=request.duration)
        )
        logger.info(f"Résultat: {len(result.diagnoses)} diagnostics | emergency={result.emergency_flag}")
        return result
    except Exception as e:
        logger.error(f"Erreur pipeline: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")


@router.post("/parse-symptoms")
def parse_symptoms_endpoint(request: ParseSymptomsRequest) -> dict:
    """Détecte les symptômes connus dans un texte libre."""
    detected = parse_text(request.text)
    return {"detected": detected, "count": len(detected)}


@router.get("/scenarios")
def get_scenarios() -> dict:
    return {
        "scenarios": [
            {"name": name, "symptoms": symptoms}
            for name, symptoms in DEMO_SCENARIOS.items()
        ]
    }