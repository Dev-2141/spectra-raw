"""Step 3 verification: dataset generation/replay + strategy comparison + export."""

from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.comparison.engine import compare_strategies
from app.comparison.export import report_to_csv, report_to_html
from app.dataset.generator import BEHAVIOR_LABELS, build_dataset
from app.dataset.store import DatasetStore
from app.main import app
from app.models.core import RFEnvironmentConfig, ReceiverConfig
from app.simulation.engine import Simulation
from app.simulation.environment import RFEnvironment

client = TestClient(app)

SMALL = RFEnvironmentConfig(num_bands=24, num_time_slots=300, seed=99)


@pytest.fixture
def store(tmp_path) -> DatasetStore:
    return DatasetStore(root=tmp_path / "datasets")


# --------------------------------------------------------------------------- #
# Dataset generation / persistence / replay
# --------------------------------------------------------------------------- #
def test_build_dataset_shapes_and_labels():
    meta, arrays = build_dataset(SMALL, name="unit")
    assert meta.number_of_bands == 24 and meta.number_of_time_slots == 300
    for key in ("occupancy", "power_db", "snr_db", "threat", "labels", "emitter_id"):
        assert arrays[key].shape == (300, 24)
    # labels are -1 (inactive) or a valid behavior code
    valid = set(BEHAVIOR_LABELS.values()) | {-1}
    assert set(np.unique(arrays["labels"])).issubset(valid)
    # a label is set exactly where occupancy is set
    assert np.array_equal(arrays["labels"] >= 0, arrays["occupancy"].astype(bool))


def test_dataset_save_load_roundtrip(store: DatasetStore):
    meta, arrays = build_dataset(SMALL, name="roundtrip")
    saved = store.save(meta, arrays)
    assert saved.files  # populated on save

    reloaded = store.load_arrays(saved.dataset_id)
    for key in arrays:
        assert np.array_equal(arrays[key], reloaded[key]), key

    got = store.get(saved.dataset_id)
    assert got.dataset_id == saved.dataset_id
    assert got.stats.occupancy_percentage == saved.stats.occupancy_percentage
    assert saved.dataset_id in [m.dataset_id for m in store.list()]


def test_replay_env_reproduces_ground_truth(store: DatasetStore):
    meta, arrays = build_dataset(SMALL, name="replay")
    saved = store.save(meta, arrays)

    original = RFEnvironment(SMALL)
    replay = store.build_replay_env(saved.dataset_id)

    assert replay.replayed is True
    assert np.array_equal(original.occupancy, replay.occupancy)
    assert np.allclose(original.snr_db, replay.snr_db)
    assert np.allclose(original.threat, replay.threat)
    assert len(original.events) == len(replay.events)
    assert original.active_bands(10) == replay.active_bands(10)


def test_replay_env_drives_simulation(store: DatasetStore):
    meta, arrays = build_dataset(SMALL, name="drive")
    saved = store.save(meta, arrays)
    env = store.build_replay_env(saved.dataset_id)

    sim = Simulation(SMALL, ReceiverConfig(), "priority", env_instance=env)
    results = sim.run(250)
    assert len(results) == 250
    m = sim.metrics_snapshot()
    assert m.steps == 250 and 0.0 <= m.scan_coverage <= 1.0


def test_stats_match_matrix(store: DatasetStore):
    meta, arrays = build_dataset(SMALL, name="stats")
    occ = arrays["occupancy"].astype(bool)
    assert meta.stats.occupancy_percentage == round(float(occ.mean()), 5)
    assert meta.stats.active_band_count == int(occ.any(axis=0).sum())
    assert meta.stats.active_time_count == int(occ.any(axis=1).sum())
    assert sum(meta.stats.emitter_type_distribution.values()) == len(meta.emitters)
    assert abs(meta.stats.sparsity_score - (1 - meta.stats.occupancy_percentage)) < 1e-6


# --------------------------------------------------------------------------- #
# Strategy comparison
# --------------------------------------------------------------------------- #
COMP_SCHEDULERS = ["round_robin", "random", "priority", "epsilon_bandit", "ucb_bandit", "q_learning"]


def test_comparison_runs_all_strategies_same_seed():
    rep = compare_strategies(
        RFEnvironmentConfig(num_bands=32, num_time_slots=600, seed=7),
        ReceiverConfig(),
        COMP_SCHEDULERS,
        steps=400,
    )
    assert [e.scheduler for e in rep.entries] == sorted(
        [e.scheduler for e in rep.entries], key=lambda s: rep.ranking.index(s)
    )
    assert set(rep.ranking) == set(COMP_SCHEDULERS)
    assert rep.scenario_seed == 7
    assert rep.winner == rep.ranking[0]
    # ranks are 1..N, unique
    assert sorted(e.rank for e in rep.entries) == list(range(1, len(COMP_SCHEDULERS) + 1))


