"""Step 4 verification: endpoints backing the full dashboard."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _reset(**env):
    client.post(
        "/api/simulation/reset",
        json={"environment": {"num_bands": 32, "num_time_slots": 500, "seed": 5, **env},
              "scheduler": "priority"},
    )


def test_full_run_from_frontend_controls():
    # Everything the control panel sets goes through reset + run.
    r = client.post(
        "/api/simulation/reset",
        json={
            "environment": {
                "num_bands": 40,
                "num_time_slots": 800,
                "emitter_density": 0.2,
                "noise_floor_db": -102,
                "seed": 77,
            },
            "receiver": {
                "detection_threshold_db": 7,
                "dwell_slots": 1,
                "retune_delay_slots": 2,
            },
            "scheduler": "ucb_bandit",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["environment"]["num_bands"] == 40
    assert body["receiver"]["retune_delay_slots"] == 2
    assert body["scheduler"] == "ucb_bandit"

    run = client.post("/api/simulation/run", json={"steps": 400, "reset": True})
    assert run.status_code == 200
    assert run.json()["metrics"]["steps"] == 400


def test_state_has_live_waterfall_and_spectrum():
    _reset()
    client.post("/api/simulation/step", json={"count": 60})
    s = client.get("/api/state").json()
    assert len(s["spectrum"]["power_db"]) == 32
    assert len(s["waterfall"]["power_db"]) > 10
    assert len(s["waterfall"]["power_db"][0]) == 32
    assert len(s["scan_path"]) >= 50
    row = s["scan_path"][-1]
    assert {"time_slot", "scanned_band", "detected", "false_alarm", "true_active"} <= row.keys()


def test_explainability_log_endpoint():
    _reset()
    client.post("/api/simulation/step", json={"count": 80})
    log = client.get("/api/explainability/log?limit=50").json()["log"]
    assert 0 < len(log) <= 50
    row = log[-1]
    for k in (
        "time_slot", "scheduler", "selected_band", "confidence",
        "reward", "outcome", "reasons", "explanation",
    ):
        assert k in row
    assert row["outcome"] in {"hit", "miss", "false_alarm", "empty"}
    assert row["scheduler"] == "priority"
    assert isinstance(row["reasons"], list)


def test_training_runs_are_recorded():
    before = len(client.get("/api/training/runs").json()["runs"])
    client.post(
        "/api/simulation/train",
        json={"scheduler": "q_learning", "episodes": 3, "steps_per_episode": 200},
    )
    runs = client.get("/api/training/runs").json()["runs"]
    assert len(runs) == before + 1
    assert runs[0]["scheduler"] == "q_learning"
    assert len(runs[0]["episode_results"]) == 3
    assert client.get("/api/training/last").json()["scheduler"] == "q_learning"


def test_dataset_preview_downsamples():
    gen = client.post(
        "/api/dataset/generate",
        json={"name": "prev", "config": {"num_bands": 64, "num_time_slots": 1000, "seed": 8}},
    )
    ds_id = gen.json()["dataset_id"]
    try:
        p = client.get(f"/api/dataset/{ds_id}/preview").json()
        assert p["bands"] == 64 and p["time_slots"] == 1000
        assert len(p["power_db"]) <= 140 and len(p["power_db"][0]) <= 96
        assert len(p["occupancy"]) == len(p["power_db"])
    finally:
        from app.dataset.store import get_store

        get_store().delete(ds_id)


def test_run_report_and_exports():
    _reset()
    client.post("/api/simulation/run", json={"steps": 300, "reset": True})

    rep = client.get("/api/report/run").json()
    assert rep["scheduler"] == "priority"
    assert rep["metrics"]["steps"] == 300
    assert "recent_decisions" in rep and len(rep["recent_decisions"]) > 0

    csv_resp = client.get("/api/report/run/export/csv")
    assert csv_resp.status_code == 200 and "text/csv" in csv_resp.headers["content-type"]
    assert "probability_of_detection" in csv_resp.text

    j = client.get("/api/report/run/export/json")
    assert json.loads(j.text)["scheduler"] == "priority"

    assert client.get("/api/report/run/export/html").status_code == 200
    assert client.get("/api/report/run/export/xml").status_code == 400
