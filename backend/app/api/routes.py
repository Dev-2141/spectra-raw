"""HTTP API for SPECTRA-SCAN AI."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.core import ResetRequest, RunRequest, StepRequest, TrainRequest
from ..schedulers.registry import LEARNING_SCHEDULERS, list_schedulers
from .manager import get_manager

router = APIRouter(prefix="/api", tags=["simulation"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "product": "SPECTRA-SCAN AI",
        "mode": "simulation-only / receive-only",
        "transmit_capability": False,
    }


@router.get("/schedulers")
def schedulers() -> dict:
    return {
        "schedulers": list_schedulers(),
        "learning_schedulers": sorted(LEARNING_SCHEDULERS),
    }


@router.get("/state")
def state() -> dict:
    return get_manager().state()


@router.post("/simulation/reset")
def simulation_reset(req: ResetRequest | None = None) -> dict:
    try:
        return get_manager().reset(req or ResetRequest())
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/simulation/step")
def simulation_step(req: StepRequest | None = None) -> dict:
    body = req or StepRequest()
    try:
        return get_manager().step(body.count)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/simulation/run")
def simulation_run(req: RunRequest | None = None) -> dict:
    body = req or RunRequest()
    try:
        return get_manager().run(
            steps=body.steps,
            scheduler=body.scheduler,
            params=body.scheduler_params,
            reset=body.reset,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/simulation/train")
def simulation_train(req: TrainRequest | None = None) -> dict:
    body = req or TrainRequest()
    try:
        return get_manager().train(body)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
