"""Extension Step 5: multi-node direction finding / geolocation."""

from __future__ import annotations

import ast
import inspect

import numpy as np
from fastapi.testclient import TestClient

from app.df import engine as df_engine
from app.df import solvers as df_solvers
from app.df.fusion import GeoFusion
from app.df.geometry import bearing_deg, toa_seconds
from app.df.nodes import _reset_for_tests as reset_nodes
from app.df.solvers import ellipse_from_cov, fuse_estimates, solve_aoa, solve_tdoa
from app.main import app

client = TestClient(app)

C_KMS = 299_792.458


def _h():
    return {"Authorization": "Bearer test"}


# --------------------------------------------------------------------------- #
# TDOA
# --------------------------------------------------------------------------- #
_NODES = np.array([[40.0, 40.0], [-40.0, 40.0], [-40.0, -40.0], [40.0, -40.0]])


def _true_toa(emitter, nodes=_NODES):
    return np.array([toa_seconds(nodes[i], emitter) for i in range(len(nodes))])


def test_tdoa_recovers_position_with_zero_noise():
    truth = np.array([12.0, -7.0])
    toa = _true_toa(truth)
    sig = np.full(4, 1e-12)
    pos, cov, ok = solve_tdoa(_NODES, toa, sig)
    assert ok
    assert np.linalg.norm(pos - truth) < 1e-2


def test_tdoa_95pct_ellipse_contains_truth():
    truth = np.array([9.0, 4.0])
    sigma_s = 30e-9
    rng = np.random.default_rng(0)
    inside = 0
    trials = 300
    for _ in range(trials):
        toa = _true_toa(truth) + rng.normal(0.0, sigma_s, size=4)
        pos, cov, ok = solve_tdoa(_NODES, toa, np.full(4, sigma_s))
        if not ok:
            continue
        d = truth - pos
        m2 = float(d @ np.linalg.solve(cov, d))
        if m2 <= 5.991:
            inside += 1
    assert inside / trials >= 0.85, inside / trials


def test_tdoa_needs_three_nodes():
    pos, cov, ok = solve_tdoa(_NODES[:2], _true_toa(np.array([1.0, 1.0]))[:2], np.full(2, 1e-9))
    assert not ok


# --------------------------------------------------------------------------- #
# AOA
# --------------------------------------------------------------------------- #
def test_aoa_two_clean_bearings_intersect_correctly():
    truth = np.array([15.0, -8.0])
    nodes = np.array([[0.0, 0.0], [30.0, 0.0]])
    brg = np.array([bearing_deg(nodes[0], truth), bearing_deg(nodes[1], truth)])
    pos, cov, ok = solve_aoa(nodes, brg, np.full(2, 0.01))
    assert ok
    assert np.linalg.norm(pos - truth) < 0.2


def test_aoa_parallel_bearings_flagged_unsolvable_no_crash():
    nodes = np.array([[0.0, 0.0], [0.0, 20.0]])
    pos, cov, ok = solve_aoa(nodes, np.array([90.0, 90.0]), np.full(2, 1.0))
    assert not ok
    assert not np.all(np.isfinite(pos)) or not np.all(np.isfinite(cov))


# --------------------------------------------------------------------------- #
# Sync degradation
# --------------------------------------------------------------------------- #
def test_worse_timing_error_grows_the_ellipse_monotonically():
    truth = np.array([5.0, 5.0])
    toa = _true_toa(truth)
    areas = []
    for sig_ns in (10, 30, 100, 300):
        s = sig_ns * 1e-9
        _, cov, ok = solve_tdoa(_NODES, toa, np.full(4, s))
        assert ok
        a, b, _ = ellipse_from_cov(cov)
        areas.append(a * b)
    assert areas == sorted(areas)
    assert areas[-1] > areas[0] * 4


# --------------------------------------------------------------------------- #
# Fusion over time (mover)
# --------------------------------------------------------------------------- #
def test_geofusion_tracks_a_mover_with_bounded_lag():
    fuse = GeoFusion(process_km_per_update=0.8)
    rng = np.random.default_rng(3)
    R = np.eye(2) * 0.25
    final = None
    for k in range(60):
        true = np.array([0.5 * k, 0.0])          # moves +0.5 km/update
        z = true + rng.normal(0.0, 0.4, size=2)
        est, _ = fuse.update(z, R, k)
        final = (est, true)
    est, true = final
    assert np.linalg.norm(est - true) < 3.0       # keeps up
    assert len(fuse.history) == 60


