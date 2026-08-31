"""Local authentication: users, roles, password hashing, JWT sessions.

Stdlib-only (PBKDF2 + hand-rolled HS256) so the platform installs with zero
extra dependencies and runs fully air-gapped. See ``passwords.py`` /
``tokens.py`` docstrings for the rationale.
"""

from .deps import Principal, Role, get_principal, require_role, role_from_name

__all__ = [
    "Principal",
    "Role",
    "get_principal",
    "require_role",
    "role_from_name",
]
