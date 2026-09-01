"""Durable session endpoints (Extension Step 7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..audit.log import audit
from ..auth.deps import Principal, Role, require_role
from ..modes.manager import get_mode_manager
from .manager import get_manager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
_viewer = require_role(Role.viewer)
_operator = require_role(Role.operator, allow_demo=False)


@router.get("")
def list_sessions(_: Principal = Depends(_viewer)) -> dict:
    return {"sessions": get_manager().session_list()}


@router.post("/start")
def start_session(
    body: dict | None = None, principal: Principal = Depends(_operator)
) -> dict:
    body = body or {}
    out = get_manager().session_start(body.get("name", ""), body.get("tags", []))
    audit(principal.username, "session.start", target=out["session_id"],
          mode=get_mode_manager().mode, role=principal.role_name)
    return out


@router.post("/finish")
def finish_session(principal: Principal = Depends(_operator)) -> dict:
    try:
        out = get_manager().session_finish()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit(principal.username, "session.finish", target=out["session_id"],
          detail={"row_counts": out.get("row_counts")},
          mode=get_mode_manager().mode, role=principal.role_name)
    return out


@router.get("/{session_id}")
def get_session(session_id: str, _: Principal = Depends(_viewer)) -> dict:
    try:
        return get_manager().session_meta(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/data/{kind}")
def get_session_data(
    session_id: str, kind: str, _: Principal = Depends(_viewer)
) -> dict:
    try:
        return {"rows": get_manager().session_data(session_id, kind)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/export")
def export_session(session_id: str, _: Principal = Depends(_viewer)) -> Response:
    try:
        blob = get_manager().session_export(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        blob,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={session_id}.zip"},
    )


@router.post("/import")
async def import_session(
    request: Request, principal: Principal = Depends(_operator)
) -> dict:
    blob = await request.body()
    try:
        out = get_manager().session_import(blob)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(principal.username, "session.import", target=out["session_id"],
          mode=get_mode_manager().mode, role=principal.role_name)
    return out
