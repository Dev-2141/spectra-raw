"""Extension Step 3: propagation, parametric emitters, simulated EW effects,
scenario store, Monte Carlo.

Default conftest principal override (admin) — behaviour tests, not auth tests.
"""

from __future__ import annotations

import sys

import numpy as np
from fastapi.testclient import TestClient

from app.comparison.montecarlo import run_montecarlo
from app.main import app
from app.models.core import (
    AntennaPattern,
    EmitterSpec,
    EWEffectSpec,
    Kinematics,
    RFEnvironmentConfig,
    ReceiverConfig,
    ScenarioSaveRequest,
)
from app.simulation import ew_effects as ew
from app.simulation import propagation as prop
from app.simulation.emitters import antenna_gain_db, emitter_doppler_hz, pri_pulse_times, received_snr_db
from app.simulation.engine import Simulation
from app.simulation.environment import RFEnvironment
from app.simulation.scenario import get_scenario_store

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Propagation
# --------------------------------------------------------------------------- #
def test_free_space_loss_monotonic_in_distance():
    losses = [prop.free_space_loss_db(d, 300.0) for d in (1, 5, 25, 100)]
    assert losses == sorted(losses)
    assert losses[-1] > losses[0]


def test_doppler_sign_matches_closing_geometry():
    assert prop.doppler_hz(+2.0, 300.0) > 0  # approaching
    assert prop.doppler_hz(-2.0, 300.0) < 0  # receding

    approaching = EmitterSpec(
        home_band=4, kinematics=Kinematics(kind="waypoint", x_km=60, y_km=0, x2_km=5, y2_km=0)
    )
    receding = EmitterSpec(
        home_band=4, kinematics=Kinematics(kind="waypoint", x_km=5, y_km=0, x2_km=60, y2_km=0)
    )
    assert emitter_doppler_hz(approaching, 100, 400, 300.0) > 0
    assert emitter_doppler_hz(receding, 100, 400, 300.0) < 0


def test_farther_mover_has_lower_received_snr():
    rng = np.random.default_rng(0)
    near = EmitterSpec(snr_db=20.0, kinematics=Kinematics(kind="waypoint", x_km=10, y_km=0, x2_km=10, y2_km=0))
    far = EmitterSpec(snr_db=20.0, kinematics=Kinematics(kind="waypoint", x_km=80, y_km=0, x2_km=80, y2_km=0))
    s_near = received_snr_db(near, 0, 100, rng, fading="none")
    s_far = received_snr_db(far, 0, 100, np.random.default_rng(0), fading="none")
    assert s_near > s_far


# --------------------------------------------------------------------------- #
# Parametric emitter model
# --------------------------------------------------------------------------- #
def test_stagger_pri_produces_expected_gaps():
    spec = EmitterSpec(
        duty="periodic", pri_model="stagger", pri_stagger=[10, 13, 11], period_slots=12,
        phase_slots=0, pulse_slots=1,
    )
    times = pri_pulse_times(spec, 80, np.random.default_rng(1))
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert gaps[:6] == [10, 13, 11, 10, 13, 11]


def test_rotating_antenna_gain_peaks_once_per_rotation():
    pat = AntennaPattern(kind="rotating", peak_gain_db=6.0, beamwidth_deg=40.0,
                         backlobe_db=-20.0, rotation_period_slots=24)
    assert antenna_gain_db(pat, 0) == 6.0          # boresight -> receiver
    assert antenna_gain_db(pat, 12) == 6.0 - 20.0  # pointing away
    # exactly one contiguous main-beam window per rotation period
    on = [antenna_gain_db(pat, t) == 6.0 for t in range(24)]
    edges = sum(1 for i in range(24) if on[i] and not on[i - 1])
    assert edges == 1


def test_parametric_environment_paints_activity():
    cfg = RFEnvironmentConfig(
        num_bands=24, num_time_slots=300, seed=7,
        emitter_specs=[
            EmitterSpec(id=1, home_band=5, duty="periodic", period_slots=15, pulse_slots=2, threat=0.9, snr_db=18),
            EmitterSpec(id=2, home_band=12, agility="list_hop", hop_bands=[12, 14, 16], hop_interval_slots=5, snr_db=16),
        ],
    )
    env = RFEnvironment(cfg)
    assert len(env.emitters) == 2
    assert env.occupancy.any()
    assert env.occupancy[:, 5].any()          # periodic emitter's home band
    assert env.occupancy[:, [12, 14, 16]].any()  # hopper touched its list


