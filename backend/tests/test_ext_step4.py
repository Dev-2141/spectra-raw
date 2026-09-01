"""Extension Step 4: features, classifier, tracks, library, tasking, alerting."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.analysis.classify import classify_features
from app.analysis.features import extract_features, runs_from_occupancy
from app.analysis.tracks import extract_tracks
from app.library.store import _reset_for_tests as reset_lib
from app.library.store import get_library, match_features
from app.main import app
from app.models.core import EmitterSpec, LibraryEntrySaveRequest, RFEnvironmentConfig, ReceiverConfig
from app.simulation.engine import Simulation
from app.simulation.environment import RFEnvironment

client = TestClient(app)


def _h():
    return {"Authorization": "Bearer test"}


# --------------------------------------------------------------------------- #
# Features
# --------------------------------------------------------------------------- #
def test_stagger_pri_and_jitter_recovered():
    # pulse starts with stagger gaps 10, 13, 11 repeating
    starts = [0, 10, 23, 34, 44, 57, 68, 78]
    runs = {5: [(s, s + 1) for s in starts]}
    f = extract_features(runs, {5: 15.0})
    assert 10.0 <= f.pri_estimate <= 13.0
    assert f.pri_jitter < 0.25
    assert f.hop_pattern == "fixed"
    assert f.n_bands == 1


def test_hopper_features_show_band_movement():
    runs = {
        5: [(0, 3)], 6: [(6, 9)], 7: [(12, 15)], 8: [(18, 21)], 7: [(24, 27)],  # noqa: F601
    }
    runs = {5: [(0, 3)], 6: [(6, 9)], 7: [(12, 15), (24, 27)], 8: [(18, 21)]}
    f = extract_features(runs, {b: 12.0 for b in runs})
    assert f.n_bands == 4
    assert f.hop_rate > 0
    assert f.hop_pattern in ("sweep", "list", "random")


# --------------------------------------------------------------------------- #
# Classifier
# --------------------------------------------------------------------------- #
def _features_for(spec: EmitterSpec, seed: int):
    cfg = RFEnvironmentConfig(num_bands=32, num_time_slots=360, seed=seed, emitter_specs=[spec])
    env = RFEnvironment(cfg)
    runs = runs_from_occupancy(env.occupancy, env.num_time_slots - 1)
    return extract_features(runs, {b: float(env.snr_db[:, b].max()) for b in runs})


def test_classifier_probabilities_and_unknown_flag():
    f = _features_for(
        EmitterSpec(home_band=8, duty="periodic", period_slots=16, pulse_slots=2, snr_db=18),
        seed=555,
    )
    res = classify_features(f.vector())
    assert abs(sum(res["probabilities"].values()) - 1.0) < 1e-6
    assert isinstance(res["is_unknown"], bool)
    assert res["modulation"] == "unknown"

    # a degenerate near-empty track -> low confidence / unknown-ish
    empty = classify_features([1, 0.01, 0.0, 0.0, 0.0, 1, 1.0, 0.01, 3.0, 1])
    assert 0.0 <= empty["confidence"] <= 1.0


def test_classifier_beats_chance_on_held_out_synthetic():
    cases = [
        ("constant", EmitterSpec(home_band=6, duty="blocks", period_slots=50, snr_db=18)),
        ("periodic", EmitterSpec(home_band=9, duty="periodic", period_slots=14, pulse_slots=2, snr_db=18)),
        ("low_duty", EmitterSpec(home_band=11, duty="low_duty", snr_db=17)),
        ("hopping", EmitterSpec(home_band=10, agility="sweep", hop_interval_slots=5,
                                sweep_span_bands=8, duty="blocks", period_slots=10, snr_db=18)),
        ("burst", EmitterSpec(home_band=14, duty="bursts", snr_db=17)),
    ]
    correct = 0
    for label, spec in cases:
        for k in range(2):
            res = classify_features(_features_for(spec, seed=7000 + hash(label) % 500 + k).vector())
            if res["class"] == label:
                correct += 1
    assert correct >= 5  # >> chance (1/6 * 10 ~= 1.7)


# --------------------------------------------------------------------------- #
# Tracks
# --------------------------------------------------------------------------- #
class _StubEnv:
    def __init__(self, occ: np.ndarray):
        self.occupancy = occ
        self.occupancy_observed = occ
        self.snr_db = np.where(occ, 15.0, 0.0).astype(np.float32)
        self.snr_observed = self.snr_db
        self.threat = np.where(occ, 0.4, 0.0).astype(np.float32)
        self.is_synthetic_effect = None
        self.num_time_slots = occ.shape[0]


def test_small_gap_is_one_track_large_gap_is_two():
    occ = np.zeros((120, 8), dtype=bool)
    occ[0:5, 3] = True
    occ[12:17, 3] = True          # gap 7 < GAP_TOL -> same track
    occ[80:85, 3] = True          # gap 63 -> new track
    tracks = extract_tracks(_StubEnv(occ), 119)
    assert len(tracks) == 2
    assert tracks[0].run_count + tracks[1].run_count == 3


def test_frequency_step_keeps_track_id():
    occ = np.zeros((120, 12), dtype=bool)
    occ[0:4, 4] = True
    occ[8:12, 6] = True           # +2 bands within band_tol, gap 4 within gap_tol
    occ[16:20, 5] = True
    tracks = extract_tracks(_StubEnv(occ), 119)
    assert len(tracks) == 1
    tr = tracks[0]
    assert tr.track_id == "trk-00000-004"   # id from earliest run
    assert set(tr.bands) == {4, 5, 6}
    assert tr.features.n_bands == 3


# --------------------------------------------------------------------------- #
# Library
# --------------------------------------------------------------------------- #
def test_library_seeded_and_matching_prefers_the_right_entry():
    lib = get_library()
    entries = lib.list()
    assert len(entries) >= 5
    assert all(e.synthetic for e in entries)

    # a hopper-shaped feature set should match the seeded hopper best
    occ = np.zeros((200, 40), dtype=bool)
    for i, b in enumerate(range(28, 36)):
        occ[i * 20 : i * 20 + 8, b] = True
    tr = extract_tracks(_StubEnv(occ), 199, library_entries=entries)[0]
    top = tr.library_matches[0]
    assert top["behavior"] == "hopping"


def test_library_versioning_and_delete_retains_history():
    reset_lib()
    lib = get_library()
    e = lib.create(LibraryEntrySaveRequest(name="ut-entry", behavior="periodic", pri_slots=12), actor="tester")
    lib.update(e.entry_id, LibraryEntrySaveRequest(name="ut-entry", behavior="periodic", pri_slots=20), actor="tester")
    revs = lib.revisions(e.entry_id)
    assert [r.action for r in revs] == ["create", "update"]
    assert revs[-1].revision == 2

    lib.delete(e.entry_id, actor="tester")
    with pytest.raises(KeyError):
        lib.get(e.entry_id)
    actions = [r.action for r in lib.revisions(e.entry_id)]
    assert actions == ["create", "update", "delete"]
    reset_lib()


def test_library_create_via_api_is_audited():
    r = client.post(
        "/api/library",
        json={"name": "api-entry", "behavior": "burst", "threat": 0.5},
        headers=_h(),
    )
    assert r.status_code == 200, r.text
    eid = r.json()["entry_id"]
    assert r.json()["synthetic"] is True
    try:
        aud = client.get("/api/audit?action=library.create", headers=_h()).json()["entries"]
        assert any(a["target"] == eid for a in aud)
    finally:
        client.delete(f"/api/library/{eid}", headers=_h())


# --------------------------------------------------------------------------- #
# Tasking weights feed the priority scheduler
# --------------------------------------------------------------------------- #
def test_watchlist_weights_bias_the_priority_scheduler():
    from app.tasking.state import get_tasking_state, _reset_for_tests as reset_tasking
    from app.models.core import WatchList

    reset_tasking()
    ts = get_tasking_state()
    cfg = RFEnvironmentConfig(num_bands=24, num_time_slots=600, seed=4, emitter_density=0.25)

    base = Simulation(cfg, ReceiverConfig(), "priority")
    base.run(400)
    base_visits = base.visit_counts.copy()

    ts.set_watch_lists([WatchList(name="w", band_lo=10, band_hi=12, weight=4.0)])
    weighted = Simulation(
        cfg, ReceiverConfig(), "priority",
        tasking_weights=ts.band_weights(cfg.num_bands),
    )
    weighted.run(400)

    watched = slice(10, 13)
    assert weighted.visit_counts[watched].sum() > base_visits[watched].sum()
    reset_tasking()


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #
def test_new_emitter_alert_fires_once_then_ack_close_lifecycle():
    from app.alerting.engine import _reset_for_tests as reset_alerts

    reset_alerts()
    # a scenario with clear emitters so tracks appear
    client.post(
        "/api/simulation/reset",
        json={
            "environment": {"num_bands": 24, "num_time_slots": 500, "seed": 6, "emitter_density": 0.3},
            "scheduler": "round_robin",
        },
        headers=_h(),
    )
    client.post("/api/simulation/step", json={"count": 220}, headers=_h())

    first = client.get("/api/alerts", headers=_h()).json()
    new_emitter = [a for a in first["alerts"] if a["rule_kind"] == "new_emitter"]
    assert len(new_emitter) >= 1
    n1 = len(new_emitter)

    # pulling again must not duplicate new_emitter alerts for the same tracks
    second = client.get("/api/alerts", headers=_h()).json()["alerts"]
    assert len([a for a in second if a["rule_kind"] == "new_emitter"]) == n1

    alert_id = new_emitter[0]["alert_id"]
    acked = client.post(f"/api/alerts/{alert_id}/ack", headers=_h())
    assert acked.status_code == 200 and acked.json()["state"] == "ack"
    closed = client.post(f"/api/alerts/{alert_id}/close", headers=_h())
    assert closed.json()["state"] == "closed"

    aud = client.get("/api/audit?action=alert.*", headers=_h()).json()["entries"]
    assert {"alert.ack", "alert.close"} <= {a["action"] for a in aud}
    reset_alerts()


def test_tracks_anomaly_forecast_endpoints_shape():
    client.post(
        "/api/simulation/reset",
        json={"environment": {"num_bands": 32, "num_time_slots": 800, "seed": 3,
                              "behavior_weights": {"periodic": 0.8, "constant": 0.2}},
              "scheduler": "priority"},
        headers=_h(),
    )
    client.post("/api/simulation/step", json={"count": 400}, headers=_h())

    tr = client.get("/api/tracks", headers=_h()).json()
    assert "tracks" in tr and isinstance(tr["tracks"], list)
    if tr["tracks"]:
        row = tr["tracks"][0]
        for k in ("track_id", "class", "class_confidence", "library_matches", "features"):
            assert k in row
        one = client.get(f"/api/tracks/{row['track_id']}", headers=_h())
        assert one.status_code == 200

    an = client.get("/api/anomaly", headers=_h()).json()
    assert "flags" in an and "anomalous_bands" in an

    fc = client.get("/api/forecast", headers=_h()).json()
    assert "forecast" in fc
