"""HTTP API for SPECTRA-SCAN AI.

``public_router`` carries only ``/api/health`` (unauthenticated). Everything on
``router`` requires at least the ``viewer`` role (enforced at the router level);
mutating endpoints additionally write an audit record.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from ..audit.log import audit
from ..auth.deps import Principal, Role, require_role
from ..comparison.export import report_to_csv, report_to_html
from ..modes.manager import get_mode_manager
from ..reporting import run_report_to_csv, run_report_to_html
from ..models.core import (
    ComparisonRequest,
    DatasetGenerateRequest,
    DatasetLoadRequest,
    ResetRequest,
    RunRequest,
    StepRequest,
    TrainRequest,
)
from ..schedulers.registry import (
    LEARNING_SCHEDULERS,
    available_schedulers,
    list_schedulers,
    scheduler_requirements,
)
from .manager import get_manager

public_router = APIRouter(prefix="/api", tags=["public"])

router = APIRouter(
    prefix="/api",
    tags=["simulation"],
    dependencies=[Depends(require_role(Role.viewer))],
)

_viewer = require_role(Role.viewer)


def _mode() -> str:
    return get_mode_manager().mode


# --------------------------------------------------------------------------- #
@public_router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "product": "SPECTRA-SCAN AI",
        "mode": "simulation-only / receive-only",
        "transmit_capability": False,
        "hardware_mode": "receive_only",
        "platform_mode": get_mode_manager().mode,
        "auth": "enabled",
        "version": "0.2.0",
    }


@router.get("/schedulers")
def schedulers() -> dict:
    return {
        "schedulers": list_schedulers(),
        "available": available_schedulers(),
        "requirements": scheduler_requirements(),
        "learning_schedulers": sorted(LEARNING_SCHEDULERS),
    }


@router.get("/presets")
def presets() -> dict:
    return {"presets": get_manager().presets()}


@router.get("/state")
def state() -> dict:
    return get_manager().state()


@router.post("/simulation/reset")
def simulation_reset(
    req: ResetRequest | None = None,
    principal: Principal = Depends(_viewer),
) -> dict:
    try:
        out = get_manager().reset(req or ResetRequest())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(
        principal.username,
        "simulation.reset",
        detail={
            "preset": getattr(req, "preset", None),
            "scheduler": getattr(req, "scheduler", None),
        },
        mode=_mode(),
        role=principal.role_name,
    )
    return out


@router.post("/simulation/step")
def simulation_step(
    req: StepRequest | None = None,
    principal: Principal = Depends(_viewer),
) -> dict:
    body = req or StepRequest()
    try:
        out = get_manager().step(body.count)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit(
        principal.username,
        "simulation.step",
        detail={"count": body.count},
        mode=_mode(),
        role=principal.role_name,
    )
    return out


@router.post("/simulation/run")
def simulation_run(
    req: RunRequest | None = None,
    principal: Principal = Depends(_viewer),
) -> dict:
    body = req or RunRequest()
    try:
        out = get_manager().run(
            steps=body.steps,
            scheduler=body.scheduler,
            params=body.scheduler_params,
            reset=body.reset,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(
        principal.username,
        "simulation.run",
        detail={"steps": body.steps, "scheduler": body.scheduler, "reset": body.reset},
        mode=_mode(),
        role=principal.role_name,
    )
    return out


@router.post("/simulation/train")
def simulation_train(
    req: TrainRequest | None = None,
    principal: Principal = Depends(_viewer),
) -> dict:
    body = req or TrainRequest()
    try:
        out = get_manager().train(body)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(
        principal.username,
        "simulation.train",
        detail={
            "scheduler": body.scheduler,
            "episodes": body.episodes,
            "steps_per_episode": body.steps_per_episode,
        },
        mode=_mode(),
        role=principal.role_name,
    )
    return out


# --------------------------------------------------------------------------- #
# Dataset lab
# --------------------------------------------------------------------------- #
@router.post("/dataset/generate")
def dataset_generate(
    req: DatasetGenerateRequest | None = None,
    principal: Principal = Depends(_viewer),
) -> dict:
    try:
        out = get_manager().generate_dataset(req or DatasetGenerateRequest())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(
        principal.username,
        "dataset.generate",
        detail={"name": getattr(req, "name", None)},
        mode=_mode(),
        role=principal.role_name,
    )
    return out


@router.get("/dataset/list")
def dataset_list() -> dict:
    return {"datasets": get_manager().list_datasets()}


@router.get("/dataset/{dataset_id}")
def dataset_get(dataset_id: str) -> dict:
    try:
        return get_manager().get_dataset(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/dataset/{dataset_id}/stats")
def dataset_stats(dataset_id: str) -> dict:
    try:
        return get_manager().dataset_stats(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/dataset/{dataset_id}/preview")
def dataset_preview(dataset_id: str) -> dict:
    from ..dataset.store import get_store

    try:
        return get_store().preview(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/dataset/{dataset_id}/load")
def dataset_load(
    dataset_id: str,
    req: DatasetLoadRequest | None = None,
    principal: Principal = Depends(_viewer),
) -> dict:
    try:
        out = get_manager().load_dataset(dataset_id, req or DatasetLoadRequest())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit(
        principal.username,
        "dataset.load",
        target=dataset_id,
        mode=_mode(),
        role=principal.role_name,
    )
    return out


# --------------------------------------------------------------------------- #
# Strategy comparison
# --------------------------------------------------------------------------- #
@router.post("/comparison/run")
def comparison_run(
    req: ComparisonRequest | None = None,
    principal: Principal = Depends(_viewer),
) -> dict:
    body = req or ComparisonRequest()
    try:
        out = get_manager().run_comparison(body)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(
        principal.username,
        "comparison.run",
        detail={"schedulers": list(body.schedulers), "steps": body.steps},
        mode=_mode(),
        role=principal.role_name,
    )
    return out


@router.get("/comparison/last")
def comparison_last() -> dict:
    rep = get_manager().last_comparison()
    if rep is None:
        raise HTTPException(status_code=404, detail="no comparison has been run yet")
    return rep.model_dump()


@router.get("/explainability/log")
def explainability_log(limit: int = 200) -> dict:
    limit = max(1, min(2000, limit))
    return {"log": get_manager().explainability_log(limit)}


@router.get("/training/runs")
def training_runs() -> dict:
    return {"runs": get_manager().training_runs()}


@router.get("/training/last")
def training_last() -> dict:
    last = get_manager().last_training()
    if last is None:
        raise HTTPException(status_code=404, detail="no training run yet")
    return last


@router.get("/report/run")
def report_run() -> dict:
    return get_manager().run_report()


@router.get("/report/run/export/{fmt}")
def report_run_export(fmt: str) -> Response:
    report = get_manager().run_report()
    if fmt == "json":
        import json

        return Response(
            json.dumps(report, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=run_report.json"},
        )
    if fmt == "csv":
        return Response(
            run_report_to_csv(report),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=run_report.csv"},
        )
    if fmt == "html":
        return Response(run_report_to_html(report), media_type="text/html")
    raise HTTPException(status_code=400, detail="format must be json, csv, or html")


@router.get("/comparison/export/{fmt}")
def comparison_export(fmt: str) -> Response:
    rep = get_manager().last_comparison()
    if rep is None:
        raise HTTPException(status_code=404, detail="no comparison has been run yet")
    if fmt == "json":
        return Response(
            rep.model_dump_json(indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=comparison.json"},
        )
    if fmt == "csv":
        return Response(
            report_to_csv(rep),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=comparison.csv"},
        )
    if fmt == "html":
        return Response(report_to_html(rep), media_type="text/html")
    raise HTTPException(status_code=400, detail="format must be json, csv, or html")
