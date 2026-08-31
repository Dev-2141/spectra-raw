"""Append-only audit log.

Every write goes to two places: a row in the ``audit`` table of the platform
SQLite database, and a line in ``<data_dir>/audit/<YYYY-MM-DD>.jsonl``. The
class exposes ``record`` and ``query`` only — no update, no delete. That is the
point: the audit trail is tamper-evident by construction.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from ..config import get_settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AuditLog:
    def __init__(self) -> None:
        settings = get_settings()
        self._path = str(settings.platform_db)
        self._audit_dir = settings.audit_dir
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts      TEXT NOT NULL,
                    actor   TEXT NOT NULL,
                    role    TEXT,
                    action  TEXT NOT NULL,
                    target  TEXT,
                    detail  TEXT,
                    mode    TEXT
                )
                """
            )

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def record(
        self,
        actor: str,
        action: str,
        target: str = "",
        detail: dict | None = None,
        mode: str = "",
        role: str = "",
    ) -> None:
        ts = _utc_now()
        detail_json = json.dumps(detail, default=str) if detail is not None else None
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO audit (ts, actor, role, action, target, detail, mode) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (ts, actor, role, action, target, detail_json, mode),
                )
            line = json.dumps(
                {
                    "ts": ts,
                    "actor": actor,
                    "role": role,
                    "action": action,
                    "target": target,
                    "detail": detail,
                    "mode": mode,
                },
                default=str,
            )
            with open(
                self._audit_dir / f"{ts[:10]}.jsonl", "a", encoding="utf-8"
            ) as handle:
                handle.write(line + "\n")

    def query(
        self,
        *,
        actor: str | None = None,
        action: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        limit = max(1, min(1000, limit))
        offset = max(0, offset)
        clauses = ["1 = 1"]
        args: list = []
        if actor:
            clauses.append("actor = ?")
            args.append(actor)
        if action:
            clauses.append("action LIKE ?")
            args.append(action.replace("*", "%"))
        args.extend([limit, offset])
        sql = (
            "SELECT id, ts, actor, role, action, target, detail, mode FROM audit "
            f"WHERE {' AND '.join(clauses)} ORDER BY id DESC LIMIT ? OFFSET ?"
        )
        with self._lock, self._conn() as conn:
            rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
        for r in rows:
            if r.get("detail"):
                try:
                    r["detail"] = json.loads(r["detail"])
                except (ValueError, TypeError):
                    pass
        return rows


# --------------------------------------------------------------------------- #
_log: AuditLog | None = None


def get_audit_log() -> AuditLog:
    global _log
    if _log is None:
        _log = AuditLog()
    return _log


def audit(
    actor: str,
    action: str,
    target: str = "",
    detail: dict | None = None,
    mode: str = "",
    role: str = "",
) -> None:
    get_audit_log().record(actor, action, target, detail, mode, role)


def _reset_for_tests() -> None:
    global _log
    _log = None
