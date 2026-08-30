"""HTTP API for SPECTRA-SCAN AI."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from ..comparison.export import report_to_csv, report_to_html
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


@router.get("/presets")
def presets() -> dict:
    return {"presets": get_manager().presets()}


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


# --------------------------------------------------------------------------- #
# Dataset lab
# --------------------------------------------------------------------------- #
@router.post("/dataset/generate")
def dataset_generate(req: DatasetGenerateRequest | None = None) -> dict:
    try:
        return get_manager().generate_dataset(req or DatasetGenerateRequest())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
def dataset_load(dataset_id: str, req: DatasetLoadRequest | None = None) -> dict:
    try:
        return get_manager().load_dataset(dataset_id, req or DatasetLoadRequest())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# --------------------------------------------------------------------------- #
# Strategy comparison
# --------------------------------------------------------------------------- #
@router.post("/comparison/run")
def comparison_run(req: ComparisonRequest | None = None) -> dict:
    try:
        return get_manager().run_comparison(req or ComparisonRequest())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