# --------------------------------------------------------------------------- #
# Simulated EW effects
# --------------------------------------------------------------------------- #
def test_ew_effects_module_does_not_touch_hardware():
    import ast

    tree = ast.parse(__import__("inspect").getsource(ew))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any("hardware" in m for m in imported), imported
    assert "hardware" not in {n for n in dir(ew) if not n.startswith("_")}


def test_spot_jam_degrades_observation_but_not_ground_truth():
    cfg = RFEnvironmentConfig(num_bands=16, num_time_slots=200, seed=3, emitter_density=0.3)
    env = RFEnvironment(cfg)
    truth_before = env.occupancy.copy()
    snr_truth_before = env.snr_db.copy()

    env.apply_ew_effects([
        EWEffectSpec(kind="spot_jam", band_lo=6, band_hi=6, start_slot=0, stop_slot=199, power_db=25.0)
    ])

    # ground truth untouched
    assert np.array_equal(env.occupancy_truth, truth_before)
    assert np.allclose(env.snr_truth, snr_truth_before)
    # observation on the jammed band is degraded + flagged synthetic
    assert env.is_synthetic_effect[:, 6].all()
    assert env.occupancy_observed[:, 6].all()
    assert (env.snr_observed[:, 6] < env.snr_truth[:, 6] + 1e-6).all()
    assert (env.noise_floor_map[:, 6] > env.noise_floor_db).all()


def test_spoof_track_creates_observed_activity_where_truth_is_idle():
    cfg = RFEnvironmentConfig(num_bands=20, num_time_slots=300, seed=9, emitter_density=0.0)
    env = RFEnvironment(cfg)
    env.apply_ew_effects([
        EWEffectSpec(kind="spoof_track", band_lo=8, target_band=8, start_slot=0, stop_slot=299,
                     spoof_period_slots=12, spoof_pulse_slots=2, spoof_snr_db=14.0)
    ])
    assert not env.occupancy_truth[:, 8].any()      # nothing real there
    assert env.occupancy_observed[:, 8].any()        # but the receiver would see pulses
    assert env.is_synthetic_effect[:, 8].any()


def test_simulation_reports_effect_counters_and_stays_truth_scored():
    cfg = RFEnvironmentConfig(num_bands=32, num_time_slots=600, seed=11, emitter_density=0.25)
    effects = [
        EWEffectSpec(kind="barrage_noise", band_lo=4, band_hi=14, start_slot=0, stop_slot=600, power_db=12.0),
        EWEffectSpec(kind="spoof_track", band_lo=20, target_band=20, start_slot=0, stop_slot=600,
                     spoof_period_slots=9, spoof_pulse_slots=2, spoof_snr_db=13.0),
    ]
    sim = Simulation(cfg, ReceiverConfig(), "round_robin", ew_effects=effects)
    sim.run(500)
    em = sim.effect_metrics()
    assert em["has_effects"] is True
    assert em["detection_under_effect_n"] >= 0
    assert em["spoof_deception_count"] >= 0
    assert len(em["effect_labels"]) == 2
    # metrics still computed against ground truth -> all in range
    m = sim.metrics_snapshot()
    assert 0.0 <= m.probability_of_detection <= 1.0
    assert 0.0 <= m.scan_coverage <= 1.0


# --------------------------------------------------------------------------- #
# Scenario store
# --------------------------------------------------------------------------- #
def test_builtin_scenarios_include_ew_presets():
    names = {s.name for s in get_scenario_store().list()}
    assert {"Jammed Spectrum", "Spoofed Track"} <= names
    assert "Sparse Environment" in names  # legacy preset re-exposed


def test_scenario_save_roundtrip_is_reproducible():
    store = get_scenario_store()
    req = ScenarioSaveRequest(
        name="rt-test",
        environment=RFEnvironmentConfig(num_bands=24, num_time_slots=400, seed=123),
        receiver=ReceiverConfig(detection_threshold_db=6.0),
        effects=[EWEffectSpec(kind="spot_jam", band_lo=3, band_hi=3, power_db=20.0)],
    )
    saved = store.save(req)
    try:
        reloaded = store.get(saved.scenario_id)
        assert reloaded.model_dump() == saved.model_dump()

        def run(scn):
            sim = Simulation(scn.environment, scn.receiver, "priority",
                             ew_effects=[e for e in scn.effects])
            sim.run(300)
            return sim.metrics_snapshot().model_dump()

        assert run(saved) == run(reloaded)
    finally:
        store.delete(saved.scenario_id)


