"""Step 5 verification: scenario presets, metric correctness, smart-vs-baseline."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.comparison.engine import compare_strategies
from app.main import app
from app.models.core import RFEnvironmentConfig, ReceiverConfig
from app.simulation.engine import Simulation
from app.simulation.environment import RFEnvironment
from app.simulation.presets import get_preset, list_presets, preset_names

client = TestClient(app)

EXPECTED_PRESETS = {
    "Sparse Environment",
    "Dense Emitter Environment",
    "Frequency Hopping Challenge",
    "Periodic Radar-Like Challenge",
    "High-Threat Low-Duty Challenge",
    "Noisy Spectrum Challenge",
}


# --------------------------------------------------------------------------- #
# Presets
# --------------------------------------------------------------------------- #
def test_all_six_presets_present_with_descriptions():
    presets = list_presets()
    assert {p["name"] for p in presets} == EXPECTED_PRESETS
    for p in presets:
        assert len(p["description"]) > 40
        assert p["environment"]["num_bands"] >= 4
        assert "detection_threshold_db" in p["receiver"]


@pytest.mark.parametrize("name", sorted(EXPECTED_PRESETS))
def test_each_preset_runs_without_crashing(name: str):
    env, rcv = get_preset(name)
    for sched in ("round_robin", "priority", "q_learning"):
        sim = Simulation(env, rcv, sched)
        sim.run(500)
        assert sim.metrics_snapshot().steps == 500


def test_behavior_weights_skew_emitter_mix():
    cfg = RFEnvironmentConfig(
        num_bands=64,
        num_time_slots=400,
        emitter_density=0.5,
        behavior_weights={"hopping": 1.0},
        seed=1,
    )
    env = RFEnvironment(cfg)
    behaviors = {e.behavior.value for e in env.emitters}
    assert behaviors == {"hopping"}


def test_api_presets_endpoint_and_apply():
    listing = client.get("/api/presets").json()["presets"]
    assert {p["name"] for p in listing} == EXPECTED_PRESETS

    r = client.post(
        "/api/simulation/reset",
        json={"preset": "Frequency Hopping Challenge", "scheduler": "priority"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["preset"] == "Frequency Hopping Challenge"
    assert body["environment"]["num_bands"] == 64
    assert body["scheduler"] == "priority"

    # a plain run keeps the preset active
    run = client.post("/api/simulation/run", json={"steps": 200, "reset": True})
    assert run.json()["preset"] == "Frequency Hopping Challenge"

    # explicit environment config clears the preset
    client.post("/api/simulation/reset", json={"environment": {"seed": 1234}})
    assert client.get("/api/state").json()["preset"] is None


def test_api_unknown_preset_is_400():
    r = client.post("/api/simulation/reset", json={"preset": "nope"})
    assert r.status_code == 400


def test_dataset_generate_from_preset():
    r = client.post(
        "/api/dataset/generate",
        json={"name": "preset-ds", "preset": "Periodic Radar-Like Challenge"},
    )
    assert r.status_code == 200
    ds_id = r.json()["dataset_id"]
    try:
        assert r.json()["number_of_bands"] == 48  # periodic preset uses 48 bands
        dist = r.json()["stats"]["emitter_type_distribution"]
        assert dist.get("periodic", 0) >= max(dist.values()) - 1  # periodic dominates
    finally:
        from app.dataset.store import get_store

        get_store().delete(ds_id)


# --------------------------------------------------------------------------- #
# Metric correctness — recompute from the raw history and compare
# --------------------------------------------------------------------------- #
def test_metric_denominators_match_definitions():
    sim = Simulation(
        RFEnvironmentConfig(num_bands=32, num_time_slots=800, seed=17),
        ReceiverConfig(),
        "priority",
    )
    sim.run(600)
    m = sim.metrics_snapshot()

    active_scans = inactive_scans = hits = false_alarms = 0
    visited: set[int] = set()
    visits: dict[int, list[int]] = {}
    for r in sim.history:
        b = r.decision.selected_band
        visited.add(b)
        visits.setdefault(b, []).append(r.time_slot)
        det = r.detection
        if det.true_active:
            active_scans += 1
            if det.detected:
                hits += 1
        else:
            inactive_scans += 1
            if det.false_alarm:
                false_alarms += 1

    # snapshot values are rounded to 4 dp in the tracker
    assert m.probability_of_detection == pytest.approx(hits / active_scans, abs=1e-3)
    assert m.false_alarm_rate == pytest.approx(false_alarms / inactive_scans, abs=1e-3)
    assert m.scan_coverage == pytest.approx(len(visited) / 32, abs=1e-3)

    gaps = [b - a for v in visits.values() if len(v) >= 2 for a, b in zip(v, v[1:])]
    assert m.average_revisit_time == pytest.approx(sum(gaps) / len(gaps), abs=1e-2)

    # interception ratio = detected events / events started by the final slot
    last_t = sim.history[-1].time_slot
    started = [e for e in sim.env.events if e.start <= last_t]
    detected = [e for e in started if e.detected]
    assert m.interception_ratio == pytest.approx(len(detected) / len(started), abs=1e-3)
    assert m.emitter_events_total == len(started)


def test_intercept_delay_is_start_to_first_detection():
    sim = Simulation(
        RFEnvironmentConfig(num_bands=24, num_time_slots=600, seed=5),
        ReceiverConfig(),
        "ucb_bandit",
    )
    sim.run(500)
    m = sim.metrics_snapshot()
    detected = [
        e for e in sim.env.events if e.detected and e.first_detection_slot is not None
    ]
    if detected:
        delays = [e.first_detection_slot - e.start for e in detected]
        assert all(d >= 0 for d in delays)
        assert m.average_intercept_delay == pytest.approx(
            sum(delays) / len(delays), abs=1e-3
        )


# --------------------------------------------------------------------------- #
# Smart schedulers outperform the baseline on tuned presets
# --------------------------------------------------------------------------- #
def _entry(report, name):
    return next(e for e in report.entries if e.scheduler == name)


def test_priority_beats_baseline_on_periodic_preset():
    env, rcv = get_preset("Periodic Radar-Like Challenge")
    rep = compare_strategies(
        env, rcv, ["round_robin", "random", "priority"], steps=800
    )
    pr = _entry(rep, "priority").metrics
    rr = _entry(rep, "round_robin").metrics
    rnd = _entry(rep, "random").metrics
    assert pr.average_reward > rr.average_reward
    assert pr.average_reward > rnd.average_reward
    assert rep.winner == "priority"


def test_smart_lifts_high_priority_detection_on_threat_preset():
    env, rcv = get_preset("High-Threat Low-Duty Challenge")
    rep = compare_strategies(
        env, rcv, ["round_robin", "priority", "q_learning"], steps=800
    )
    base = _entry(rep, "round_robin").metrics.high_priority_detection_rate
    best_smart = max(
        _entry(rep, s).metrics.high_priority_detection_rate
        for s in ("priority", "q_learning")
    )
    assert best_smart > base
    assert _entry(rep, "priority").metrics.average_reward > _entry(
        rep, "round_robin"
    ).metrics.average_reward


def test_smart_beats_baseline_reward_on_every_preset():
    scheds = ["round_robin", "random", "priority", "epsilon_bandit", "ucb_bandit"]
    for name in preset_names():
        env, rcv = get_preset(name)
        rep = compare_strategies(env, rcv, scheds, steps=600)
        best_base = max(
            _entry(rep, s).metrics.average_reward for s in ("round_robin", "random")
        )
        best_smart = max(
            _entry(rep, s).metrics.average_reward
            for s in ("priority", "epsilon_bandit", "ucb_bandit")
        )
        assert best_smart >= best_base, f"{name}: smart {best_smart} < base {best_base}"
