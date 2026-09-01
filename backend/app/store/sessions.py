"""Session recorder + store."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import sqlite3
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings

SESSION_SCHEMA_VERSION = 1
_KINDS = ("decisions", "metrics", "alerts", "tracks", "df_fixes")

try:  # optional Parquet upgrade
    import pyarrow as _pa  # type: ignore
    import pyarrow.parquet as _pq  # type: ignore

    _HAVE_PARQUET = True
except Exception:  # pragma: no cover - pyarrow not installed here
    _HAVE_PARQUET = False


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sessions_dir() -> Path:
    d = get_settings().data_dir / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._db = str(get_settings().platform_db)
        with self._lock, self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY, name TEXT, tags TEXT, mode TEXT,
                    scenario TEXT, scheduler TEXT, started_at TEXT, finished_at TEXT,
                    status TEXT, row_counts TEXT, schema_version INTEGER)"""
            )
        self._active: dict | None = None  # {session_id, buffers: {kind: [rows]}}

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------ #
    def start(self, name: str, tags: list[str], meta: dict) -> dict:
        with self._lock:
            sid = f"sess_{uuid.uuid4().hex[:12]}"
            self._active = {
                "session_id": sid,
                "name": name or sid,
                "tags": list(tags),
                "meta": dict(meta),
                "started_at": _utc(),
                "buffers": {k: [] for k in _KINDS},
            }
            return {"session_id": sid, "recording": True}

    @property
    def active_id(self) -> str | None:
        return self._active["session_id"] if self._active else None

    def record(self, kind: str, rows: list[dict]) -> None:
        if not self._active or kind not in _KINDS or not rows:
            return
        with self._lock:
            buf = self._active["buffers"][kind]
            for r in rows:
                buf.append({**r, "schema_version": SESSION_SCHEMA_VERSION})

    def discard(self) -> None:
        with self._lock:
            self._active = None

    def finish(self) -> dict:
        with self._lock:
            if not self._active:
                raise RuntimeError("no active session")
            a = self._active
            self._active = None

        d = _sessions_dir() / a["session_id"]
        d.mkdir(parents=True, exist_ok=True)
        counts: dict[str, int] = {}
        for kind, rows in a["buffers"].items():
            counts[kind] = len(rows)
            if rows:
                self._write_rows(d, kind, rows)
        meta = {
            "session_id": a["session_id"],
            "name": a["name"],
            "tags": a["tags"],
            "schema_version": SESSION_SCHEMA_VERSION,
            "started_at": a["started_at"],
            "finished_at": _utc(),
            "row_counts": counts,
            "format": "parquet" if _HAVE_PARQUET else "jsonl.gz",
            **a["meta"],
        }
        (d / "meta.json").write_text(json.dumps(meta, indent=2), "utf-8")

        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (a["session_id"], a["name"], json.dumps(a["tags"]),
                 a["meta"].get("mode", ""), a["meta"].get("scenario", ""),
                 a["meta"].get("scheduler", ""), a["started_at"], meta["finished_at"],
                 "finished", json.dumps(counts), SESSION_SCHEMA_VERSION),
            )
        return meta

    # ------------------------------------------------------------------ #
    def _write_rows(self, d: Path, kind: str, rows: list[dict]) -> None:
        if _HAVE_PARQUET:  # pragma: no cover - pyarrow not installed here
            table = _pa.Table.from_pylist(rows)
            _pq.write_table(table, d / f"{kind}.parquet")
        else:
            with gzip.open(d / f"{kind}.jsonl.gz", "wt", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(r, default=str) + "\n")

    def _read_rows(self, d: Path, kind: str) -> list[dict]:
        pq = d / f"{kind}.parquet"
        jz = d / f"{kind}.jsonl.gz"
        if pq.is_file() and _HAVE_PARQUET:  # pragma: no cover
            return _pq.read_table(pq).to_pylist()
        if jz.is_file():
            with gzip.open(jz, "rt", encoding="utf-8") as fh:
                return [json.loads(line) for line in fh if line.strip()]
        return []

    # ------------------------------------------------------------------ #
    def list(self) -> list[dict]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC"
            ).fetchall()
        return [
            {**dict(r), "tags": json.loads(r["tags"] or "[]"),
             "row_counts": json.loads(r["row_counts"] or "{}")}
            for r in rows
        ]

    def meta(self, session_id: str) -> dict:
        path = _sessions_dir() / session_id / "meta.json"
        if not path.is_file():
            raise KeyError(f"session not found: {session_id}")
        return json.loads(path.read_text("utf-8"))

    def data(self, session_id: str, kind: str) -> list[dict]:
        if kind not in _KINDS:
            raise KeyError(f"unknown kind: {kind}")
        d = _sessions_dir() / session_id
        if not d.is_dir():
            raise KeyError(f"session not found: {session_id}")
        return self._read_rows(d, kind)

    # ------------------------------------------------------------------ #
    def export_zip(self, session_id: str) -> bytes:
        d = _sessions_dir() / session_id
        if not d.is_dir():
            raise KeyError(f"session not found: {session_id}")
        buf = io.BytesIO()
        manifest = {"session_id": session_id, "schema_version": SESSION_SCHEMA_VERSION,
                    "files": {}}
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(d.iterdir()):
                data = f.read_bytes()
                z.writestr(f.name, data)
                manifest["files"][f.name] = {
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            z.writestr(
                "DATA_SCHEMA.md",
                (Path(__file__).resolve().parents[3] / "docs" / "DATA_SCHEMA.md").read_text("utf-8")
                if (Path(__file__).resolve().parents[3] / "docs" / "DATA_SCHEMA.md").is_file()
                else "see repo docs/DATA_SCHEMA.md",
            )
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
        return buf.getvalue()

    def import_zip(self, blob: bytes) -> dict:
        try:
            z_ctx = zipfile.ZipFile(io.BytesIO(blob))
        except zipfile.BadZipFile as exc:
            raise ValueError(f"not a valid zip archive: {exc}") from exc
        with z_ctx as z:
            names = z.namelist()
            if "meta.json" not in names or "manifest.json" not in names:
                raise ValueError("not a SPECTRA session export (missing meta/manifest)")
            manifest = json.loads(z.read("manifest.json"))
            meta = json.loads(z.read("meta.json"))
            if int(meta.get("schema_version", 0)) != SESSION_SCHEMA_VERSION:
                raise ValueError(
                    f"schema_version {meta.get('schema_version')} != {SESSION_SCHEMA_VERSION}"
                )
            for fname, info in manifest.get("files", {}).items():
                if fname in names and hashlib.sha256(z.read(fname)).hexdigest() != info["sha256"]:
                    raise ValueError(f"checksum mismatch on {fname}")

            sid = meta["session_id"]
            d = _sessions_dir() / sid
            d.mkdir(parents=True, exist_ok=True)
            for name in names:
                if name in ("manifest.json", "DATA_SCHEMA.md"):
                    continue
                (d / name).write_bytes(z.read(name))

        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (sid, meta.get("name", sid), json.dumps(meta.get("tags", [])),
                 meta.get("mode", ""), meta.get("scenario", ""),
                 meta.get("scheduler", ""), meta.get("started_at", ""),
                 meta.get("finished_at", ""), "imported",
                 json.dumps(meta.get("row_counts", {})), SESSION_SCHEMA_VERSION),
            )
        return meta


_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store


def _reset_for_tests() -> None:
    global _store
    _store = None
