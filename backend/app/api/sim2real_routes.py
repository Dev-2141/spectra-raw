"""Sim-to-real calibration + reality-gap endpoints (Step 6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..audit.log import audit
from ..auth.deps import Principal, Role, require_role
from ..modes.manager import get_mode_manager
from ..models.core import Sim2RealCalibrateRequest, Sim2RealGapRequest
from .manager import get_manager

router = APIRouter(prefix="/api/sim2real", tags=["sim2real"])
_viewer = require_role(Role.viewer)
_operator = require_role(Role.operator, allow_demo=False)


@router.post("/calibrate")
def calibrate(
    req: Sim2RealCalibrateRequest, principal: Principal = Depends(_operator)
) -> dict:
    try:
        out = get_manager().sim2real_calibrate(req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(principal.username, "sim2real.calibrate", target=out["profile_id"],
          detail={"recording_id": req.recording_id},
          mode=get_mode_manager().mode, role=principal.role_name)
    return out


@router.get("/profiles")
def profiles(_: Principal = Depends(_viewer)) -> dict:
    return get_manager().sim2real_profiles()


@router.post("/gap")
def gap(req: Sim2RealGapRequest, _: Principal = Depends(_viewer)) -> dict:
    try:
        return get_manager().sim2real_gap(req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
