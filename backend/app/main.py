"""FastAPI application entrypoint for SPECTRA-SCAN AI.

Run with:  uvicorn app.main:app --reload --port 8000  (from the backend/ dir)
Production:  SPECTRA_PRODUCTION=1 SPECTRA_JWT_KEY=... SPECTRA_TLS_CERT=... \
             SPECTRA_TLS_KEY=... SPECTRA_SEED_USERS=0 SPECTRA_CORS_ORIGINS=... \
             uvicorn app.main:app --host 0.0.0.0 --port 8443 \
             --ssl-certfile $SPECTRA_TLS_CERT --ssl-keyfile $SPECTRA_TLS_KEY
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .ratelimit import RateLimiter

from .api.analysis_routes import router as analysis_router
from .api.df_routes import router as df_router
from .api.hardware_routes import router as hardware_router
from .api.library_routes import router as library_router
from .api.montecarlo_routes import router as montecarlo_router
from .api.platform_routes import router as platform_router
from .api.rl_routes import router as rl_router
from .api.routes import public_router, router
from .api.scenario_routes import router as scenario_router
from .api.sessions_routes import router as sessions_router
from .api.sim2real_routes import router as sim2real_router
from .api.stream_routes import router as stream_router
from .api.tasking_routes import router as tasking_router
from .auth.routes import router as auth_router
from .config import get_settings, validate_production

settings = get_settings()

# Refuse to start in production with any insecure default.
validate_production(settings)

app = FastAPI(
    title="SPECTRA-SCAN AI",
    version="0.3.0",
    description=(
        "Adaptive smart scan scheduler for SIMULATED electronic-support spectrum "
        "surveillance. Dual-mode platform: simulation + receive-only live path. "
        "No transmission, jamming, spoofing, or real emitter data. Authenticated; "
        "every mutation audited. Air-gapped; no outbound network."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Middleware: /api/v1 alias, per-IP rate limit, security headers
# --------------------------------------------------------------------------- #
_rate_limiter = RateLimiter(settings.rate_limit_rpm)


@app.middleware("http")
async def platform_middleware(request: Request, call_next):
    scope_path = request.scope.get("path", "")

    # /api/v1/<rest>  ->  /api/<rest>   (frozen v1 alias)
    if scope_path == "/api/v1" or scope_path.startswith("/api/v1/"):
        request.scope["path"] = "/api" + scope_path[len("/api/v1") :]

    ip = request.client.host if request.client else "?"
    if scope_path.startswith("/api") and ip != "testclient":
        if not _rate_limiter.allow(ip):
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy", "default-src 'self'; connect-src 'self' ws: wss:"
    )
    return response


# --------------------------------------------------------------------------- #
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
app.include_router(sessions_router)
app.include_router(stream_router)
app.include_router(router)


@app.get("/api")
def api_root() -> dict:
    return {"product": "SPECTRA-SCAN AI", "api_version": "v1", "health": "/api/health"}


# --------------------------------------------------------------------------- #
# Serve the built frontend from the backend in production (no CDN, no network).
# --------------------------------------------------------------------------- #
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if settings.serve_frontend and _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
else:

    @app.get("/")
    def root() -> dict:
        return {
            "product": "SPECTRA-SCAN AI",
            "docs": "/docs",
            "health": "/api/health",
            "ws": "/ws?token=<jwt>",
            "auth": "enabled",
        }
