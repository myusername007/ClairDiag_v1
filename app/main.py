import logging
from fastapi import FastAPI
from app.api.routes import router
 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
 
app = FastAPI(
    title="ClairDiag",
    description="Demo: симптоми → діагнози → аналізи",
    version="0.2.0",
)
 
app.include_router(router, prefix="/v1")
 
 
@app.get("/", include_in_schema=False)
def root():
    return {"service": "ClairDiag", "docs": "/docs", "health": "/v1/health"}
 