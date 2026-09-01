"""Synthetic emitter/threat library endpoints (Extension Step 4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..audit.log import audit
from ..auth.deps import Principal, Role, require_role
from ..library.store import get_library
from ..modes.manager import get_mode_manager
from ..models.core import LibraryEntrySaveRequest

router = APIRouter(prefix="/api/library", tags=["library"])
_viewer = require_role(Role.viewer)
_operator = require_role(Role.operator, allow_demo=False)


def _mode() -> str:
    return get_mode_manager().mode


@router.get("")
def list_entries(_: Principal = Depends(_viewer)) -> dict:
    return {"entries": [e.model_dump() for e in get_library().list()]}


@router.get("/{entry_id}")
def get_entry(entry_id: str, _: Principal = Depends(_viewer)) -> dict:
    try:
        return get_library().get(entry_id).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{entry_id}/revisions")
def get_revisions(entry_id: str, _: Principal = Depends(_viewer)) -> dict:
    return {"revisions": [r.model_dump() for r in get_library().revisions(entry_id)]}


@router.post("")
def create_entry(
    body: LibraryEntrySaveRequest, principal: Principal = Depends(_operator)
) -> dict:
    try:
        entry = get_library().create(body, actor=principal.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(principal.username, "library.create", target=entry.entry_id,
          detail={"name": entry.name}, mode=_mode(), role=principal.role_name)
    return entry.model_dump()


@router.put("/{entry_id}")
def update_entry(
    entry_id: str,
    body: LibraryEntrySaveRequest,
    principal: Principal = Depends(_operator),
) -> dict:
    try:
        entry = get_library().update(entry_id, body, actor=principal.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(principal.username, "library.update", target=entry_id,
          detail={"revision": entry.revision}, mode=_mode(), role=principal.role_name)
    return entry.model_dump()


@router.delete("/{entry_id}")
def delete_entry(entry_id: str, principal: Principal = Depends(_operator)) -> dict:
    try:
        get_library().delete(entry_id, actor=principal.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit(principal.username, "library.delete", target=entry_id,
          mode=_mode(), role=principal.role_name)
    return {"ok": True, "history_retained": True}
