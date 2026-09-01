"""Tasking (watch lists + alert rules) and alert lifecycle (Extension Step 4).

Protected bands stay on the platform router. Watch lists and alert rules are
operator-set; ack / close on an alert is analyst+.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..audit.log import audit
from ..auth.deps import Principal, Role, require_role
from ..modes.manager import get_mode_manager
from ..models.core import AlertRulesRequest, WatchListsRequest
from .manager import get_manager

router = APIRouter(prefix="/api", tags=["tasking"])
_viewer = require_role(Role.viewer)
_analyst = require_role(Role.analyst, allow_demo=False)
_operator = require_role(Role.operator, allow_demo=False)


def _mode() -> str:
    return get_mode_manager().mode


# --- watch lists ------------------------------------------------------ #
@router.get("/tasking/watchlists")
def get_watchlists(_: Principal = Depends(_viewer)) -> dict:
    return get_manager().watch_lists()


@router.post("/tasking/watchlists")
def set_watchlists(
    body: WatchListsRequest, principal: Principal = Depends(_operator)
) -> dict:
    out = get_manager().set_watch_lists(body.watch_lists)
    audit(principal.username, "tasking.watchlists.set",
          detail={"count": len(out["watch_lists"])}, mode=_mode(),
          role=principal.role_name)
    return out


# --- alert rules --------------------------------------------------- #
@router.get("/tasking/alert-rules")
def get_alert_rules(_: Principal = Depends(_viewer)) -> dict:
    return get_manager().alert_rules()


@router.post("/tasking/alert-rules")
def set_alert_rules(
    body: AlertRulesRequest, principal: Principal = Depends(_operator)
) -> dict:
    out = get_manager().set_alert_rules(body.alert_rules)
    audit(principal.username, "tasking.alert_rules.set",
          detail={"count": len(out["alert_rules"])}, mode=_mode(),
          role=principal.role_name)
    return out


# --- alerts ------------------------------------------------------ #
@router.get("/alerts")
def list_alerts(state: str | None = None, _: Principal = Depends(_viewer)) -> dict:
    return get_manager().alerts(state)


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: str, principal: Principal = Depends(_analyst)) -> dict:
    try:
        out = get_manager().set_alert_state(alert_id, "ack")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown alert: {alert_id}") from exc
    audit(principal.username, "alert.ack", target=alert_id, mode=_mode(),
          role=principal.role_name)
    return out


@router.post("/alerts/{alert_id}/close")
def close_alert(alert_id: str, principal: Principal = Depends(_analyst)) -> dict:
    try:
        out = get_manager().set_alert_state(alert_id, "closed")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown alert: {alert_id}") from exc
    audit(principal.username, "alert.close", target=alert_id, mode=_mode(),
          role=principal.role_name)
    return out
