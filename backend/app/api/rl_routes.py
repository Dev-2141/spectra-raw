"""RL training, online learning, and explainability++ endpoints (Step 6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..audit.log import audit
from ..auth.deps import Principal, Role, require_role
from ..modes.manager import get_mode_manager
from ..models.core import OnlineEnableRequest, RLTrainRequest
from .manager import get_manager

router = APIRouter(prefix="/api", tags=["rl"])
_viewer = require_role(Role.viewer)
_operator = require_role(Role.operator, allow_demo=False)


def _mode() -> str:
    return get_mode_manager().mode


# --- training jobs --------------------------------------------------- #
@router.post("/rl/train")
def rl_train(req: RLTrainRequest, principal: Principal = Depends(_operator)) -> dict:
    try:
        out = get_manager().rl_submit(req)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(principal.username, "rl.train", target=out["job_id"],
          detail={"scheduler": req.scheduler, "episodes": req.episodes,
                  "curriculum": req.curriculum},
          mode=_mode(), role=principal.role_name)
    return out


@router.get("/rl/jobs")
def rl_jobs(_: Principal = Depends(_viewer)) -> dict:
    return get_manager().rl_jobs()


@router.get("/rl/jobs/{job_id}")
def rl_job(job_id: str, _: Principal = Depends(_viewer)) -> dict:
    try:
        return get_manager().rl_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}") from exc


@router.post("/rl/jobs/{job_id}/promote")
def rl_promote(job_id: str, principal: Principal = Depends(_operator)) -> dict:
    try:
        out = get_manager().rl_promote(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(principal.username, "rl.promote", target=job_id, mode=_mode(),
          role=principal.role_name)
    return out


# --- online learning --------------------------------------------- #
@router.post("/online/enable")
def online_enable(
    req: OnlineEnableRequest, principal: Principal = Depends(_operator)
) -> dict:
    try:
        out = get_manager().enable_online(req)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(principal.username, "online.enable", detail=req.model_dump(),
          mode=_mode(), role=principal.role_name)
    return out


@router.post("/online/disable")
def online_disable(principal: Principal = Depends(_operator)) -> dict:
    out = get_manager().disable_online()
    audit(principal.username, "online.disable", mode=_mode(), role=principal.role_name)
    return out


@router.get("/online/status")
def online_status(_: Principal = Depends(_viewer)) -> dict:
    return get_manager().online_status()


# --- explainability++ ------------------------------------------ #
@router.get("/explain/policy")
def explain_policy(_: Principal = Depends(_viewer)) -> dict:
    return get_manager().explain_policy()