def test_fuse_estimates_information_form():
    a = (np.array([0.0, 0.0]), np.eye(2) * 4.0, True)
    b = (np.array([2.0, 0.0]), np.eye(2) * 4.0, True)
    pos, cov, ok = fuse_estimates(a, b)
    assert ok
    assert np.allclose(pos, [1.0, 0.0])           # equal weight -> midpoint
    assert cov[0, 0] < 4.0                         # fused is tighter


# --------------------------------------------------------------------------- #
# Offline guarantee
# --------------------------------------------------------------------------- #
def test_df_package_has_no_network_imports():
    import app.df.engine
    import app.df.fusion
    import app.df.geometry
    import app.df.nodes
    import app.df.solvers
    import app.df.sync

    banned = {"requests", "httpx", "urllib", "socket", "aiohttp", "http"}
    for mod in (app.df.engine, app.df.fusion, app.df.geometry, app.df.nodes,
                app.df.solvers, app.df.sync):
        tree = ast.parse(inspect.getsource(mod))
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names.append((node.module or "").split(".")[0])
        assert not (banned & set(names)), (mod.__name__, names)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_df_api_end_to_end_in_sim():
    reset_nodes()
    r = client.post(
        "/api/simulation/reset",
        json={"environment": {"num_bands": 32, "num_time_slots": 800, "seed": 5,
                              "emitter_density": 0.3},
              "scheduler": "priority"},
        headers=_h(),
    )
    assert r.status_code == 200
    client.post("/api/simulation/step", json={"count": 300}, headers=_h())

    nodes = client.get("/api/df/nodes", headers=_h()).json()["nodes"]
    assert len(nodes) == 4

    fixes = client.get("/api/df/fixes", headers=_h()).json()
    assert fixes["summary"]["n_nodes"] == 4
    assert len(fixes["fixes"]) >= 1
    f0 = fixes["fixes"][0]
    for k in ("est_x_km", "est_y_km", "true_x_km", "ellipse_a_km", "cep_km", "error_km"):
        assert k in f0
    assert f0["true_x_km"] is not None        # sim -> ground truth present
    assert f0["error_km"] is not None
    assert f0["n_nodes"] == 4

    one = client.get(f"/api/df/fixes/{f0['track_id']}", headers=_h())
    assert one.status_code == 200
    assert "history" in one.json()

    health = client.get("/api/df/health", headers=_h()).json()
    assert health["node_count"] == 4
    assert all("timing_sigma_ns" in n for n in health["nodes"])

    # determinism: same state -> identical fixes
    again = client.get("/api/df/fixes", headers=_h()).json()["fixes"]
    assert again == fixes["fixes"]

    st = client.get("/api/state", headers=_h()).json()
    assert "df" in st and st["df"]["n_nodes"] == 4
    reset_nodes()


def test_df_nodes_replace_and_lan_register():
    reset_nodes()
    custom = {
        "nodes": [
            {"node_id": "a", "name": "A", "x_km": 0, "y_km": 30},
            {"node_id": "b", "name": "B", "x_km": 26, "y_km": -15},
            {"node_id": "c", "name": "C", "x_km": -26, "y_km": -15},
        ]
    }
    assert client.post("/api/df/nodes", json=custom, headers=_h()).status_code == 200
    assert len(client.get("/api/df/nodes", headers=_h()).json()["nodes"]) == 3

    bad = client.post(
        "/api/df/register",
        json={"key": "wrong", "node": {"name": "peer", "x_km": 5, "y_km": 5}},
    )
    assert bad.status_code == 403

    ok = client.post(
        "/api/df/register",
        json={"key": "spectra-df-lan-key",
              "node": {"name": "peer", "x_km": 5, "y_km": 5}},
    )
    assert ok.status_code == 200
    assert ok.json()["kind"] == "lan"
    assert len(client.get("/api/df/nodes", headers=_h()).json()["nodes"]) == 4
    reset_nodes()
