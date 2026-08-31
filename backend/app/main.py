"""FastAPI application entrypoint for SPECTRA-SCAN AI.

Run with:  uvicorn app.main:app --reload --port 8000  (from the backend/ dir)
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.analysis_routes import router as analysis_router
from .api.df_routes import router as df_router
from .api.hardware_routes import router as hardware_router
from .api.library_routes import router as library_router
from .api.montecarlo_routes import router as montecarlo_router
from .api.platform_routes import router as platform_router
from .api.rl_routes import router as rl_router
from .api.routes import public_router, router
from .api.scenario_routes import router as scenario_router
from .api.sim2real_routes import router as sim2real_router
from .api.tasking_routes import router as tasking_router
from .auth.routes import router as auth_router
from .config import get_settings

settings = get_settings()

app = FastAPI(
    title="SPECTRA-SCAN AI",
    version="0.2.0",
    description=(
        "Adaptive smart scan scheduler for SIMULATED electronic-support spectrum "
        "surveillance. Dual-mode platform: simulation, plus a receive-only live "
        "path (extension in progress). No transmission, jamming, spoofing, or "
        "real emitter data. Authenticated; every mutation is audited."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# public_router: /api/health (unauthenticated)
# auth_router:   /api/auth/*  (login / demo / me / ...)
# router:        /api/*       (viewer role required at the router level)
# platform_router: /api/mode, /api/audit, /api/tasking/protected-bands
app.include_router(public_router)
app.include_router(auth_router)
app.include_router(platform_router)
app.include_router(hardware_router)
app.include_router(scenario_router)
app.include_router(montecarlo_router)
app.include_router(analysis_router)
app.include_router(library_router)
app.include_router(tasking_router)
app.include_router(df_router)
app.include_router(rl_router)
app.include_router(sim2real_router)
app.include_router(router)


@app.get("/")
def root() -> dict:
    return {
        "product": "SPECTRA-SCAN AI",
        "docs": "/docs",
        "health": "/api/health",
        "mode": "simulation-only / receive-only",
        "auth": "enabled",
    }
