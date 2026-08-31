"""Signal analysis endpoints (Extension Step 4): tracks / anomaly / forecast."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth.deps import Principal, Role, require_role
from .manager import get_manager

router = APIRouter(prefix="/api", tags=["analysis"])
_viewer = require_role(Role.viewer)


@router.get("/tracks")
def tracks(_: Principal = Depends(_viewer)) -> dict:
    return get_manager().tracks()


@router.get("/tracks/{track_id}")
def track(track_id: str, _: Principal = Depends(_viewer)) -> dict:
    try:
        return get_manager().track(track_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown track: {track_id}") from exc


@router.get("/anomaly")
def anomaly(_: Principal = Depends(_viewer)) -> dict:
    return get_manager().anomaly()


@router.get("/forecast")
def forecast(_: Principal = Depends(_viewer)) -> dict:
    return get_manager().forecast()
