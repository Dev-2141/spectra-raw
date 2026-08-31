"""Extension Step 5: role gating for the DF endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.df.nodes import _reset_for_tests as reset_nodes
from app.main import app

pytestmark = pytest.mark.real_auth

client = TestClient(app)


def _login(u, p):
    r = client.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def test_df_read_is_viewer_write_is_operator():
    reset_nodes()
    assert client.get("/api/df/nodes").status_code == 401

    viewer = _login("viewer", "viewer")
    assert client.get("/api/df/nodes", headers=_h(viewer)).status_code == 200
    assert client.get("/api/df/health", headers=_h(viewer)).status_code == 200

    demo = client.post("/api/auth/demo").json()["access_token"]
    body = {"nodes": [{"name": "n", "x_km": 1, "y_km": 1}]}
    for tok in (viewer, demo, _login("analyst", "analyst")):
        assert client.post("/api/df/nodes", json=body, headers=_h(tok)).status_code == 403

    admin = _login("admin", "admin")
    assert client.post("/api/df/nodes", json=body, headers=_h(admin)).status_code == 200

    aud = client.get("/api/audit?action=df.nodes.set", headers=_h(admin)).json()["entries"]
    assert any(a["action"] == "df.nodes.set" for a in aud)
    reset_nodes()
