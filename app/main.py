import logging
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from app.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

app = FastAPI(
    title="ClairDiag",
    description="Demo: симптоми → діагнози → аналізи",
    version="0.3.0",
)

app.include_router(router, prefix="/v1")

_FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
def root():
    with open(_FRONTEND, encoding="utf-8") as f:
        return f.read()
 