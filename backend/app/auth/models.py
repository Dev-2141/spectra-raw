"""Pydantic request / response models for the auth API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .store import ROLES


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    demo: bool = False
    must_change_password: bool = False
    expires_in: int


class MeResponse(BaseModel):
    username: str
    role: str
    demo: bool
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=6)
    role: str = Field(default="viewer")

    def validate_role(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")


class SetRoleRequest(BaseModel):
    role: str


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=6)
