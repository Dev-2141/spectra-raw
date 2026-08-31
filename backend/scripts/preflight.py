"""Air-gap preflight: prove the platform opens no outbound network connection.

Monkeypatches socket + urllib to trip on any non-loopback connect(), then runs
a full in-process smoke (import app, health, login, reset, step, tracks, df,
sessions). Exits non-zero if anything reaches the network.

    python -m scripts.preflight        # from backend/
"""

from __future__ import annotations

import ipaddress
import os
import socket
import sys
import tempfile

_VIOLATIONS: list[str] = []
_real_connect = socket.socket.connect


def _is_local(addr) -> bool:
    try:
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_unspecified
    except ValueError:
        return host in ("localhost", "", "::1")


def _guarded_connect(self, address):  # noqa: ANN001
    if not _is_local(address):
        _VIOLATIONS.append(f"outbound connect -> {address}")
        raise OSError(f"preflight: blocked outbound connect to {address}")
    return _real_connect(self, address)


def main() -> int:
    socket.socket.connect = _guarded_connect  # type: ignore[assignment]
    os.environ.setdefault("SPECTRA_DATA_DIR", tempfile.mkdtemp(prefix="preflight-"))
    os.environ.setdefault("SPECTRA_SEED_USERS", "1")

    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"username": "admin", "password": "admin"}).json()[
        "access_token"
    ]
    h = {"Authorization": f"Bearer {tok}"}

    checks = [
        ("health", c.get("/api/health")),
        ("v1 alias", c.get("/api/v1/health")),
        ("state", c.get("/api/state", headers=h)),
        ("reset", c.post("/api/simulation/reset", json={"scheduler": "priority"}, headers=h)),
        ("step", c.post("/api/simulation/step", json={"count": 40}, headers=h)),
        ("tracks", c.get("/api/tracks", headers=h)),
        ("df", c.get("/api/df/fixes", headers=h)),
        ("sessions", c.get("/api/sessions", headers=h)),
        ("schedulers", c.get("/api/schedulers", headers=h)),
    ]
    bad = [name for name, r in checks if r.status_code >= 500]

    if _VIOLATIONS:
        print("FAIL — outbound network detected:")
        for v in _VIOLATIONS:
            print("  -", v)
        return 2
    if bad:
        print("FAIL — endpoints errored:", ", ".join(bad))
        return 1
    print(f"OK — {len(checks)} endpoints exercised, 0 outbound connections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
