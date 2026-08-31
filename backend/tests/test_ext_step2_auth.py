"""Extension Step 2: role / demo gating for the receive-only hardware controls.

Marked ``real_auth`` so the genuine token path is exercised.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.hardware.manager import _reset_for_tests as reset_hw
from app.main import app

pytestmark = pytest.mark.real_auth

client = TestClient(app)


def _login(username: str, password: str) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_hardware_reads_need_a_token_but_any_role_can_read():
    assert client.get("/api/hardware/status").status_code == 401
    viewer = _login("viewer", "viewer")
    assert client.get("/api/hardware/status", headers=_h(viewer)).status_code == 200
    assert client.get("/api/hardware/devices", headers=_h(viewer)).status_code == 200


def test_demo_and_viewer_cannot_start_hardware_or_record():
    reset_hw()
    demo = client.post("/api/auth/demo").json()["access_token"]
    viewer = _login("viewer", "viewer")
    analyst = _login("analyst", "analyst")
    for tok in (demo, viewer, analyst):
        r = client.post(
            "/api/hardware/start",
            json={"config": {"source_mode": "file_replay", "recording_id": "nope"}},
            headers=_h(tok),
        )
        assert r.status_code == 403, (tok, r.status_code)
        assert client.post("/api/hardware/stop", headers=_h(tok)).status_code == 403
        assert client.post("/api/hardware/config",
                           json={"source_mode": "file_replay"},
                           headers=_h(tok)).status_code == 403
        assert client.post("/api/hardware/record/start", headers=_h(tok)).status_code == 403


def test_operator_can_reach_hardware_start_and_failure_is_audited():
    reset_hw()
    # promote a throwaway user to operator
    admin = _login("admin", "admin")
    client.post(
        "/api/auth/users",
        json={"username": "op_hw", "password": "op-pw-123", "role": "operator"},
        headers=_h(admin),
    )
    try:
        op = _login("op_hw", "op-pw-123")
        client.post("/api/mode", json={"mode": "live_es", "confirm": True}, headers=_h(admin))
        r = client.post(
            "/api/hardware/start",
            json={"config": {"source_mode": "file_replay", "recording_id": "does-not-exist"}},
            headers=_h(op),
        )
        # reached the handler (not 403); missing recording -> 409
        assert r.status_code == 409, r.text

        entries = client.get(
            "/api/audit?action=hardware.start", headers=_h(admin)
        ).json()["entries"]
        assert any(e["action"] == "hardware.start" for e in entries)
    finally:
        client.post("/api/mode", json={"mode": "simulation", "confirm": True}, headers=_h(admin))
        client.delete("/api/auth/users/op_hw", headers=_h(admin))
        reset_hw()
