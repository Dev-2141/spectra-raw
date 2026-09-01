"""Durable session storage (Extension Step 7).

Time-series rows (decisions, metrics, alerts, tracks, DF fixes) persisted per
session. Parquet when pyarrow is available, gzip-JSONL otherwise — both carry
``schema_version`` and are covered by ``docs/DATA_SCHEMA.md``.
"""

from .sessions import SESSION_SCHEMA_VERSION, SessionStore, get_session_store

__all__ = ["SESSION_SCHEMA_VERSION", "SessionStore", "get_session_store"]
