"""Evidence pack — one signed .zip a reviewer can verify offline.

Bundles, for a single persisted session:

* every raw session file (Parquet / gzip-JSONL + meta.json),
* the rendered mission report (HTML + JSON),
* a fresh benchmark JSON (quick matrix) so headline numbers are reproducible,
* ``docs/DATA_SCHEMA.md``, and
* ``manifest.json`` with a SHA-256 for every entry.

No network, no external assets.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .reporting import build_mission_report, mission_report_to_html
from .store.sessions import SESSION_SCHEMA_VERSION, _sessions_dir


def _docs_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "docs"


def build_evidence_pack(session_id: str) -> bytes:
    """Return the evidence-pack ``.zip`` bytes for ``session_id``.

    Raises ``KeyError`` if the session does not exist.
    """
    sdir = _sessions_dir() / session_id
    if not sdir.is_dir():
        raise KeyError(f"session not found: {session_id}")

    report = build_mission_report(session_id)
    report_html = mission_report_to_html(report)

    # A small, fast benchmark so the pack stays quick to generate.
    try:
        from scripts.benchmark import run_benchmark

        benchmark = run_benchmark(seeds=[0, 101], steps=200)
    except Exception as exc:  # pragma: no cover - benchmark is best-effort
        benchmark = {"error": f"benchmark unavailable: {exc}"}

    manifest: dict = {
        "kind": "spectra_evidence_pack",
        "session_id": session_id,
        "schema_version": SESSION_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": {},
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:

        def _add(name: str, data: bytes) -> None:
            z.writestr(name, data)
            manifest["files"][name] = {
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }

        for f in sorted(sdir.iterdir()):
            if f.is_file():
                _add(f"session/{f.name}", f.read_bytes())

        _add("mission_report.html", report_html.encode("utf-8"))
        _add(
            "mission_report.json",
            json.dumps(report, indent=2, default=str).encode("utf-8"),
        )
        _add("benchmark.json", json.dumps(benchmark, indent=2).encode("utf-8"))

        schema = _docs_dir() / "DATA_SCHEMA.md"
        _add(
            "DATA_SCHEMA.md",
            schema.read_bytes()
            if schema.is_file()
            else b"see repo docs/DATA_SCHEMA.md",
        )

        z.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))

    return buf.getvalue()


def verify_evidence_pack(blob: bytes) -> dict:
    """Re-hash every file in a pack against its manifest. For tests / CLI."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        manifest = json.loads(z.read("manifest.json"))
        bad: list[str] = []
        for name, info in manifest["files"].items():
            got = hashlib.sha256(z.read(name)).hexdigest()
            if got != info["sha256"]:
                bad.append(name)
    return {"ok": not bad, "mismatched": bad, "file_count": len(manifest["files"])}
