import logging
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from app.api.routes import router
from app.models.schemas import ENGINE_VERSION, RULES_VERSION, CORE_STATUS
from app.api.routes_v2 import router_v2
from app.api.routes_v3 import router_v3


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
app.include_router(router_v2, prefix="/v2")
app.include_router(router_v3, prefix="/v3")


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
    
_FRONTEND_V2 = os.path.join(os.path.dirname(__file__), "..", "frontend", "index_v2.html")

@app.get("/v2", include_in_schema=False, response_class=HTMLResponse)
def root_v2():
    with open(_FRONTEND_V2, encoding="utf-8") as f:
        return f.read()
    
_FRONTEND_V3 = os.path.join(os.path.dirname(__file__), "..", "frontend", "index_v3.html")

@app.get("/v3", include_in_schema=False, response_class=HTMLResponse)
def root_v3():
    with open(_FRONTEND_V3, encoding="utf-8") as f:
        return f.read()