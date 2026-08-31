"""Minimal HS256 JWT — stdlib only.

Not a general-purpose JWT library: it issues and verifies exactly the tokens
this platform creates (compact JWS, HMAC-SHA256, ``exp`` check). Kept in-tree
to avoid a PyJWT dependency and stay air-gapped.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


class TokenError(Exception):
    """Raised when a token is malformed, has a bad signature, or is expired."""


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def encode_token(claims: dict, key: str, *, ttl_seconds: int) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {**claims, "iat": now, "exp": now + ttl_seconds}
    signing_input = (
        _b64u(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        + "."
        + _b64u(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    )
    sig = hmac.new(key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64u(sig)}"


def decode_token(token: str, key: str) -> dict:
    try:
        header_seg, payload_seg, sig_seg = token.split(".")
    except ValueError as exc:
        raise TokenError("malformed token") from exc

    expected = _b64u(
        hmac.new(
            key.encode("utf-8"),
            f"{header_seg}.{payload_seg}".encode("ascii"),
            hashlib.sha256,
        ).digest()
    )
    if not hmac.compare_digest(expected, sig_seg):
        raise TokenError("bad signature")

    try:
        payload = json.loads(_b64u_decode(payload_seg))
    except (ValueError, TypeError) as exc:
        raise TokenError("bad payload") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise TokenError("token expired")
    return payload