def test_comparison_metrics_not_hardcoded():
    rep = compare_strategies(
        RFEnvironmentConfig(num_bands=32, num_time_slots=600, seed=7),
        ReceiverConfig(),
        ["round_robin", "priority"],
        steps=500,
    )
    by = {e.scheduler: e.metrics for e in rep.entries}
    assert by["round_robin"].model_dump() != by["priority"].model_dump()
    assert by["round_robin"].average_reward != by["priority"].average_reward


def test_comparison_shared_environment_is_identical():
    cfg = RFEnvironmentConfig(num_bands=20, num_time_slots=300, seed=55)
    a = Simulation(cfg, ReceiverConfig(), "round_robin")
    b = Simulation(cfg, ReceiverConfig(), "priority")
    assert np.array_equal(a.env.occupancy, b.env.occupancy)
    assert np.allclose(a.env.snr_db, b.env.snr_db)


def test_comparison_series_are_populated():
    rep = compare_strategies(
        RFEnvironmentConfig(num_bands=24, num_time_slots=400, seed=3),
        ReceiverConfig(),
        ["round_robin", "priority"],
        steps=300,
        series_points=30,
    )
    for e in rep.entries:
        assert len(e.series.time_slot) > 5
        assert len(e.series.average_reward) == len(e.series.time_slot)


def test_export_csv_json_html():
    rep = compare_strategies(
        RFEnvironmentConfig(num_bands=20, num_time_slots=300, seed=1),
        ReceiverConfig(),
        ["round_robin", "priority", "random"],
        steps=200,
    )
    csv_txt = report_to_csv(rep)
    lines = csv_txt.strip().splitlines()
    assert lines[0].startswith("scheduler,rank,weighted_score")
    assert len(lines) == 1 + 3

    html = report_to_html(rep)
    assert rep.winner in html and "<table" in html


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_api_dataset_lifecycle_and_replay():
    gen = client.post(
        "/api/dataset/generate",
        json={"name": "api-test", "config": {"num_bands": 20, "num_time_slots": 250, "seed": 4242}},
    )
    assert gen.status_code == 200, gen.text
    ds_id = gen.json()["dataset_id"]
    try:
        assert gen.json()["stats"]["occupancy_percentage"] >= 0.0

        lst = client.get("/api/dataset/list").json()["datasets"]
        assert ds_id in [d["dataset_id"] for d in lst]

        assert client.get(f"/api/dataset/{ds_id}").json()["number_of_bands"] == 20
        assert "sparsity_score" in client.get(f"/api/dataset/{ds_id}/stats").json()

        loaded = client.post(f"/api/dataset/{ds_id}/load", json={"scheduler": "priority"})
        assert loaded.status_code == 200
        body = loaded.json()
        assert body["dataset_id"] == ds_id and body["replay_mode"] is True
        assert body["environment"]["num_bands"] == 20

        run = client.post("/api/simulation/run", json={"steps": 150, "reset": True})
        assert run.status_code == 200
        assert run.json()["replay_mode"] is True
        assert run.json()["steps_executed"] == 150
    finally:
        from app.dataset.store import get_store

        get_store().delete(ds_id)
        client.post("/api/simulation/reset", json={"environment": {"seed": 1234}})


def test_api_dataset_get_missing_is_404():
    assert client.get("/api/dataset/does_not_exist").status_code == 404


def test_api_comparison_run_and_export():
    r = client.post(
        "/api/comparison/run",
        json={
            "schedulers": ["round_robin", "random", "priority", "q_learning"],
            "steps": 300,
            "seed": 21,
        },
    )
    assert r.status_code == 200, r.text
    rep = r.json()
    assert len(rep["entries"]) == 4
    assert rep["winner"] in rep["ranking"]
    assert rep["scenario_seed"] == 21
    assert len(rep["metrics_table"]) == 4

    csv_resp = client.get("/api/comparison/export/csv")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert csv_resp.text.count("\n") >= 4

    json_resp = client.get("/api/comparison/export/json")
    assert json_resp.status_code == 200
    assert json.loads(json_resp.text)["winner"] == rep["winner"]

    assert client.get("/api/comparison/export/html").status_code == 200


def test_api_comparison_unknown_scheduler_400():
    r = client.post("/api/comparison/run", json={"schedulers": ["bogus"], "steps": 50})
    assert r.status_code == 400
