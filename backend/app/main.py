"""Tunisian Bac Analytics & Prediction Engine - FastAPI entrypoint.
Run:  uvicorn app.main:app --reload      (Swagger UI at /docs)"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .deps import load_store
from .routers import analytics, records
from .services.data_store import DatasetError

log = logging.getLogger("bac")


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = load_store()                      # fail fast if the CSV is missing/corrupt
    log.info("Dataset loaded: %d records", len(store.df))
    yield


app = FastAPI(title="Tunisian Bac Analytics & Prediction Engine", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET"], allow_headers=["*"])
app.include_router(records.router)
app.include_router(analytics.router)


@app.exception_handler(DatasetError)
async def dataset_error(_: Request, exc: DatasetError):
    return JSONResponse(status_code=503, content={"detail": f"Dataset unavailable: {exc}"})


@app.get("/api/health")
def health():
    return {"status": "ok"}
