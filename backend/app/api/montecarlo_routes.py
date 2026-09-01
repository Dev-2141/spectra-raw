"""Monte-Carlo evaluation endpoints (Extension Step 3)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response

from ..audit.log import audit
from ..auth.deps import Principal, Role, require_role
from ..comparison.montecarlo import (
    get_cached,
    montecarlo_to_csv,
    montecarlo_to_html,
)
from ..modes.manager import get_mode_manager
from ..models.core import MonteCarloRequest
from .manager import get_manager

router = APIRouter(prefix="/api/montecarlo", tags=["montecarlo"])

_viewer = require_role(Role.viewer)


@router.post("/run")
def montecarlo_run(
    body: MonteCarloRequest, principal: Principal = Depends(_viewer)
) -> dict:
    try:
        out = get_manager().run_montecarlo(body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(
        principal.username,
        "montecarlo.run",
        target=out.get("montecarlo_id", ""),
        detail={
            "scenario_id": body.scenario_id,
            "schedulers": body.schedulers,
            "seeds": len(out.get("seeds", [])),
            "steps": body.steps,
        },
        mode=get_mode_manager().mode,
        role=principal.role_name,
    )
    return out


@router.get("/last")
def montecarlo_last(_: Principal = Depends(_viewer)) -> dict:
    rep = get_manager().last_montecarlo()
    if rep is None:
        raise HTTPException(status_code=404, detail="no Monte Carlo run yet")
    return rep.model_dump()


@router.get("/{montecarlo_id}")
def montecarlo_get(montecarlo_id: str, _: Principal = Depends(_viewer)) -> dict:
    rep = get_cached(montecarlo_id)
    if rep is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {montecarlo_id}")
    return rep.model_dump()


@router.get("/{montecarlo_id}/export/{fmt}")
def montecarlo_export(
    montecarlo_id: str, fmt: str, _: Principal = Depends(_viewer)
) -> Response:
    rep = get_cached(montecarlo_id)
    if rep is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {montecarlo_id}")
    if fmt == "json":
        return Response(
            json.dumps(rep.model_dump(), indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=montecarlo.json"},
        )
    if fmt == "csv":
        return Response(
            montecarlo_to_csv(rep),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=montecarlo.csv"},
        )
    if fmt == "html":
        return Response(montecarlo_to_html(rep), media_type="text/html")
    raise HTTPException(status_code=400, detail="format must be json, csv, or html")
