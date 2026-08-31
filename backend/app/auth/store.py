"""SQLite-backed user store. Seeds default users on first init (dev only)."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

from ..config import get_settings
from .passwords import hash_password, verify_password

ROLES: tuple[str, ...] = ("viewer", "analyst", "operator", "admin")

# username, password, role  — seeded only when SPECTRA_SEED_USERS is true.
_SEED_USERS: list[tuple[str, str, str]] = [
    ("admin", "admin", "admin"),
    ("analyst", "analyst", "analyst"),
    ("viewer", "viewer", "viewer"),
    ("demo", "demo", "viewer"),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class UserStore:
    def __init__(self, db_path: str | None = None) -> None:
        settings = get_settings()
        self._path = str(db_path or settings.platform_db)
        self._lock = threading.RLock()
        self._init_db()
        if settings.seed_users:
            self._seed()

    # ------------------------------------------------------------------ #
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username              TEXT PRIMARY KEY,
                    password_hash         TEXT NOT NULL,
                    role                  TEXT NOT NULL,
                    must_change_password  INTEGER NOT NULL DEFAULT 0,
                    created_at            TEXT NOT NULL,
                    updated_at            TEXT NOT NULL
                )
                """
            )

    def _seed(self) -> None:
        with self._lock, self._conn() as conn:
            for username, password, role in _SEED_USERS:
                exists = conn.execute(
                    "SELECT 1 FROM users WHERE username = ?", (username,)
                ).fetchone()
                if exists:
                    continue
                must_change = 0 if username == "demo" else 1
                now = _utc_now()
                conn.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                    (username, hash_password(password), role, must_change, now, now),
                )

    # ------------------------------------------------------------------ #
    def get_user(self, username: str) -> dict | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            return dict(row) if row else None

    def verify_login(self, username: str, password: str) -> dict | None:
        row = self.get_user(username)
        if not row or not verify_password(password, row["password_hash"]):
            return None
        return row

    def list_users(self) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT username, role, must_change_password, created_at, updated_at "
                "FROM users ORDER BY username"
            ).fetchall()
            return [dict(r) for r in rows]

    def count_admins(self) -> int:
        with self._lock, self._conn() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin'"
                ).fetchone()[0]
            )

    def create_user(self, username: str, password: str, role: str) -> dict:
        if role not in ROLES:
            raise ValueError(f"unknown role: {role}")
        username = username.strip()
        if not username:
            raise ValueError("username required")
        with self._lock, self._conn() as conn:
            if conn.execute(
                "SELECT 1 FROM users WHERE username = ?", (username,)
            ).fetchone():
                raise ValueError(f"user already exists: {username}")
            now = _utc_now()
            conn.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                (username, hash_password(password), role, 1, now, now),
            )
        return self.get_user(username)  # type: ignore[return-value]

    def set_password(
        self, username: str, password: str, *, must_change: bool = False
    ) -> None:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = ?, "
                "updated_at = ? WHERE username = ?",
                (hash_password(password), int(must_change), _utc_now(), username),
            )
            if cur.rowcount == 0:
                raise KeyError(username)

    def set_role(self, username: str, role: str) -> None:
        if role not in ROLES:
            raise ValueError(f"unknown role: {role}")
        with self._lock, self._conn() as conn:
            if role != "admin":
                row = conn.execute(
                    "SELECT role FROM users WHERE username = ?", (username,)
                ).fetchone()
                if row and row["role"] == "admin" and self.count_admins() <= 1:
                    raise ValueError("cannot demote the last admin")
            cur = conn.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE username = ?",
                (role, _utc_now(), username),
            )
            if cur.rowcount == 0:
                raise KeyError(username)

    def delete_user(self, username: str) -> None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT role FROM users WHERE username = ?", (username,)
            ).fetchone()
            if not row:
                raise KeyError(username)
            if row["role"] == "admin" and self.count_admins() <= 1:
                raise ValueError("cannot delete the last admin")
            conn.execute("DELETE FROM users WHERE username = ?", (username,))
