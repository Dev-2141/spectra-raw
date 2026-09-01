"""Extension Step 6: DRL / bandit schedulers, online learning, sim-to-real,
explainability++."""

from __future__ import annotations

import json
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.core import SweepFrame
from app.schedulers.registry import (
    available_schedulers,
    create_scheduler,
    list_schedulers,
    scheduler_requirements,
)
from app.simulation.engine import Simulation
from app.simulation.presets import get_preset

client = TestClient(app)


def _h():
    return {"Authorization": "Bearer test"}


# --------------------------------------------------------------------------- #
# contextual_bandit (no torch)
# --------------------------------------------------------------------------- #
def test_contextual_bandit_beats_random_and_runs_1000_steps():
    env, rcv = get_preset("Dense Emitter Environment")
    env = env.model_copy(update={"num_time_slots": 1300})

    def avg_reward(name: str) -> float:
        sim = Simulation(env, rcv, name)
        sim.run(1200)
        return sim.metrics_snapshot().average_reward

    cb = avg_reward("contextual_bandit")
    rnd = avg_reward("random")
    assert cb > rnd, (cb, rnd)


def test_contextual_bandit_checkpoint_roundtrip():
    env, rcv = get_preset("Sparse Environment")
    s1 = create_scheduler("contextual_bandit", env.num_bands, np.random.default_rng(1), {})
    sim = Simulation(env, rcv, "contextual_bandit", scheduler_instance=s1)
    sim.run(300)
    sd = s1.state_dict()
    blob = json.loads(json.dumps(sd))  # must be JSON-serialisable

    s2 = create_scheduler("contextual_bandit", env.num_bands, np.random.default_rng(2), {})
    s2.load_state_dict(blob)
    assert np.allclose(np.array(s1.A), np.array(s2.A))
    assert np.allclose(np.array(s1.b), np.array(s2.b))


# --------------------------------------------------------------------------- #
# torch gating
# --------------------------------------------------------------------------- #
def test_torch_schedulers_registered_but_gated_without_torch():
    names = set(list_schedulers())
    assert {"contextual_bandit", "dqn", "drqn"} <= names

    reqs = scheduler_requirements()
    assert reqs["contextual_bandit"] == []
    # torch is not installed in this environment
    assert reqs["dqn"] == ["torch"] and reqs["drqn"] == ["torch"]
    assert "dqn" not in available_schedulers()
    assert "contextual_bandit" in available_schedulers()

    with pytest.raises(ValueError, match="requires PyTorch"):
        create_scheduler("dqn", 16, np.random.default_rng(0), {})

    r = client.post("/api/simulation/reset", json={"scheduler": "dqn"}, headers=_h())
    assert r.status_code == 400 and "PyTorch" in r.json()["detail"]

    # nothing else broke
    ok = client.post("/api/simulation/reset", json={"scheduler": "priority"}, headers=_h())
    assert ok.status_code == 200

    sc = client.get("/api/schedulers", headers=_h()).json()
    assert "contextual_bandit" in sc["schedulers"]
    assert sc["requirements"]["dqn"] == ["torch"]


# --------------------------------------------------------------------------- #
# Online learning guardrail
# --------------------------------------------------------------------------- #
def test_online_guardrail_auto_reverts_a_bad_policy():
    from app.alerting.engine import _reset_for_tests as reset_alerts
    from app.rl.online import _reset_for_tests as reset_online

    reset_online()
    reset_alerts()
    client.post(
        "/api/simulation/reset",
        json={"environment": {"num_bands": 24, "num_time_slots": 4000, "seed": 7,
                              "emitter_density": 0.35},
              "scheduler": "round_robin"},
        headers=_h(),
    )
    r = client.post(
        "/api/online/enable",
        json={"scheduler": "random", "margin": 0.5, "window": 40},
        headers=_h(),
    )
    assert r.status_code == 200 and r.json()["enabled"] is True

    for _ in range(8):
        client.post("/api/simulation/step", json={"count": 100}, headers=_h())

    st = client.get("/api/online/status", headers=_h()).json()
    assert st["reverted"] is True
    assert st["reverted_at_slot"] is not None
    assert st["policy_reward_ema"] < st["shadow_reward_ema"]

    assert client.get("/api/state", headers=_h()).json()["scheduler"] == "priority"

    alerts = client.get("/api/alerts", headers=_h()).json()["alerts"]
    assert any(a["rule_kind"] == "online_guardrail" for a in alerts)
    aud = client.get(
        "/api/audit?action=online.guardrail.revert", headers=_h()
    ).json()["entries"]
    assert len(aud) >= 1

    client.post("/api/online/disable", headers=_h())
    reset_online()
    reset_alerts()


def test_online_guardrail_holds_a_good_policy():
    from app.rl.online import OnlineGuardrail

    g = OnlineGuardrail(margin=1.0, window=40)
    rng = np.random.default_rng(0)
    for t in range(400):
        # policy consistently a bit better than shadow
        g.observe(t, 2.0 + rng.normal(0, 0.2), 1.0 + rng.normal(0, 0.2))
    assert not g.reverted


# --------------------------------------------------------------------------- #
# Sim-to-real
# --------------------------------------------------------------------------- #
def _write_recording(n_frames: int, tone: range) -> str:
    from app.hardware.recordings import recordings_dir

    rid = f"s2r{int(time.time() * 1000) % 100000}"
    d = recordings_dir() / rid
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "frames.jsonl", "w", encoding="utf-8") as fh:
        for i in range(n_frames):
            power = np.full(200, -96.0)
            power[list(tone)] = -45.0
            fr = SweepFrame(ts=i * 0.1, seq=i, f_start_hz=88e6, f_stop_hz=108e6,
                            bin_hz=1e5, power_dbm=[float(x) for x in power], source="s2r")
            fh.write(fr.model_dump_json() + "\n")
    (d / "meta.json").write_text(json.dumps({
        "recording_id": rid, "created_at": "2026-01-01T00:00:00Z", "name": "s2r",
        "source": "s2r", "device_label": None, "start_freq_hz": 88e6,
        "stop_freq_hz": 108e6, "bin_hz": 1e5, "frame_count": n_frames,
        "duration_s": n_frames * 0.1, "first_frame_ts": 0.0,
        "last_frame_ts": n_frames * 0.1}), "utf-8")
    return rid


