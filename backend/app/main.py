"""FastAPI application entrypoint for SPECTRA-SCAN AI.

Run with:  uvicorn app.main:app --reload --port 8000  (from the backend/ dir)
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router

app = FastAPI(
    title="SPECTRA-SCAN AI",
    version="0.1.0",
    description=(
        "Adaptive smart scan scheduler for SIMULATED electronic-support spectrum "
        "surveillance. Receive-only, simulation-only, educational prototype. "
        "No transmission, jamming, spoofing, or real emitter data."
    ),
)

_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_origins = os.getenv("SPECTRA_CORS_ORIGINS", _default_origins).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root() -> dict:
    return {
        "product": "SPECTRA-SCAN AI",
        "docs": "/docs",
        "health": "/api/health",
        "mode": "simulation-only / receive-only",
    }
