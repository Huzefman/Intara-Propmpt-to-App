"""Account auth — Supabase JWT verification for the multi-tenant deploy.

Every Studio endpoint requires a Supabase access token. The backend holds the
service key (bypasses RLS), so isolation is enforced twice:
  1. here — the caller's identity comes from a verified JWT, never a body arg;
  2. in the API/data layer — every query is scoped to that identity.

Set AUTH_REQUIRED=0 only for local MEM-only development or tests.
"""
from __future__ import annotations

import hashlib
import os
import time

from fastapi import Header, HTTPException

# Validated-token cache: the Studio polls every 2s, so verifying the JWT against
# Supabase on every request would be wasteful. 60s is short enough that revoked
# sessions stop working promptly.
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 60.0
_CACHE_MAX = 500


def auth_required() -> bool:
    raw = os.getenv("AUTH_REQUIRED", "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(401, message, headers={"WWW-Authenticate": "Bearer"})


def require_user(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency: resolve the bearer token to {id, email}."""
    if not auth_required():
        # Dev/test bypass. ``id`` is None so ownership helpers skip filtering.
        return {"id": None, "email": "dev@localhost", "dev": True}

    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("Sign in to continue.")

    token = authorization.split(None, 1)[1].strip()
    if not token:
        raise _unauthorized("Sign in to continue.")

    cache_key = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    hit = _CACHE.get(cache_key)
    if hit and hit[0] > now:
        return hit[1]

    try:
        from db.wishes import _client
        res = _client().auth.get_user(token)
        user = getattr(res, "user", None)
    except Exception:
        raise _unauthorized("Your session expired — sign in again.")

    uid = str(getattr(user, "id", "") or "") if user is not None else ""
    if not uid:
        raise _unauthorized("Your session is not valid — sign in again.")

    resolved = {"id": uid, "email": getattr(user, "email", None)}
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[cache_key] = (now + _CACHE_TTL, resolved)
    return resolved


def is_dev(user: dict | None) -> bool:
    return bool((user or {}).get("dev"))


def uid(user: dict | None) -> str | None:
    return (user or {}).get("id")


def assert_owner(row: dict | None, user: dict, field: str = "owner") -> None:
    """404 (not 403) — an outsider must not learn that a row exists."""
    if is_dev(user):
        return
    if not row or str(row.get(field) or "") != str(uid(user) or ""):
        raise HTTPException(404, "not found")
