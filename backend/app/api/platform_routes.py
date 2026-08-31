"""Platform-level HTTP API: mode, audit, protected bands.

These endpoints exist from extension Step 1. Later steps add hardware,
scenario, DF, RL, etc. under their own routers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit.log import audit, get_audit_log
from ..auth.deps import Principal, Role, require_role
from ..modes.manager import MODES, get_mode_manager
from ..tasking.state import get_tasking_state

router = APIRouter(prefix="/api", tags=["platform"])

_viewer = require_role(Role.viewer)
_operator = require_role(Role.operator, allow_demo=False)


# --------------------------------------------------------------------------- #
# Mode
# --------------------------------------------------------------------------- #
class ModeChangeRequest(BaseModel):
    mode: str
    confirm: bool = False


@router.get("/mode")
def get_mode(_: Principal = Depends(_viewer)) -> dict:
    return get_mode_manager().snapshot()


@router.post("/mode")
def set_mode(
    body: ModeChangeRequest, principal: Principal = Depends(_operator)
) -> dict:
    if body.mode not in MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {MODES}")
    if not body.confirm:
        raise HTTPException(
            status_code=400, detail="mode change requires confirm=true"
        )
    snapshot = get_mode_manager().set_mode(body.mode)
    audit(
        principal.username,
        "mode.set",
        body.mode,
        snapshot,
        mode=snapshot["mode"],
        role=principal.role_name,
    )
    return snapshot


# --------------------------------------------------------------------------- #
# Audit (read-only; operator+)
# --------------------------------------------------------------------------- #
@router.get("/audit")
def get_audit(
    actor: str | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _: Principal = Depends(require_role(Role.operator)),
) -> dict:
    return {
        "entries": get_audit_log().query(
            actor=actor, action=action, limit=limit, offset=offset
        )
    }


# --------------------------------------------------------------------------- #
# Protected bands (never-scan list)
# --------------------------------------------------------------------------- #
class ProtectedBandsRequest(BaseModel):
    bands: list[int] = Field(default_factory=list)


@router.get("/tasking/protected-bands")
def get_protected_bands(_: Principal = Depends(_viewer)) -> dict:
    return {"protected_bands": sorted(get_tasking_state().protected_bands)}


@router.post("/tasking/protected-bands")
def set_protected_bands(
    body: ProtectedBandsRequest, principal: Principal = Depends(_operator)
) -> dict:
    out = get_tasking_state().set_protected_bands(body.bands)
    audit(
        principal.username,
        "tasking.protected_bands.set",
        detail={"bands": out},
        mode=get_mode_manager().mode,
        role=principal.role_name,
    )
    return {"protected_bands": out}
