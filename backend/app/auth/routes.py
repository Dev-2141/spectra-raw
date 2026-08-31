"""Authentication + user-management HTTP API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..audit.log import audit
from ..config import get_settings
from ..modes.manager import get_mode_manager
from .deps import Principal, Role, get_principal, get_user_store, require_role
from .models import (
    ChangePasswordRequest,
    CreateUserRequest,
    LoginRequest,
    MeResponse,
    QuickLoginRequest,
    ResetPasswordRequest,
    SetRoleRequest,
    TokenResponse,
)
from .store import ROLES
from .tokens import encode_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue(username: str, *, demo: bool) -> str:
    settings = get_settings()
    return encode_token(
        {"sub": username, "demo": demo},
        settings.jwt_key,
        ttl_seconds=settings.token_ttl_hours * 3600,
    )


def _mode() -> str:
    return get_mode_manager().mode


# --------------------------------------------------------------------------- #
@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    store = get_user_store()
    row = store.verify_login(body.username, body.password)
    if not row:
        audit("anonymous", "auth.login.failed", body.username, mode=_mode())
        raise HTTPException(status_code=401, detail="invalid credentials")
    audit(row["username"], "auth.login", row["username"],
          {"role": row["role"]}, mode=_mode(), role=row["role"])
    return TokenResponse(
        access_token=_issue(row["username"], demo=False),
        username=row["username"],
        role=row["role"],
        demo=False,
        must_change_password=bool(row["must_change_password"]),
        expires_in=get_settings().token_ttl_hours * 3600,
    )


@router.post("/demo", response_model=TokenResponse)
def demo_login() -> TokenResponse:
    if get_settings().production:
        raise HTTPException(status_code=403, detail="demo login is disabled in production")
    audit("demo", "auth.demo", "demo", mode=_mode(), role="viewer")
    return TokenResponse(
        access_token=_issue("demo", demo=True),
        username="demo",
        role="viewer",
        demo=True,
        must_change_password=False,
        expires_in=get_settings().token_ttl_hours * 3600,
    )


@router.get("/config")
def auth_config() -> dict:
    """Unauthenticated: what the login screen may offer.

    ``quick_login`` and the demo session both exist ONLY for local development
    / presentations and are hard-disabled when ``SPECTRA_PRODUCTION`` is set or
    when seed users are turned off. No passwords are ever returned.
    """
    s = get_settings()
    quick = bool(s.seed_users and not s.production)
    return {
        "quick_login_enabled": quick,
        "demo_enabled": not s.production,
        "roles": list(ROLES),
        # dev-seed convention, shown so a presenter knows what is happening
        "seed_convention": "username = role = password" if quick else None,
    }


@router.post("/quick-login", response_model=TokenResponse)
def quick_login(body: QuickLoginRequest) -> TokenResponse:
    """Issue a real token for the seeded user of a chosen role. Dev only.

    Bypasses password entry but NOT the user store: it logs in as an actual
    seeded account (username == role) and is refused in production or without
    seed users. It cannot mint a session for a user that does not exist.
    """
    settings = get_settings()
    if settings.production or not settings.seed_users:
        raise HTTPException(
            status_code=403,
            detail="quick-login is disabled (production or seed users off)",
        )
    role = body.role.strip().lower()
    if role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {ROLES}")

    row = get_user_store().get_user(role)  # seeded username == role
    if not row or row["role"] != role:
        raise HTTPException(
            status_code=403, detail=f"no seeded '{role}' account to quick-login as"
        )
    audit(role, "auth.quick_login", role, {"role": role}, mode=_mode(), role=role)
    return TokenResponse(
        access_token=_issue(role, demo=False),
        username=role,
        role=role,
        demo=False,
        must_change_password=bool(row["must_change_password"]),
        expires_in=settings.token_ttl_hours * 3600,
    )


@router.get("/me", response_model=MeResponse)
def me(principal: Principal = Depends(get_principal)) -> MeResponse:
    must_change = False
    if not principal.is_demo:
        row = get_user_store().get_user(principal.username)
        must_change = bool(row and row["must_change_password"])
    return MeResponse(
        username=principal.username,
        role=principal.role_name,
        demo=principal.is_demo,
        must_change_password=must_change,
    )


@router.post("/logout")
def logout(principal: Principal = Depends(get_principal)) -> dict:
    # Stateless JWT: the client discards the token. Logged for the audit trail.
    audit(principal.username, "auth.logout", principal.username,
          mode=_mode(), role=principal.role_name)
    return {"ok": True}


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    principal: Principal = Depends(get_principal),
) -> dict:
    if principal.is_demo:
        raise HTTPException(status_code=403, detail="demo session has no password")
    store = get_user_store()
    if not store.verify_login(principal.username, body.current_password):
        raise HTTPException(status_code=400, detail="current password is incorrect")
    store.set_password(principal.username, body.new_password, must_change=False)
    audit(principal.username, "auth.change_password", principal.username,
          mode=_mode(), role=principal.role_name)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Admin: user management
# --------------------------------------------------------------------------- #
_admin = require_role(Role.admin, allow_demo=False)


@router.get("/users")
def list_users(_: Principal = Depends(_admin)) -> dict:
    return {"users": get_user_store().list_users(), "roles": list(ROLES)}


@router.post("/users")
def create_user(
    body: CreateUserRequest, principal: Principal = Depends(_admin)
) -> dict:
    if body.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {ROLES}")
    try:
        row = get_user_store().create_user(body.username, body.password, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(principal.username, "user.create", body.username,
          {"role": body.role}, mode=_mode(), role=principal.role_name)
    return {"username": row["username"], "role": row["role"]}


@router.post("/users/{username}/role")
def set_user_role(
    username: str, body: SetRoleRequest, principal: Principal = Depends(_admin)
) -> dict:
    try:
        get_user_store().set_role(username, body.role)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown user: {username}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(principal.username, "user.set_role", username,
          {"role": body.role}, mode=_mode(), role=principal.role_name)
    return {"username": username, "role": body.role}


@router.post("/users/{username}/reset-password")
def reset_user_password(
    username: str,
    body: ResetPasswordRequest,
    principal: Principal = Depends(_admin),
) -> dict:
    try:
        get_user_store().set_password(username, body.new_password, must_change=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown user: {username}") from exc
    audit(principal.username, "user.reset_password", username,
          mode=_mode(), role=principal.role_name)
    return {"ok": True}


@router.delete("/users/{username}")
def delete_user(username: str, principal: Principal = Depends(_admin)) -> dict:
    if username == principal.username:
        raise HTTPException(status_code=400, detail="cannot delete your own account")
    try:
        get_user_store().delete_user(username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown user: {username}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(principal.username, "user.delete", username,
          mode=_mode(), role=principal.role_name)
    return {"ok": True}
