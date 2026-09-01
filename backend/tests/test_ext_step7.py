"""Extension Step 7: streaming, durable sessions, data schema, hardening,
air-gap, v1 alias."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ratelimit import RateLimiter
from app.stream.hub import StreamHub

client = TestClient(app)
_BACKEND = Path(__file__).resolve().parents[1]


def _h():
    return {"Authorization": "Bearer test"}


def _real_token() -> str:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    return r.json()["access_token"]


# --------------------------------------------------------------------------- #
# WebSocket /ws
# --------------------------------------------------------------------------- #
def test_ws_streams_ordered_state_events():
    tok = _real_token()
    with client.websocket_connect(f"/ws?token={tok}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"

        client.post("/api/simulation/reset", json={"scheduler": "priority"}, headers=_h())
        seqs: list[int] = []
        for _ in range(3):
            client.post("/api/simulation/step", json={"count": 20}, headers=_h())
        # drain a few events
        got = 0
        while got < 3:
            evt = ws.receive_json()
            if evt["type"] == "state":
                seqs.append(evt["seq"])
                got += 1
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
        assert "time_slot" in evt["payload"]


def test_ws_rejects_a_bad_token():
    with pytest.raises(Exception):
        with client.websocket_connect("/ws?token=not-a-jwt") as ws:
            ws.receive_json()


def test_hub_backpressure_drops_state_never_alert():
    hub = StreamHub()
    sub = hub.subscribe()  # nobody consuming
    for i in range(400):
        hub.publish("state", {"i": i})
    assert sub.dropped > 0
    assert sub.queue.qsize() <= 300  # soft cap held

    sub2 = hub.subscribe()
    for i in range(400):
        hub.publish("alert", {"i": i})
    assert sub2.dropped == 0
    assert sub2.queue.qsize() == 400  # alerts are never dropped


# --------------------------------------------------------------------------- #
# Durable sessions
# --------------------------------------------------------------------------- #
def test_session_record_finish_reload_export_import():
    from app.store.sessions import SESSION_SCHEMA_VERSION
    from app.store.sessions import _reset_for_tests as reset_store

    reset_store()
    start = client.post(
        "/api/sessions/start", json={"name": "unit-sess", "tags": ["test"]}, headers=_h()
    )
    assert start.status_code == 200
    sid = start.json()["session_id"]

    client.post("/api/simulation/reset", json={"scheduler": "priority"}, headers=_h())
    client.post("/api/simulation/step", json={"count": 200}, headers=_h())

    fin = client.post("/api/sessions/finish", headers=_h())
    assert fin.status_code == 200
    meta = fin.json()
    assert meta["session_id"] == sid
    assert meta["schema_version"] == SESSION_SCHEMA_VERSION
    assert meta["row_counts"]["decisions"] >= 150

    listed = client.get("/api/sessions", headers=_h()).json()["sessions"]
    assert any(s["session_id"] == sid for s in listed)

    rows = client.get(f"/api/sessions/{sid}/data/decisions", headers=_h()).json()["rows"]
    assert len(rows) == meta["row_counts"]["decisions"]
    assert all(r["schema_version"] == SESSION_SCHEMA_VERSION for r in rows)
    assert {"time_slot", "selected_band", "reward"} <= set(rows[0])

    blob = client.get(f"/api/sessions/{sid}/export", headers=_h()).content
    assert blob[:2] == b"PK"  # zip

    # wipe local copy, re-import
    from app.store.sessions import _sessions_dir

    import shutil

    shutil.rmtree(_sessions_dir() / sid)
    imp = client.post("/api/sessions/import", content=blob, headers=_h())
    assert imp.status_code == 200
    assert imp.json()["session_id"] == sid
    rows2 = client.get(f"/api/sessions/{sid}/data/decisions", headers=_h()).json()["rows"]
    assert len(rows2) == len(rows)
    reset_store()


def test_session_import_rejects_a_tampered_archive():
    from app.store.sessions import _reset_for_tests as reset_store

    reset_store()
    client.post("/api/sessions/start", json={"name": "tamper"}, headers=_h())
    client.post("/api/simulation/step", json={"count": 30}, headers=_h())
    sid = client.post("/api/sessions/finish", headers=_h()).json()["session_id"]
    blob = bytearray(client.get(f"/api/sessions/{sid}/export", headers=_h()).content)
    blob[-40:] = b"x" * 40  # corrupt the tail
    r = client.post("/api/sessions/import", content=bytes(blob), headers=_h())
    assert r.status_code == 400
    reset_store()


# --------------------------------------------------------------------------- #
# API v1 alias
# --------------------------------------------------------------------------- #
def test_v1_alias_matches_bare_paths():
    assert client.get("/api/health").json() == client.get("/api/v1/health").json()
    a = client.get("/api/schedulers", headers=_h()).json()
    b = client.get("/api/v1/schedulers", headers=_h()).json()
    assert a == b


# --------------------------------------------------------------------------- #
# Rate limiter
# --------------------------------------------------------------------------- #
def test_rate_limiter_sliding_window():
    rl = RateLimiter(rpm=3, window_s=60.0)
    assert [rl.allow("k", now=t) for t in (0, 1, 2)] == [True, True, True]
    assert rl.allow("k", now=3) is False
    assert rl.allow("other", now=3) is True       # per-key
    assert rl.allow("k", now=61) is True           # window slid past the first hit


# --------------------------------------------------------------------------- #
# Production hardening
# --------------------------------------------------------------------------- #
def test_production_refuses_insecure_defaults(monkeypatch):
    from app.config import InsecureProductionConfig, get_settings, validate_production

    monkeypatch.setenv("SPECTRA_PRODUCTION", "1")
    monkeypatch.delenv("SPECTRA_JWT_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(InsecureProductionConfig) as exc:
            validate_production()
        msg = str(exc.value)
        assert "JWT" in msg and "TLS" in msg

        monkeypatch.setenv("SPECTRA_JWT_KEY", "a-real-secret-key-not-the-default-000")
        monkeypatch.setenv("SPECTRA_SEED_USERS", "0")
        monkeypatch.setenv("SPECTRA_TLS_CERT", "/etc/spectra/cert.pem")
        monkeypatch.setenv("SPECTRA_TLS_KEY", "/etc/spectra/key.pem")
        monkeypatch.setenv("SPECTRA_CORS_ORIGINS", "https://ops.example.internal")
        get_settings.cache_clear()
        assert validate_production() == []
    finally:
        get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# Air-gap preflight
# --------------------------------------------------------------------------- #
def test_preflight_reports_zero_outbound_connections():
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.preflight"],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "0 outbound connections" in proc.stdout
