"""Step 1 verification tests."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.models.core import RFEnvironmentConfig, ReceiverConfig
from app.simulation.engine import Simulation
from app.simulation.environment import RFEnvironment

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Environment
# --------------------------------------------------------------------------- #
def test_environment_matrix_shapes():
    cfg = RFEnvironmentConfig(num_bands=32, num_time_slots=200, seed=7)
    env = RFEnvironment(cfg)
    assert env.occupancy.shape == (200, 32)
    assert env.power_db.shape == (200, 32)
    assert env.threat.shape == (200, 32)
    assert env.snr_db.shape == (200, 32)
    assert len(env.bands) == 32


def test_environment_has_activity_and_events():
    cfg = RFEnvironmentConfig(num_bands=64, num_time_slots=1000, seed=1)
    env = RFEnvironment(cfg)
    assert env.occupancy.any(), "environment produced no activity"
    assert 0.0 < env.occupancy_percentage() < 1.0
    assert len(env.events) > 0
    assert all(e.end >= e.start for e in env.events)


def test_environment_deterministic_by_seed():
    a = RFEnvironment(RFEnvironmentConfig(seed=42, num_time_slots=300))
    b = RFEnvironment(RFEnvironmentConfig(seed=42, num_time_slots=300))
    assert np.array_equal(a.occupancy, b.occupancy)
    assert np.allclose(a.power_db, b.power_db)


# --------------------------------------------------------------------------- #
# Receiver / engine
# --------------------------------------------------------------------------- #
def test_step_advances_time():
    sim = Simulation(
        RFEnvironmentConfig(num_bands=16, num_time_slots=100, seed=3),
        ReceiverConfig(),
        "round_robin",
    )
    assert sim.t == 0
    sim.step()
    assert sim.t == 1
    sim.step()
    assert sim.t == 2


def test_round_robin_cycles_bands():
    sim = Simulation(
        RFEnvironmentConfig(num_bands=8, num_time_slots=50, seed=3),
        ReceiverConfig(),
        "round_robin",
    )
    picked = [sim.step().decision.selected_band for _ in range(16)]
    assert picked[:8] == list(range(8))
    assert picked[8:] == list(range(8))


def test_random_scheduler_runs_and_stays_in_range():
    sim = Simulation(
        RFEnvironmentConfig(num_bands=20, num_time_slots=400, seed=9),
        ReceiverConfig(),
        "random",
    )
    results = sim.run(300)
    assert len(results) == 300
    assert all(0 <= r.decision.selected_band < 20 for r in results)


def test_metrics_populated_after_run():
    sim = Simulation(
        RFEnvironmentConfig(num_bands=64, num_time_slots=1000, seed=5),
        ReceiverConfig(),
        "round_robin",
    )
    sim.run(500)
    m = sim.metrics_snapshot()
    assert m.steps == 500
    assert 0.0 <= m.scan_coverage <= 1.0
    assert 0.0 <= m.probability_of_detection <= 1.0
    assert m.emitter_events_total >= m.emitter_events_detected


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_health_endpoint():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["transmit_capability"] is False


def test_reset_creates_environment():
    r = client.post(
        "/api/simulation/reset",
        json={
            "environment": {"num_bands": 48, "num_time_slots": 500, "seed": 11},
            "scheduler": "round_robin",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["environment"]["num_bands"] == 48
    assert body["time_slot"] == 0
    assert len(body["emitters"]) > 0


def test_step_endpoint_advances_and_returns_json():
    client.post("/api/simulation/reset", json={"scheduler": "round_robin"})
    r = client.post("/api/simulation/step", json={"count": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["time_slot"] == 1
    assert body["last_step"]["decision"]["scheduler"] == "round_robin"


def test_run_endpoint_executes_many_steps():
    r = client.post(
        "/api/simulation/run",
        json={"steps": 250, "scheduler": "random", "reset": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["steps_executed"] == 250
    assert body["metrics"]["steps"] == 250


def test_state_endpoint_shape():
    client.post("/api/simulation/reset", json={"scheduler": "round_robin"})
    r = client.get("/api/state")
    assert r.status_code == 200
    body = r.json()
    for key in ("spectrum", "waterfall", "metrics", "emitters", "scan_path"):
        assert key in body
    assert len(body["spectrum"]["power_db"]) == body["environment"]["num_bands"]
