"""Append-only audit log (SQLite table + daily JSONL).

There is deliberately no update or delete path — see ``log.py``.
"""

from .log import AuditLog, audit, get_audit_log

__all__ = ["AuditLog", "audit", "get_audit_log"]
