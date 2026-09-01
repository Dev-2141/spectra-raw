"""Extension Step 8: mission report, metric split, evidence pack, ablation.

The benchmark CI gate lives in ``test_ext_step8_benchmark.py``.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.metrics.split import (
    LIVE_METRICS,
    SIM_METRICS,
    recompute_live_metrics,
    recompute_sim_metrics,
)
from app.simulation.engine import Simulation
from app.simulation.presets import get_preset

client = TestClient(app)
_REPO = Path(__file__).resolve().parents[2]


def _h() -> dict:
    return {"Authorization": "Bearer test"}


# --------------------------------------------------------------------------- #
# Metric split — recompute from raw history == live snapshot
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "preset,scheduler",
    [
        ("Periodic Radar-Like Challenge", "priority"),
        ("Frequency Hopping Challenge", "ucb_bandit"),
        ("Dense Emitter Environment", "round_robin"),
    ],
)
def test_sim_metrics_recompute_matches_live_snapshot(preset, scheduler):
    env, rcv = get_preset(preset)
    sim = Simulation(env_config=env, receiver_config=rcv, scheduler_name=scheduler)
    sim.run(500)
    snap = sim.metrics_snapshot().model_dump()
    recomputed = recompute_sim_metrics(sim.history, sim.env)

    assert set(recomputed) <= set(SIM_METRICS)
    for name, value in recomputed.items():
        assert value == pytest.approx(snap[name], abs=1e-2), name


def test_live_metrics_recompute_is_self_consistent():
    env, rcv = get_preset("Frequency Hopping Challenge")
    sim = Simulation(env_config=env, receiver_config=rcv, scheduler_name="priority")
    sim.run(400)
    live = recompute_live_metrics(sim.history)

    assert set(live) <= set(LIVE_METRICS)
    assert 0.0 <= live["occupancy_estimate"] <= 1.0
    assert 0.0 <= live["scan_coverage"] <= 1.0
    # above-threshold count == receiver-flagged steps, recomputed independently
    flagged = sum(
        1 for r in sim.history if r.detection.detected or r.detection.false_alarm
    )
    assert live["above_threshold_detections"] == flagged
    assert live["occupancy_estimate"] == pytest.approx(
        flagged / len(sim.history), abs=1e-4
    )


def test_metric_split_endpoint_names_and_documented():
    r = client.get("/api/report/metrics/split", headers=_h())
    assert r.status_code == 200
    body = r.json()
    sim_names = {m["name"] for m in body["simulation"]}
    live_names = {m["name"] for m in body["live"]}
    assert sim_names == set(SIM_METRICS)
    assert live_names == set(LIVE_METRICS)
    # only the two explicitly-shared metrics may appear in both lists
    assert sim_names & live_names == {"scan_coverage", "average_revisit_time"}
    # ground-truth-only metrics must not leak into the live list
    assert "probability_of_detection" in sim_names
    assert "probability_of_detection" not in live_names
    assert "average_intercept_delay" not in live_names
    assert all(m["definition"] for m in body["simulation"] + body["live"])

    ref = (_REPO / "docs" / "REFERENCE.md").read_text("utf-8")
    assert "Metric split" in ref
    for name in ("probability_of_detection", "average_proxy_reward"):
        assert name in ref


# --------------------------------------------------------------------------- #
# Mission report
# --------------------------------------------------------------------------- #
def _record_session(name: str, preset: str, scheduler: str, steps: int = 240) -> str:
    from app.store.sessions import _reset_for_tests

    _reset_for_tests()
    client.post(
        "/api/simulation/reset",
        json={"preset": preset, "scheduler": scheduler},
        headers=_h(),
    )
    sid = client.post(
        "/api/sessions/start", json={"name": name, "tags": ["step8"]}, headers=_h()
    ).json()["session_id"]
    for _ in range(4):
        client.post("/api/simulation/step", json={"count": steps // 4}, headers=_h())
    client.post("/api/sessions/finish", headers=_h())
    return sid


def test_mission_report_has_every_section_and_no_external_assets():
    sid = _record_session("unit-mission", "Periodic Radar-Like Challenge", "priority")

    j = client.get(f"/api/report/mission/{sid}", headers=_h()).json()
    for key in (
        "session",
        "summary",
        "metrics",
        "timeline",
        "reward_series",
        "scheduler_vs_baseline",
        "tracks",
        "df_fixes",
        "alerts",
        "assumptions",
        "limitations",
    ):
        assert key in j, key
    assert j["metrics"]["simulation"], "expected recorded sim metrics"
    b = j["scheduler_vs_baseline"]
    assert b and b["winner"] == "priority"
    assert b["adaptive_minus_baseline"]["average_reward"] > 0

    html = client.get(
        f"/api/report/mission/{sid}/export/html", headers=_h()
    ).text
    assert html.startswith("<!doctype html>")
    # zero external asset references
    assert not re.search(r"https?://(?!www\.w3\.org)", html)
    assert "src=" not in html
    assert "cdn" not in html.lower()
    assert "googleapis" not in html
    assert "<svg" in html  # server-rendered charts present

    from app.store.sessions import _reset_for_tests

    _reset_for_tests()


def test_mission_report_unknown_session_is_404():
    assert client.get("/api/report/mission/sess_nope", headers=_h()).status_code == 404
    assert (
        client.get("/api/report/mission/sess_nope/export/html", headers=_h()).status_code
        == 404
    )


# --------------------------------------------------------------------------- #
# Evidence pack
# --------------------------------------------------------------------------- #
def test_evidence_pack_manifest_checksums_verify():
    sid = _record_session("unit-evidence", "Frequency Hopping Challenge", "priority")

    blob = client.get(f"/api/evidence/{sid}", headers=_h()).content
    assert blob[:2] == b"PK"

    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = set(z.namelist())
        assert {"manifest.json", "mission_report.html", "benchmark.json"} <= names
        assert any(n.startswith("session/") and n.endswith("meta.json") for n in names)

        import hashlib
        import json

        manifest = json.loads(z.read("manifest.json"))
        assert manifest["session_id"] == sid
        for fname, info in manifest["files"].items():
            assert (
                hashlib.sha256(z.read(fname)).hexdigest() == info["sha256"]
            ), fname

    from app.evidence import verify_evidence_pack

    v = verify_evidence_pack(blob)
    assert v["ok"] and not v["mismatched"] and v["file_count"] >= 5

    from app.store.sessions import _reset_for_tests

    _reset_for_tests()


def test_evidence_pack_unknown_session_is_404():
    assert client.get("/api/evidence/sess_missing", headers=_h()).status_code == 404


# --------------------------------------------------------------------------- #
# Ablation runner
# --------------------------------------------------------------------------- #
def test_ablation_runner_returns_ci_rows_and_baseline_deltas():
    from scripts.ablation import run_ablation

    rep = run_ablation(
        presets=["Sparse Environment"],
        schedulers=["round_robin", "random", "priority"],
        seeds=[0, 101, 202],
        steps=200,
    )
    assert rep["rows"]
    for row in rep["rows"]:
        m = row["metrics"]["average_reward"]
        assert "mean" in m and "ci95" in m
        assert m["ci95"] >= 0.0
        if not row["is_baseline"]:
            assert "round_robin" in row["avg_reward_delta_vs"]

    # determinism
    rep2 = run_ablation(
        presets=["Sparse Environment"],
        schedulers=["round_robin", "random", "priority"],
        seeds=[0, 101, 202],
        steps=200,
    )
    assert rep["rows"] == rep2["rows"]


# --------------------------------------------------------------------------- #
# Docs: internal links resolve; every new module appears in REFERENCE.md
# --------------------------------------------------------------------------- #
_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_docs_have_no_dead_internal_links():
    md_files = [_REPO / "README.md", *sorted((_REPO / "docs").glob("*.md"))]
    missing: list[str] = []
    for md in md_files:
        for target in _LINK.findall(md.read_text("utf-8")):
            target = target.split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (md.parent / target).resolve().exists():
                missing.append(f"{md.name} -> {target}")
    assert not missing, "dead internal links: " + "; ".join(missing)


def test_scenario_load_degrades_cleanly_when_scheduler_unavailable():
    """A torch-gated scheduler left selected must not turn scenario load into a 500."""
    from app.schedulers.registry import scheduler_requirements

    if scheduler_requirements().get("drqn") != ["torch"]:
        pytest.skip("torch is installed — no unavailable scheduler to exercise")

    # selecting drqn fails 400 but the manager keeps the previous sim; a
    # subsequent scenario load must also fail cleanly (400), never 500.
    client.post("/api/simulation/reset", json={"scheduler": "drqn"}, headers=_h())
    scenarios = client.get("/api/scenario", headers=_h()).json()["scenarios"]
    sid = scenarios[0]["scenario_id"]
    r = client.post(
        f"/api/scenario/{sid}/load", headers=_h()
    )
    assert r.status_code in (200, 400), r.status_code
    # and the sim path still works
    assert (
        client.post(
            "/api/simulation/reset", json={"scheduler": "priority"}, headers=_h()
        ).status_code
        == 200
    )


def test_every_step8_module_is_documented_in_reference():
    ref = (_REPO / "docs" / "REFERENCE.md").read_text("utf-8")
    for token in (
        "app/metrics/split.py",
        "app/evidence.py",
        "scripts/benchmark.py",
        "scripts/ablation.py",
        "build_mission_report",
        "mission_report_to_html",
        "BriefMode.tsx",
        "metricsSplit",
    ):
        assert token in ref, token
