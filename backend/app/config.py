"""Typed runtime settings (environment + safe defaults).

No secrets in source. Every key is documented in
``hdw extension prompt.md`` Appendix C. Later extension steps read the feature
flags declared here; Step 1 only consumes the auth / data / mode keys.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

_BACKEND_DIR = Path(__file__).resolve().parents[1]  # .../backend
DEFAULT_JWT_KEY = "spectra-dev-insecure-key-change-me"  # noqa: S105 - intentional dev default


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _int_list(name: str, default: list[int]) -> list[int]:
    raw = os.getenv(name)
    if not raw:
        return list(default)
    out: list[int] = []
    for tok in raw.replace(",", " ").split():
        try:
            out.append(int(tok))
        except ValueError:
            continue
    return out


class Settings(BaseModel):
    jwt_key: str
    jwt_key_is_default: bool
    token_ttl_hours: int
    seed_users: bool
    production: bool
    data_dir: Path
    cors_origins: list[str]
    protected_bands: list[int]
    rate_limit_rpm: int
    df_node_key: str
    tls_cert_path: str
    tls_key_path: str
    retention_days: int
    db_encryption_key: str
    serve_frontend: bool

    # Feature flags — declared now, consumed by later extension steps.
    flag_soapysdr: bool
    flag_torch_rl: bool
    flag_torch_classifier: bool
    flag_ws_streaming: bool
    flag_df: bool
    flag_online_learning: bool

    @property
    def platform_db(self) -> Path:
        return self.data_dir / "platform.db"

    @property
    def audit_dir(self) -> Path:
        return self.data_dir / "audit"


@lru_cache
def get_settings() -> Settings:
    production = _flag("SPECTRA_PRODUCTION", False)
    data_dir = Path(
        os.getenv("SPECTRA_DATA_DIR", str(_BACKEND_DIR / "data"))
    ).resolve()
    origins_raw = os.getenv(
        "SPECTRA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    jwt_key = os.getenv("SPECTRA_JWT_KEY", "").strip() or DEFAULT_JWT_KEY

    settings = Settings(
        jwt_key=jwt_key,
        jwt_key_is_default=(jwt_key == DEFAULT_JWT_KEY),
        token_ttl_hours=_int("SPECTRA_TOKEN_TTL_HOURS", 12),
        seed_users=_flag("SPECTRA_SEED_USERS", not production),
        production=production,
        data_dir=data_dir,
        cors_origins=[o.strip() for o in origins_raw.split(",") if o.strip()],
        protected_bands=_int_list("SPECTRA_PROTECTED_BANDS", []),
        rate_limit_rpm=_int("SPECTRA_RATE_LIMIT_RPM", 600),
        df_node_key=os.getenv("SPECTRA_DF_NODE_KEY", "spectra-df-lan-key"),
        tls_cert_path=os.getenv("SPECTRA_TLS_CERT", ""),
        tls_key_path=os.getenv("SPECTRA_TLS_KEY", ""),
        retention_days=_int("SPECTRA_RETENTION_DAYS", 30),
        db_encryption_key=os.getenv("SPECTRA_DB_ENCRYPTION_KEY", ""),
        serve_frontend=_flag("SPECTRA_SERVE_FRONTEND", production),
        flag_soapysdr=_flag("FLAG_SOAPYSDR", False),
        flag_torch_rl=_flag("FLAG_TORCH_RL", False),
        flag_torch_classifier=_flag("FLAG_TORCH_CLASSIFIER", False),
        flag_ws_streaming=_flag("FLAG_WS_STREAMING", True),
        flag_df=_flag("FLAG_DF", True),
        flag_online_learning=_flag("FLAG_ONLINE_LEARNING", False),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings


class InsecureProductionConfig(RuntimeError):
    """Raised when --production is set but an insecure default remains."""


def validate_production(settings: "Settings | None" = None) -> list[str]:
    """Return the list of production violations; raise if any and production is on."""
    s = settings or get_settings()
    if not s.production:
        return []
    problems: list[str] = []
    if s.jwt_key_is_default:
        problems.append("SPECTRA_JWT_KEY is the built-in default")
    if s.seed_users:
        problems.append("SPECTRA_SEED_USERS is on (seeded admin/admin etc.)")
    if not (s.tls_cert_path and s.tls_key_path):
        problems.append("no SPECTRA_TLS_CERT / SPECTRA_TLS_KEY configured")
    if "localhost" in " ".join(s.cors_origins) or "127.0.0.1" in " ".join(s.cors_origins):
        problems.append("CORS still allows localhost origins")
    if problems:
        raise InsecureProductionConfig(
            "refusing to start in production: " + "; ".join(problems)
        )
    return problems


def _reset_for_tests() -> None:
    get_settings.cache_clear()
