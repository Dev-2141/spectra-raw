"""Password hashing — stdlib PBKDF2-HMAC-SHA256, no external crypto deps.

Chosen over argon2/bcrypt to keep the platform install dependency-free and
fully air-gapped (no wheel to download, nothing to compile). PBKDF2 with a
high iteration count is an accepted KDF for this threat model. Step 7
(hardening) may swap in argon2 if a vetted local wheel is bundled.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 240_000
_SALT_BYTES = 16


def hash_password(password: str, *, iterations: int = _ITERATIONS) -> str:
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    dk_b64 = base64.b64encode(dk).decode("ascii")
    return f"{_ALGO}${iterations}${salt_b64}${dk_b64}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_s, salt_b64, dk_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        iterations = int(iters_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk, expected)


def needs_rehash(stored: str) -> bool:
    try:
        algo, iters_s, _, _ = stored.split("$")
    except ValueError:
        return True
    return algo != _ALGO or int(iters_s) < _ITERATIONS
