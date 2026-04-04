import logging
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from app.api.routes import router
from app.models.schemas import ENGINE_VERSION, RULES_VERSION, CORE_STATUS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

logger = logging.getLogger("clairdiag")

app = FastAPI(
    title="ClairDiag",
    description="Demo: symptômes → diagnostics → analyses | CORE v2.3 LOCKED",
    version=ENGINE_VERSION,
)

app.include_router(router, prefix="/v1")


@app.on_event("startup")
async def startup_event():
    logger.info(
        f"ClairDiag started | engine={ENGINE_VERSION} | rules={RULES_VERSION} | core={CORE_STATUS}"
    )


_FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
def root():
    with open(_FRONTEND, encoding="utf-8") as f:
        return f.read()