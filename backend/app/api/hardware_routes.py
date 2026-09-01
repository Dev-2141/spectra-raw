"""Receive-only hardware HTTP API (Extension Step 2).

Reads are ``viewer``. Anything that starts/stops/reconfigures a device or a
recording is ``operator`` and blocked for the demo session, and is audited.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..audit.log import audit
from ..auth.deps import Principal, Role, require_role
from ..hardware.base import HardwareUnavailable
from ..modes.manager import get_mode_manager
from ..models.core import HardwareConfig, HardwareStartRequest, RecordStartRequest
from .manager import get_manager

router = APIRouter(prefix="/api/hardware", tags=["hardware"])

_viewer = require_role(Role.viewer)
_operator = require_role(Role.operator, allow_demo=False)


def _mode() -> str:
    return get_mode_manager().mode


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
@router.get("/status")
def hardware_status(_: Principal = Depends(_viewer)) -> dict:
    return get_manager().hardware_status()


@router.get("/devices")
def hardware_devices(_: Principal = Depends(_viewer)) -> dict:
    return {"devices": get_manager().hardware_devices()}


@router.get("/frame")
def hardware_frame(_: Principal = Depends(_viewer)) -> dict:
    return {"frame": get_manager().hardware_frame()}


@router.get("/frames")
def hardware_frames(since: int = -1, _: Principal = Depends(_viewer)) -> dict:
    return get_manager().hardware_frames(since)


@router.get("/recordings")
def hardware_recordings(_: Principal = Depends(_viewer)) -> dict:
    return {"recordings": get_manager().list_recordings()}


@router.get("/recordings/{recording_id}")
def hardware_recording(recording_id: str, _: Principal = Depends(_viewer)) -> dict:
    try:
        return get_manager().get_recording(recording_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# --------------------------------------------------------------------------- #
# Controls (operator+, audited, no demo)
# --------------------------------------------------------------------------- #
@router.post("/config")
def hardware_config(
    config: HardwareConfig, principal: Principal = Depends(_operator)
) -> dict:
    try:
        out = get_manager().configure_hardware(config)
    except HardwareUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit(
        principal.username,
        "hardware.config",
        detail=config.model_dump(),
        mode=_mode(),
        role=principal.role_name,
    )
    return out


@router.post("/start")
def hardware_start(
    body: HardwareStartRequest | None = None,
    principal: Principal = Depends(_operator),
) -> dict:
    cfg = body.config if body and body.config else None
    # Log the attempt before acting, so the audit trail captures failed starts too.
    audit(
        principal.username,
        "hardware.start",
        detail={"config": cfg.model_dump() if cfg else None},
        mode=_mode(),
        role=principal.role_name,
    )
    try:
        return get_manager().start_hardware(cfg)
    except HardwareUnavailable as exc:
        audit(
            principal.username,
            "hardware.start.failed",
            detail={"error": str(exc)},
            mode=_mode(),
            role=principal.role_name,
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/stop")
def hardware_stop(principal: Principal = Depends(_operator)) -> dict:
    out = get_manager().stop_hardware()
    audit(principal.username, "hardware.stop", mode=_mode(), role=principal.role_name)
    return out


@router.post("/record/start")
def record_start(
    body: RecordStartRequest | None = None,
    principal: Principal = Depends(_operator),
) -> dict:
    try:
        out = get_manager().start_recording(body.name if body else None)
    except HardwareUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit(
        principal.username,
        "hardware.record.start",
        target=out.get("recording_id", ""),
        mode=_mode(),
        role=principal.role_name,
    )
    return out


@router.post("/record/stop")
def record_stop(principal: Principal = Depends(_operator)) -> dict:
    try:
        out = get_manager().stop_recording()
    except HardwareUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit(
        principal.username,
        "hardware.record.stop",
        target=out.get("recording_id", ""),
        detail={"frame_count": out.get("frame_count")},
        mode=_mode(),
        role=principal.role_name,
    )
    return out
