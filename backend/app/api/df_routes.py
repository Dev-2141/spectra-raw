"""Direction-finding / geolocation endpoints (Extension Step 5).

Reads (nodes, fixes, health) are viewer. Placing nodes is operator. LAN peer
registration needs the shared node key from config.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..audit.log import audit
from ..auth.deps import Principal, Role, require_role
from ..config import get_settings
from ..modes.manager import get_mode_manager
from ..models.core import DFNodesRequest, DFRegisterRequest
from .manager import get_manager

router = APIRouter(prefix="/api/df", tags=["direction-finding"])
_viewer = require_role(Role.viewer)
_operator = require_role(Role.operator, allow_demo=False)


@router.get("/nodes")
def get_nodes(_: Principal = Depends(_viewer)) -> dict:
    return get_manager().df_nodes()


@router.post("/nodes")
def set_nodes(body: DFNodesRequest, principal: Principal = Depends(_operator)) -> dict:
    out = get_manager().set_df_nodes(body.nodes)
    audit(principal.username, "df.nodes.set", detail={"count": len(out["nodes"])},
          mode=get_mode_manager().mode, role=principal.role_name)
    return out


@router.post("/register")
def register_node(body: DFRegisterRequest) -> dict:
    if body.key != get_settings().df_node_key:
        raise HTTPException(status_code=403, detail="invalid node key")
    out = get_manager().df_register(body.node)
    audit("lan-node", "df.node.register", target=out["node_id"],
          mode=get_mode_manager().mode)
    return out


@router.get("/fixes")
def get_fixes(_: Principal = Depends(_viewer)) -> dict:
    return get_manager().df_fixes()


@router.get("/fixes/{track_id}")
def get_fix(track_id: str, _: Principal = Depends(_viewer)) -> dict:
    try:
        return get_manager().df_fix(track_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"no fix for track: {track_id}") from exc


@router.get("/health")
def get_health(_: Principal = Depends(_viewer)) -> dict:
    return get_manager().df_health()
