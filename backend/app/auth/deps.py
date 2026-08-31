"""FastAPI auth dependencies: principal extraction + role gate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from fastapi import Depends, HTTPException, Request

from ..config import get_settings
from .store import ROLES, UserStore
from .tokens import TokenError, decode_token


class Role(IntEnum):
    viewer = 0
    analyst = 1
    operator = 2
    admin = 3


def role_from_name(name: str) -> Role:
    try:
        return Role(ROLES.index(name))
    except ValueError:
        return Role.viewer


@dataclass
class Principal:
    username: str
    role: Role
    is_demo: bool = False

    @property
    def role_name(self) -> str:
        return ROLES[int(self.role)]


# --------------------------------------------------------------------------- #
_store: UserStore | None = None


def get_user_store() -> UserStore:
    global _store
    if _store is None:
        _store = UserStore()
    return _store


def _reset_for_tests() -> None:
    global _store
    _store = None


# --------------------------------------------------------------------------- #
def get_principal(request: Request) -> Principal:
    """Parse the bearer token into a :class:`Principal` or raise 401."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = header[len("Bearer ") :].strip()
    try:
        claims = decode_token(token, get_settings().jwt_key)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc

    if bool(claims.get("demo", False)):
        return Principal(username="demo", role=Role.viewer, is_demo=True)

    username = str(claims.get("sub", ""))
    row = get_user_store().get_user(username)
    if not row:
        raise HTTPException(status_code=401, detail="unknown user")
    return Principal(
        username=username, role=role_from_name(row["role"]), is_demo=False
    )


def require_role(min_role: Role, *, allow_demo: bool = True):
    """Return a dependency that enforces ``principal.role >= min_role``.

    ``allow_demo=False`` additionally blocks the read-only demo session even
    when its nominal role would satisfy ``min_role``.
    """

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.is_demo and not allow_demo:
            raise HTTPException(
                status_code=403,
                detail="demo session cannot perform this action",
            )
        if int(principal.role) < int(min_role):
            raise HTTPException(
                status_code=403,
                detail=f"requires role >= {ROLES[int(min_role)]}",
            )
        return principal

    return _dep
