"""SQLite-backed, versioned emitter/threat library + track matching."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from ..config import get_settings
from ..models.core import EmitterLibraryEntry, LibraryEntrySaveRequest, LibraryRevision

_BEHAVIOURS = ("constant", "burst", "periodic", "hopping", "low_duty", "priority")

_SEED = [
    dict(name="SYN-PULSE-A", behavior="periodic", modulation="chirp", home_band=12,
         freq_lo_mhz=2440, freq_hi_mhz=2445, pri_slots=14, pri_jitter=0.05,
         duty_cycle=0.14, threat=0.85, notes="synthetic radar-like pulse train"),
    dict(name="SYN-HOP-B", behavior="hopping", modulation="fsk", home_band=30,
         freq_lo_mhz=2500, freq_hi_mhz=2540, hop_span_bands=8, duty_cycle=0.5,
         threat=0.6, notes="synthetic frequency hopper"),
    dict(name="SYN-CW-C", behavior="constant", modulation="fm", home_band=5,
         freq_lo_mhz=2420, freq_hi_mhz=2425, duty_cycle=0.8, threat=0.3,
         notes="synthetic continuous carrier"),
    dict(name="SYN-BURST-D", behavior="burst", modulation="psk", home_band=44,
         freq_lo_mhz=2560, freq_hi_mhz=2566, duty_cycle=0.18, threat=0.4,
         notes="synthetic bursty comms"),
    dict(name="SYN-INTERMIT-E", behavior="priority", modulation="unknown", home_band=20,
         freq_lo_mhz=2480, freq_hi_mhz=2485, pri_slots=8, pri_jitter=0.2,
         duty_cycle=0.05, threat=0.95, notes="synthetic high-value intermittent"),
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class EmitterLibrary:
    def __init__(self) -> None:
        self._path = str(get_settings().platform_db)
        self._lock = threading.RLock()
        with self._lock, self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS library_entries (
                    entry_id TEXT PRIMARY KEY, name TEXT NOT NULL, data TEXT NOT NULL,
                    revision INTEGER NOT NULL, created_at TEXT, updated_at TEXT)"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS library_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, action TEXT NOT NULL, actor TEXT,
                    ts TEXT NOT NULL, snapshot TEXT NOT NULL)"""
            )
            n = c.execute("SELECT COUNT(*) FROM library_entries").fetchone()[0]
        if n == 0:
            for row in _SEED:
                self.create(LibraryEntrySaveRequest(**row), actor="system")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------ #
    def _row_to_entry(self, row: sqlite3.Row) -> EmitterLibraryEntry:
        data = json.loads(row["data"])
        data.update(
            entry_id=row["entry_id"], revision=row["revision"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
        return EmitterLibraryEntry(**data)

    def list(self) -> list[EmitterLibraryEntry]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM library_entries ORDER BY threat DESC, name"
                if False
                else "SELECT * FROM library_entries ORDER BY name"
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def get(self, entry_id: str) -> EmitterLibraryEntry:
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM library_entries WHERE entry_id = ?", (entry_id,)
            ).fetchone()
        if not row:
            raise KeyError(f"library entry not found: {entry_id}")
        return self._row_to_entry(row)

    def revisions(self, entry_id: str) -> list[LibraryRevision]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM library_revisions WHERE entry_id = ? ORDER BY revision",
                (entry_id,),
            ).fetchall()
        return [
            LibraryRevision(
                entry_id=r["entry_id"], revision=r["revision"], action=r["action"],
                actor=r["actor"] or "", ts=r["ts"], snapshot=json.loads(r["snapshot"]),
            )
            for r in rows
        ]

    def _write_revision(self, c, entry: EmitterLibraryEntry, action: str, actor: str) -> None:
        c.execute(
            "INSERT INTO library_revisions (entry_id, revision, action, actor, ts, snapshot)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (entry.entry_id, entry.revision, action, actor, _utc(),
             entry.model_dump_json()),
        )

    def create(self, req: LibraryEntrySaveRequest, actor: str) -> EmitterLibraryEntry:
        if req.behavior not in _BEHAVIOURS:
            raise ValueError(f"behavior must be one of {_BEHAVIOURS}")
        now = _utc()
        entry = EmitterLibraryEntry(
            entry_id=f"lib_{uuid.uuid4().hex[:10]}", synthetic=True, revision=1,
            created_at=now, updated_at=now, **req.model_dump(),
        )
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO library_entries VALUES (?, ?, ?, ?, ?, ?)",
                (entry.entry_id, entry.name, entry.model_dump_json(), 1, now, now),
            )
            self._write_revision(c, entry, "create", actor)
        return entry

    def update(self, entry_id: str, req: LibraryEntrySaveRequest, actor: str) -> EmitterLibraryEntry:
        if req.behavior not in _BEHAVIOURS:
            raise ValueError(f"behavior must be one of {_BEHAVIOURS}")
        current = self.get(entry_id)
        now = _utc()
        entry = EmitterLibraryEntry(
            entry_id=entry_id, synthetic=True, revision=current.revision + 1,
            created_at=current.created_at, updated_at=now, **req.model_dump(),
        )
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE library_entries SET name=?, data=?, revision=?, updated_at=? "
                "WHERE entry_id=?",
                (entry.name, entry.model_dump_json(), entry.revision, now, entry_id),
            )
            self._write_revision(c, entry, "update", actor)
        return entry

    def delete(self, entry_id: str, actor: str) -> None:
        current = self.get(entry_id)  # raises KeyError
        current.revision += 1
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM library_entries WHERE entry_id = ?", (entry_id,))
            self._write_revision(c, current, "delete", actor)


_library: EmitterLibrary | None = None


def get_library() -> EmitterLibrary:
    global _library
    if _library is None:
        _library = EmitterLibrary()
    return _library


def _reset_for_tests() -> None:
    global _library
    _library = None


# --------------------------------------------------------------------------- #
# Track <-> library matching
# --------------------------------------------------------------------------- #
def match_features(feats, entries: list, top_k: int = 3) -> list[dict]:
    """Score a track's features against library entries by parameter distance."""
    scored: list[dict] = []
    f_beh = feats.hop_pattern
    for e in entries:
        d = 0.0
        # behaviour agreement (coarse: hop pattern -> hopping)
        beh_match = (
            (e.behavior == "hopping" and f_beh in ("sweep", "list", "random"))
            or (e.behavior in ("periodic", "constant", "burst", "low_duty", "priority")
                and f_beh == "fixed")
        )
        d += 0.0 if beh_match else 0.6
        if e.pri_slots > 0 and feats.pri_estimate > 0:
            d += min(1.0, abs(e.pri_slots - feats.pri_estimate) / max(e.pri_slots, 1.0))
        d += min(1.0, abs(e.duty_cycle - feats.duty_cycle) * 2.0)
        if e.hop_span_bands or feats.bandwidth_bands:
            d += min(1.0, abs(e.hop_span_bands - feats.bandwidth_bands) / 8.0)
        d += min(1.0, abs(e.pri_jitter - feats.pri_jitter))
        score = 1.0 / (1.0 + d)
        scored.append(
            {
                "entry_id": e.entry_id,
                "name": e.name,
                "behavior": e.behavior,
                "modulation": e.modulation,
                "threat": e.threat,
                "score": round(float(score), 4),
            }
        )
    scored.sort(key=lambda m: m["score"], reverse=True)
    return scored[:top_k]