def test_sim2real_gap_small_when_calibrated_and_grows_with_mismatch():
    from app.sim2real.calibrate import calibrate
    from app.sim2real.gap import compute_gap

    rid = _write_recording(40, range(90, 110))
    profile = calibrate(rid, "unit-cal")
    assert profile.synthetic if hasattr(profile, "synthetic") else True
    assert profile.num_bands == 48

    g0 = compute_gap(rid, profile.profile_id, "priority", 300, noise_shift_db=0.0)
    g1 = compute_gap(rid, profile.profile_id, "priority", 300, noise_shift_db=12.0)
    g2 = compute_gap(rid, profile.profile_id, "priority", 300, noise_shift_db=24.0)

    assert g0.gap_score < 0.6
    assert g0.gap_score <= g1.gap_score + 1e-6
    assert g1.gap_score <= g2.gap_score + 1e-6
    assert g2.gap_score > g0.gap_score
    assert {m.metric for m in g0.metrics} >= {"occupancy_rate", "mean_snr_db"}
    assert isinstance(g2.narrative, str) and g2.narrative


def test_sim2real_api_flow():
    rid = _write_recording(30, range(95, 105))
    cal = client.post(
        "/api/sim2real/calibrate", json={"recording_id": rid, "name": "api-cal"}, headers=_h()
    )
    assert cal.status_code == 200, cal.text
    pid = cal.json()["profile_id"]

    profs = client.get("/api/sim2real/profiles", headers=_h()).json()["profiles"]
    assert any(p["profile_id"] == pid for p in profs)

    gap = client.post(
        "/api/sim2real/gap",
        json={"recording_id": rid, "profile_id": pid, "scheduler": "priority", "steps": 200},
        headers=_h(),
    )
    assert gap.status_code == 200
    assert "gap_score" in gap.json() and "metrics" in gap.json()


# --------------------------------------------------------------------------- #
# Explainability++ : counterfactual flip
# --------------------------------------------------------------------------- #
def _nudge(ctx, factor: str, band: int) -> None:
    n = ctx.num_bands
    others = np.arange(n) != band
    if factor == "threat":
        ctx.band_threat_prior = ctx.band_threat_prior.copy()
        ctx.band_threat_prior[band] += 20.0
    elif factor == "activity":
        ctx.predicted_activity = ctx.predicted_activity.copy()
        ctx.predicted_activity[band] = 20.0
    elif factor == "hit_rate":
        ctx.hit_counts = ctx.hit_counts.copy()
        ctx.visit_counts = ctx.visit_counts.copy()
        ctx.hit_counts[band] = 200
        ctx.visit_counts[band] = 200
    elif factor == "uncertainty":
        ctx.visit_counts = ctx.visit_counts.copy()
        ctx.visit_counts[band] = 0
        ctx.visit_counts[others] = 2000
    elif factor == "staleness":
        ctx.last_visit_slot = ctx.last_visit_slot.copy()
        ctx.last_visit_slot[band] = -1
        ctx.last_visit_slot[others] = ctx.time_slot
    elif factor == "tasking":
        tw = np.ones(n)
        tw[band] = 20.0
        ctx.tasking_weights = tw
    elif factor == "periodicity":
        pytest.skip("periodicity is internal scheduler state, not a context input")


def test_priority_counterfactual_flip_factor_actually_flips_the_choice():
    env, rcv = get_preset("Dense Emitter Environment")
    sim = Simulation(env, rcv, "priority")
    sim.run(6)  # a few steps so threat/activity dominate, no learned periodicity yet
    ctx = sim._context()

    d = sim.scheduler.decide(ctx)
    cf = d.counterfactual
    assert cf is not None
    assert cf["flip_factor"] in (
        "activity", "staleness", "uncertainty", "threat", "hit_rate",
        "periodicity", "tasking",
    )
    assert cf["margin"] >= 0.0

    _nudge(ctx, cf["flip_factor"], cf["alt_band"])
    d2 = sim.scheduler.decide(ctx)
    assert d2.selected_band == cf["alt_band"], (cf, d2.selected_band)


def test_contextual_bandit_emits_counterfactual_and_policy_grid():
    env, rcv = get_preset("Sparse Environment")
    sim = Simulation(env, rcv, "contextual_bandit")
    sim.run(120)
    ctx = sim._context()
    d = sim.scheduler.decide(ctx)
    assert d.counterfactual is not None
    from app.schedulers.learning import FEATURE_NAMES

    assert d.counterfactual["flip_factor"] in FEATURE_NAMES

    grid = sim.scheduler.policy_attribution(ctx)
    assert grid["features"] == FEATURE_NAMES
    assert len(grid["grid"]) == len(FEATURE_NAMES)
    assert len(grid["grid"][0]) == env.num_bands


def test_explain_policy_endpoint():
    client.post("/api/simulation/reset", json={"scheduler": "priority"}, headers=_h())
    client.post("/api/simulation/step", json={"count": 40}, headers=_h())
    r = client.get("/api/explain/policy", headers=_h()).json()
    assert r["available"] is True
    assert "grid" in r and "features" in r and "scores" in r
    assert len(r["scores"]) > 0
