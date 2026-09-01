"""Shared test fixtures.

Extension Step 1 puts auth in front of every ``/api`` route. The pre-existing
test suites (``test_step1..5``) were written before auth existed and call the
API with no token. Rather than edit those files, this autouse fixture overrides
the ``get_principal`` dependency with a static admin principal for every test —
EXCEPT tests marked ``real_auth`` (the new ``test_ext_step1`` suite), which
exercise the real login flow.

A fresh, throwaway data dir is used so the platform DB / audit JSONL never
touch the repo.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP_DATA_DIR = Path(tempfile.mkdtemp(prefix="spectra-test-data-"))
os.environ.setdefault("SPECTRA_DATA_DIR", str(_TMP_DATA_DIR))
os.environ.setdefault("SPECTRA_SEED_USERS", "1")
os.environ.setdefault("SPECTRA_PRODUCTION", "0")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "real_auth: run against the real auth stack (no principal override)",
    )


@pytest.fixture(autouse=True)
def _auth_override(request: pytest.FixtureRequest):
    from app.auth.deps import Principal, Role, get_principal
    from app.main import app

    if request.node.get_closest_marker("real_auth"):
        app.dependency_overrides.pop(get_principal, None)
        yield
        return

    app.dependency_overrides[get_principal] = lambda: Principal(
        username="test-admin", role=Role.admin, is_demo=False
    )
    yield
    app.dependency_overrides.pop(get_principal, None)
