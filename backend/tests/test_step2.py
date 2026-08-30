"""Step 2 verification: smart schedulers, learning, explainability, training."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.core import RFEnvironmentConfig, ReceiverConfig
from app.schedulers.registry import (
    LEARNING_SCHEDULERS,
    SCHEDULER_REGISTRY,
    list_schedulers,
)
from app.simulation.engine import Simulation
from app.simulation.reward import RewardEngine

client = TestClient(app)

SMART = ["priority", "epsilon_bandit", "ucb_bandit", "thompson", "q_learning"]
ALL = ["round_robin", "random", *SMART]


def _sim(name: str, bands: int = 48, slots: int = 1000, seed: int = 7) -> Simulation:
    return Simulation(
        RFEnvironmentConfig(num_bands=bands, num_time_slots=slots, seed=seed),
        ReceiverConfig(),
        name,
    )


# --------------------------------------------------------------------------- #
def test_registry_exposes_all_six_plus_thompson():
    names = list_schedulers()
    for n in [
        "round_robin",
        "random",
        "priority",
        "epsilon_bandit",
        "ucb_bandit",
        "q_learning",
    ]:
        assert n in names
    assert "thompson" in names
    assert SCHEDULER_REGISTRY.keys() == set(names)


@pytest.mark.parametrize("name", ALL)
def test_every_scheduler_runs_500_steps(name: str):
    sim = _sim(name)
    results = sim.run(600)
    assert len(results) == 600
    assert all(0 <= r.decision.selected_band < 48 for r in results)
    m = sim.metrics_snapshot()
    assert m.steps == 600


@pytest.mark.parametrize("name", SMART)
def test_smart_schedulers_emit_explanations(name: str):
    sim = _sim(name)
    seen_reasons = 0
    for _ in range(120):
        d = sim.step().decision
        assert d.scheduler == name
        assert 0.0 <= d.confidence <= 1.0
        assert d.explanation
        assert len(d.reasons) <= 3
        assert len(d.alternatives) <= 3
        if d.reasons:
            seen_reasons += 1
    assert seen_reasons > 100


def test_reward_history_updates():
    sim = _sim("priority")
    sim.run(50)
    assert len(sim.reward_history) == 50
    assert any(r != 0 for r in sim.reward_history)


def test_learning_feedback_updates_counts():
    sim = _sim("epsilon_bandit")
    sim.run(300)
    assert sim.visit_counts.sum() == 300
    assert (sim.hit_counts + sim.miss_counts).sum() >= 1
    assert sim.last_visit_slot.max() >= 0


def test_bandit_values_move_from_init():
    sim = _sim("epsilon_bandit")
    sched = sim.scheduler
    before = sched.values.copy()
    sim.run(400)
    assert not np.allclose(before, sched.values)
    assert sched.counts.sum() == 400


def test_ucb_visits_every_band_before_repeating():
    sim = _sim("ucb_bandit", bands=32, slots=400)
    first = [sim.step().decision.selected_band for _ in range(32)]
    assert sorted(first) == list(range(32))


def test_priority_predictions_feed_correct_prediction_metric():
    sim = _sim("priority")
    sim.run(600)
    m = sim.metrics_snapshot()
    # Priority makes activity predictions, so the metric must be populated.
    assert m.correct_prediction_percentage > 0.0


def test_qlearning_trains_over_episodes():
    sim = _sim("q_learning", bands=24, slots=400)
    sched = sim.scheduler
    for ep in range(6):
        s = _sim("q_learning", bands=24, slots=400, seed=100 + ep)
        s.scheduler = sched  # reuse the learner
        s.run(400)
        sched.end_episode()
    assert sched.updates > 500
    assert len(sched.q) > 0
    assert sched.epsilon < 0.2  # decayed


def test_reward_engine_signs():
    eng = RewardEngine()
    r_hi, b_hi = eng.evaluate(
        true_active=True, detected=True, false_alarm=False, threat=0.9,
        retuned=False, predicted_active=True,
    )
    assert r_hi == 10.0 and "high_priority_detection" in b_hi
    r_fa, b_fa = eng.evaluate(
        true_active=False, detected=True, false_alarm=True, threat=0.0,
        retuned=False, predicted_active=None,
    )
    assert b_fa["false_alarm"] == -4.0 and r_fa < 0
    r_ok, b_ok = eng.evaluate(
        true_active=False, detected=False, false_alarm=False, threat=0.0,
        retuned=False, predicted_active=False,
    )
    assert b_ok["correct_inactive"] == 1.0


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", SMART)
def test_api_select_and_run_each_smart_scheduler(name: str):
    r = client.post(
        "/api/simulation/run",
        json={"steps": 300, "scheduler": name, "reset": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scheduler"] == name
    assert body["steps_executed"] == 300
    assert body["last_step"]["decision"]["scheduler"] == name


def test_api_schedulers_lists_learning_set():
    r = client.get("/api/schedulers")
    assert r.status_code == 200
    body = r.json()
    assert set(body["learning_schedulers"]) == LEARNING_SCHEDULERS


def test_api_train_endpoint_returns_episode_curve():
    r = client.post(
        "/api/simulation/train",
        json={
            "scheduler": "q_learning",
            "episodes": 5,
            "steps_per_episode": 300,
            "vary_seed": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["episode_results"]) == 5
    assert body["episode_results"][0]["episode"] == 1
    assert body["episode_results"][-1]["q_updates"] > 0
    assert "reward_improvement" in body
