"""Extension Step 1 verification: identity, access control, mode spine, safety.

Marked ``real_auth`` so conftest does NOT override the principal — these tests
drive the genuine login / token / role path.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.real_auth

client = TestClient(app)


def _login(username: str, password: str) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# Safety spine
# --------------------------------------------------------------------------- #
def test_health_is_public_and_declares_safety():
    b = client.get("/api/health").json()
    assert b["status"] == "ok"
    assert b["transmit_capability"] is False
    assert b["hardware_mode"] == "receive_only"
    assert b["platform_mode"] == "simulation"  # safe default on boot
    assert b["auth"] == "enabled"


def test_mode_defaults_to_simulation():
    admin = _login("admin", "admin")
    m = client.get("/api/mode", headers=_h(admin)).json()
    assert m["mode"] == "simulation"
    assert m["transmit_capability"] is False
    assert m["hardware_mode"] == "receive_only"


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def test_protected_routes_require_a_token():
    assert client.get("/api/state").status_code == 401
    assert client.post("/api/simulation/reset", json={}).status_code == 401
    assert client.get("/api/mode").status_code == 401


def test_login_success_and_failure():
    assert _login("admin", "admin")
    bad = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401


def test_me_reports_role():
    tok = _login("analyst", "analyst")
    me = client.get("/api/auth/me", headers=_h(tok)).json()
    assert me["username"] == "analyst"
    assert me["role"] == "analyst"
    assert me["demo"] is False


# --------------------------------------------------------------------------- #
# Demo / Skip button
# --------------------------------------------------------------------------- #
def test_demo_token_can_read_and_run_sim_but_not_mutate_platform():
    r = client.post("/api/auth/demo")
    assert r.status_code == 200
    body = r.json()
    assert body["demo"] is True and body["role"] == "viewer"
    tok = body["access_token"]

    # allowed: read + run simulation
    assert client.get("/api/state", headers=_h(tok)).status_code == 200
    assert (
        client.post(
            "/api/simulation/reset",
            json={"scheduler": "round_robin"},
            headers=_h(tok),
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/simulation/step", json={"count": 3}, headers=_h(tok)
        ).status_code
        == 200
    )

    # blocked: hardware/config/user/mode mutations
    assert (
        client.post(
            "/api/mode", json={"mode": "live_es", "confirm": True}, headers=_h(tok)
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/tasking/protected-bands", json={"bands": [1]}, headers=_h(tok)
        ).status_code
        == 403
    )
    assert client.get("/api/auth/users", headers=_h(tok)).status_code == 403


# --------------------------------------------------------------------------- #
# RBAC
# --------------------------------------------------------------------------- #
def test_role_hierarchy_on_mode_switch():
    viewer = _login("viewer", "viewer")
    analyst = _login("analyst", "analyst")
    admin = _login("admin", "admin")

    for tok in (viewer, analyst):
        r = client.post(
            "/api/mode", json={"mode": "live_es", "confirm": True}, headers=_h(tok)
        )
        assert r.status_code == 403

    # confirm flag is mandatory
    assert (
        client.post("/api/mode", json={"mode": "live_es"}, headers=_h(admin)).status_code
        == 400
    )

    r = client.post(
        "/api/mode", json={"mode": "live_es", "confirm": True}, headers=_h(admin)
    )
    assert r.status_code == 200
    assert r.json()["mode"] == "live_es"
    assert r.json()["degraded"] is True  # no hardware configured yet

    # restore
    client.post(
        "/api/mode", json={"mode": "simulation", "confirm": True}, headers=_h(admin)
    )


def test_unknown_mode_rejected():
    admin = _login("admin", "admin")
    r = client.post(
        "/api/mode", json={"mode": "transmit", "confirm": True}, headers=_h(admin)
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
def test_mode_switch_and_login_are_audited():
    admin = _login("admin", "admin")
    client.post(
        "/api/mode", json={"mode": "live_es", "confirm": True}, headers=_h(admin)
    )
    client.post(
        "/api/mode", json={"mode": "simulation", "confirm": True}, headers=_h(admin)
    )
    entries = client.get("/api/audit", headers=_h(admin)).json()["entries"]
    actions = {e["action"] for e in entries}
    assert "mode.set" in actions
    assert "auth.login" in actions


def test_simulation_reset_is_audited():
    admin = _login("admin", "admin")
    client.post("/api/simulation/reset", json={"scheduler": "random"}, headers=_h(admin))
    entries = client.get(
        "/api/audit?action=simulation.reset", headers=_h(admin)
    ).json()["entries"]
    assert any(e["action"] == "simulation.reset" for e in entries)


def test_audit_is_read_only_and_operator_gated():
    viewer = _login("viewer", "viewer")
    admin = _login("admin", "admin")
    assert client.get("/api/audit", headers=_h(viewer)).status_code == 403
    assert client.get("/api/audit", headers=_h(admin)).status_code == 200
    # no mutation verbs on the audit resource
    assert client.put("/api/audit", headers=_h(admin)).status_code in (404, 405)
    assert client.delete("/api/audit", headers=_h(admin)).status_code in (404, 405)


# --------------------------------------------------------------------------- #
# Protected bands
# --------------------------------------------------------------------------- #
def test_protected_band_guard_redirects_and_logs():
    admin = _login("admin", "admin")
    protected = [0, 1, 2, 3, 4]
    try:
        assert (
            client.post(
                "/api/tasking/protected-bands",
                json={"bands": protected},
                headers=_h(admin),
            ).status_code
            == 200
        )
        client.post(
            "/api/simulation/reset",
            json={
                "environment": {"num_bands": 12, "num_time_slots": 300, "seed": 3},
                "scheduler": "round_robin",
            },
            headers=_h(admin),
        )
        s = client.post(
            "/api/simulation/step", json={"count": 48}, headers=_h(admin)
        ).json()

        scanned = {row["scanned_band"] for row in s["scan_path"]}
        assert scanned.isdisjoint(set(protected)), scanned
        assert s["protected_override_count"] >= 1

        overrides = client.get(
            "/api/audit?action=protected_band.override", headers=_h(admin)
        ).json()["entries"]
        assert len(overrides) >= 1
    finally:
        client.post(
            "/api/tasking/protected-bands", json={"bands": []}, headers=_h(admin)
        )


# --------------------------------------------------------------------------- #
# User management + change password
# --------------------------------------------------------------------------- #
def test_admin_can_manage_users_and_password_change_flow():
    admin = _login("admin", "admin")

    created = client.post(
        "/api/auth/users",
        json={"username": "tmp_user", "password": "initial-pw", "role": "analyst"},
        headers=_h(admin),
    )
    assert created.status_code == 200, created.text

    try:
        tok = _login("tmp_user", "initial-pw")
        changed = client.post(
            "/api/auth/change-password",
            json={"current_password": "initial-pw", "new_password": "second-pw-9"},
            headers=_h(tok),
        )
        assert changed.status_code == 200

        assert (
            client.post(
                "/api/auth/login",
                json={"username": "tmp_user", "password": "initial-pw"},
            ).status_code
            == 401
        )
        assert _login("tmp_user", "second-pw-9")

        promoted = client.post(
            "/api/auth/users/tmp_user/role",
            json={"role": "operator"},
            headers=_h(admin),
        )
        assert promoted.status_code == 200
    finally:
        client.delete("/api/auth/users/tmp_user", headers=_h(admin))

    assert (
        client.post(
            "/api/auth/login", json={"username": "tmp_user", "password": "second-pw-9"}
        ).status_code
        == 401
    )


def test_cannot_delete_last_admin():
    admin = _login("admin", "admin")
    r = client.delete("/api/auth/users/admin", headers=_h(admin))
    # blocked either as "own account" or "last admin"
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Quick sign-in (login-screen role picker) — dev only
# --------------------------------------------------------------------------- #
def test_auth_config_advertises_quick_login_in_dev():
    cfg = client.get("/api/auth/config").json()
    assert cfg["quick_login_enabled"] is True
    assert cfg["demo_enabled"] is True
    assert "admin" in cfg["roles"]
    assert cfg["seed_convention"] == "username = role = password"


def test_quick_login_issues_a_real_scoped_token_per_role():
    for role in ("viewer", "analyst", "operator", "admin"):
        r = client.post("/api/auth/quick-login", json={"role": role})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["role"] == role and body["demo"] is False
        me = client.get("/api/auth/me", headers=_h(body["access_token"])).json()
        assert me["username"] == role and me["role"] == role

    # operator token really has operator power (mode switch is operator+)
    op = client.post("/api/auth/quick-login", json={"role": "operator"}).json()["access_token"]
    assert client.post(
        "/api/mode", json={"mode": "live_es", "confirm": True}, headers=_h(op)
    ).status_code == 200
    client.post("/api/mode", json={"mode": "simulation", "confirm": True}, headers=_h(op))

    # unknown role rejected; quick-login is audited
    assert client.post("/api/auth/quick-login", json={"role": "root"}).status_code == 400
    admin = _login("admin", "admin")
    aud = client.get("/api/audit?action=auth.quick_login", headers=_h(admin)).json()["entries"]
    assert any(a["action"] == "auth.quick_login" for a in aud)