def test_cannot_edit_or_delete_builtin_scenario():
    store = get_scenario_store()
    try:
        store.delete("builtin:Jammed Spectrum")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


# --------------------------------------------------------------------------- #
# Monte Carlo
# --------------------------------------------------------------------------- #
def _mc(seeds):
    return run_montecarlo(
        environment=RFEnvironmentConfig(num_bands=24, num_time_slots=400),
        receiver=ReceiverConfig(),
        effects=[],
        schedulers=["round_robin", "priority"],
        seeds=seeds,
        steps=200,
    )


def test_montecarlo_is_deterministic_for_a_seed_set():
    a = _mc([1, 2, 3, 4])
    b = _mc([1, 2, 3, 4])
    assert a.montecarlo_id == b.montecarlo_id  # cache hit
    assert [e.model_dump() for e in a.entries] == [e.model_dump() for e in b.entries]
    for e in a.entries:
        for agg in e.aggregates:
            assert agg.n == 4
            assert agg.ci95_low <= agg.mean <= agg.ci95_high
            assert agg.std >= 0.0
    assert abs(sum(e.win_rate for e in a.entries) - 1.0) < 1e-6


def test_montecarlo_ci_tightens_with_more_seeds():
    def reward_ci_width(rep):
        e = next(e for e in rep.entries if e.scheduler == "priority")
        a = next(a for a in e.aggregates if a.metric == "average_reward")
        return a.ci95_high - a.ci95_low

    narrow = reward_ci_width(_mc(list(range(100, 116))))  # 16 seeds
    wide = reward_ci_width(_mc(list(range(200, 204))))    # 4 seeds
    assert narrow <= wide + 1e-9


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def _h():
    return {"Authorization": "Bearer test"}


def test_scenario_load_and_montecarlo_via_api():
    scn = client.get("/api/scenario", headers=_h()).json()["scenarios"]
    jammed = next(s for s in scn if s["name"] == "Jammed Spectrum")

    loaded = client.post(
        f"/api/scenario/{jammed['scenario_id']}/load", headers=_h()
    )
    assert loaded.status_code == 200, loaded.text
    body = loaded.json()
    assert body["scenario"] == "Jammed Spectrum"
    assert body["effects"]["has_effects"] is True

    st = client.post("/api/simulation/step", json={"count": 50}, headers=_h()).json()
    assert st["effects"]["has_effects"] is True
    assert "synthetic_effect" in st["waterfall"]

    mc = client.post(
        "/api/montecarlo/run",
        json={
            "scenario_id": jammed["scenario_id"],
            "schedulers": ["round_robin", "priority"],
            "n_seeds": 4,
            "steps": 150,
        },
        headers=_h(),
    )
    assert mc.status_code == 200, mc.text
    rep = mc.json()
    assert len(rep["entries"]) == 2
    assert rep["winner"] in ("round_robin", "priority")
    assert set(rep["ranking"]) == {"round_robin", "priority"}

    got = client.get(f"/api/montecarlo/{rep['montecarlo_id']}", headers=_h())
    assert got.status_code == 200
    csv = client.get(
        f"/api/montecarlo/{rep['montecarlo_id']}/export/csv", headers=_h()
    )
    assert csv.status_code == 200 and "average_reward" in csv.text

    # restore to a clean preset so later tests are unaffected
    client.post("/api/simulation/reset", json={"preset": "Sparse Environment"}, headers=_h())


def test_scenario_duplicate_then_delete_via_api():
    dup = client.post(
        "/api/scenario/builtin:Sparse Environment/duplicate", headers=_h()
    )
    assert dup.status_code == 200, dup.text
    new_id = dup.json()["scenario_id"]
    assert dup.json()["builtin"] is False
    try:
        assert client.get(f"/api/scenario/{new_id}", headers=_h()).status_code == 200
    finally:
        d = client.delete(f"/api/scenario/{new_id}", headers=_h())
        assert d.status_code == 200
