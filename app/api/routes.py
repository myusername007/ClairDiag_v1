import logging
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    AnalyzeRequest, AnalyzeResponse, ParseSymptomsRequest,
    RevaluateRequest, RevaluateResponse, Diagnosis,
    ParseConfirmRequest, ParseConfirmResponse,
)
from app.pipeline.nse import parse_text
import app.pipeline as pipeline_module
from app.pipeline import erl
from app.pipeline import session as session_store
from app.pipeline.tcs import run as tcs_run
from app.pipeline.rme import run as rme_run
from app.pipeline.sgl import run as sgl_run
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
            AnalyzeRequest(
                symptoms=symptoms_clean,
                onset=request.onset,
                duration=request.duration,
                debug=request.debug,
            )
        )
        logger.info(f"Résultat: {len(result.diagnoses)} diagnostics | emergency={result.emergency_flag}")

        # Créer une session pour le re-evaluation loop
        if not result.emergency_flag and result.diagnoses:
            from app.pipeline.orchestrator import PROBABILITY_THRESHOLD
            from app.pipeline import nse, scm, bpu, cre, tce
            # Recalculer probs internes pour la session
            s1 = nse.run(symptoms_clean)
            s2 = scm.run(s1)
            probs_raw, _ = bpu.run(s2)
            probs_cre = cre.run(probs_raw, s2)
            probs_tce = tce.run(probs_cre, onset=request.onset, duration=request.duration)
            session_id = session_store.create(probs_tce, s2)
            result.session_id = session_id

        return result
    except Exception as e:
        logger.error(f"Erreur pipeline: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne")


@router.post("/parse-symptoms")
def parse_symptoms_endpoint(request: ParseSymptomsRequest) -> dict:
    """Détecte les symptômes connus dans un texte libre."""
    detected = parse_text(request.text)
    return {"detected": detected, "count": len(detected)}


@router.post("/parse-confirm", response_model=ParseConfirmResponse)
def parse_confirm(request: ParseConfirmRequest) -> ParseConfirmResponse:
    """
    Étape de confirmation parser (pункт 8).
    Détecte les symptômes, retourne la liste pour confirmation utilisateur.
    Le frontend affiche "Reconnu: X, Y, Z — Confirmer?" avant /analyze.
    """
    from app.pipeline import scm
    from app.data.symptoms import ALIASES, SYMPTOM_DIAGNOSES

    # NSE — parse texte
    detected_raw = parse_text(request.text)

    # SCM — compression/déduplication
    detected = scm.run(detected_raw)

    # Identifier les mots non reconnus
    text_lower = request.text.lower()
    known_words = set(SYMPTOM_DIAGNOSES.keys()) | set(ALIASES.keys())
    words = [w.strip(".,!?;:") for w in text_lower.split()]
    unknown = [w for w in words if len(w) > 3 and w not in known_words
               and not any(w in k for k in known_words)][:5]

    # Message de confirmation
    if detected:
        items = "\n".join(f" • {s}" for s in detected)
        msg = f"Symptômes reconnus :\n{items}\n\nConfirmer pour analyser ?"
    else:
        msg = "Aucun symptôme reconnu. Essayez de décrire vos symptômes différemment."

    logger.info(f"ParseConfirm: '{request.text[:50]}' → {detected}")

    return ParseConfirmResponse(
        detected=detected,
        unknown=unknown,
        confirmation_message=msg,
        ready_to_analyze=len(detected) > 0,
    )


@router.post("/revaluate", response_model=RevaluateResponse)
def revaluate(request: RevaluateRequest) -> RevaluateResponse:
    """
    Étape 2 — recalcul des probabilités selon les résultats d'examens.
    Requiert un session_id obtenu à l'étape 1 (/analyze).
    """
    session = session_store.get(request.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session introuvable ou expirée (TTL 30 min). Relancez /analyze."
        )

    probs_before = session["probs"]
    symptoms = session["symptoms"]

    # Snapshot diagnostics avant réévaluation
    diagnoses_before = [
        Diagnosis(name=n, probability=round(p, 2))
        for n, p in sorted(probs_before.items(), key=lambda x: -x[1])[:3]
        if p >= 0.15
    ]

    # ERL — recalcul BPU avec résultats examens
    probs_after, changes_log = erl.run(probs_before, request.exam_results)

    # Recalculer TCS + RME + SGL
    tcs_level, confidence_level, _ = tcs_run(
        probs_after, len(symptoms), symptoms=symptoms
    )
    urgency_level = rme_run(probs_after)
    confidence_final, sgl_warnings = sgl_run(
        diagnoses_names=[n for n, _ in sorted(probs_after.items(), key=lambda x: -x[1])[:3]],
        probs=probs_after,
        symptom_count=len(symptoms),
        confidence_level=confidence_level,
    )

    # Diagnostics après réévaluation
    diagnoses_after = [
        Diagnosis(name=n, probability=round(p, 2))
        for n, p in sorted(probs_after.items(), key=lambda x: -x[1])[:3]
        if p >= 0.15
    ]

    # Mettre à jour la session avec les nouvelles probs
    session_store.delete(request.session_id)

    logger.info(
        f"Revaluate: session={request.session_id[:8]}… "
        f"exams={list(request.exam_results.keys())} "
        f"top={diagnoses_after[0].name if diagnoses_after else 'none'}"
    )

    return RevaluateResponse(
        session_id=request.session_id,
        diagnoses_before=diagnoses_before,
        diagnoses_after=diagnoses_after,
        changes_log=changes_log,
        tcs_level=tcs_level,
        confidence_level=confidence_final,
        urgency_level=urgency_level,
        sgl_warnings=sgl_warnings,
    )


@router.get("/scenarios")
def get_scenarios() -> dict:
    return {
        "scenarios": [
            {"name": name, "symptoms": symptoms}
            for name, symptoms in DEMO_SCENARIOS.items()
        ]
    }