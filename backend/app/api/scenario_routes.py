"""Scenario CRUD + load (Extension Step 3).

Anyone authenticated can list, read and load a scenario. Creating, editing,
duplicating and deleting requires the ``operator`` role (and is audited);
built-in scenarios are read-only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..audit.log import audit
from ..auth.deps import Principal, Role, require_role
from ..modes.manager import get_mode_manager
from ..models.core import ScenarioSaveRequest
from ..simulation.scenario import get_scenario_store
from .manager import get_manager

router = APIRouter(prefix="/api/scenario", tags=["scenario"])

_viewer = require_role(Role.viewer)
_operator = require_role(Role.operator, allow_demo=False)


def _mode() -> str:
    return get_mode_manager().mode


@router.get("")
def list_scenarios(_: Principal = Depends(_viewer)) -> dict:
    return {"scenarios": [s.model_dump() for s in get_scenario_store().list()]}


@router.get("/{scenario_id:path}")
def get_scenario(scenario_id: str, _: Principal = Depends(_viewer)) -> dict:
    try:
        return get_scenario_store().get(scenario_id).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("")
def create_scenario(
    body: ScenarioSaveRequest, principal: Principal = Depends(_operator)
) -> dict:
    try:
        scn = get_scenario_store().save(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(principal.username, "scenario.create", target=scn.scenario_id,
          detail={"name": scn.name, "effects": len(scn.effects)},
          mode=_mode(), role=principal.role_name)
    return scn.model_dump()


@router.put("/{scenario_id:path}")
def update_scenario(
    scenario_id: str,
    body: ScenarioSaveRequest,
    principal: Principal = Depends(_operator),
) -> dict:
    try:
        scn = get_scenario_store().save(body, scenario_id=scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(principal.username, "scenario.update", target=scenario_id,
          mode=_mode(), role=principal.role_name)
    return scn.model_dump()


@router.post("/{scenario_id:path}/duplicate")
def duplicate_scenario(
    scenario_id: str, principal: Principal = Depends(_operator)
) -> dict:
    try:
        scn = get_scenario_store().duplicate(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit(principal.username, "scenario.duplicate", target=scenario_id,
          detail={"new_id": scn.scenario_id}, mode=_mode(), role=principal.role_name)
    return scn.model_dump()


@router.delete("/{scenario_id:path}")
def delete_scenario(
    scenario_id: str, principal: Principal = Depends(_operator)
) -> dict:
    try:
        get_scenario_store().delete(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(principal.username, "scenario.delete", target=scenario_id,
          mode=_mode(), role=principal.role_name)
    return {"ok": True}


@router.post("/{scenario_id:path}/load")
def load_scenario(scenario_id: str, principal: Principal = Depends(_viewer)) -> dict:
    try:
        out = get_manager().load_scenario(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit(principal.username, "scenario.load", target=scenario_id,
          mode=_mode(), role=principal.role_name)
    return out
