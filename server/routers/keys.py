"""Account + bring-your-own-key endpoints (all owner-scoped)."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from auth import require_user, uid
import userkeys
from quotas import daily_limit
from services.llm import verify_user_key

router = APIRouter()

_TEST_HITS: dict[str, list[float]] = {}
_TEST_LIMIT = 20
_TEST_WINDOW = 3600.0


class KeyIn(BaseModel):
    api_key: str
    model: str | None = None
    base_url: str | None = None


class KeyTestIn(KeyIn):
    provider: str


def _test_rate(owner: str | None) -> None:
    who = owner or "dev"
    now = time.time()
    for key, stamps in list(_TEST_HITS.items()):
        _TEST_HITS[key] = [t for t in stamps if now - t < _TEST_WINDOW]
    stamps = _TEST_HITS.get(who, [])
    if len(stamps) >= _TEST_LIMIT:
        raise HTTPException(429, "Too many key tests — try again in an hour.")
    stamps.append(now)
    _TEST_HITS[who] = stamps


def _quota(owner: str | None, byok: bool) -> dict:
    if byok:
        return {"mode": "byok", "limit": None, "used": 0, "remaining": None}
    limit = daily_limit()
    if not owner:
        return {"mode": "shared", "limit": limit, "used": 0,
                "remaining": max(limit, 0) if limit > 0 else None}
    used = 0
    try:
        from db.wishes import _client
        start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        res = (_client().table("build_events")
               .select("id", count="exact")
               .eq("owner", owner)
               .gte("created_at", start)
               .execute())
        used = res.count if getattr(res, "count", None) is not None else len(res.data or [])
    except Exception:
        used = 0
    return {"mode": "shared", "limit": limit, "used": used,
            "remaining": max(limit - used, 0) if limit > 0 else None}


@router.get("/account")
def get_account(response: Response, user: dict = Depends(require_user)):
    # Account metadata (including masked key hints) is per-session; never cache.
    response.headers["Cache-Control"] = "no-store"
    owner = uid(user)
    available = True
    error = None
    keys: list[dict] = []
    try:
        keys = [userkeys.public_row(row) for row in userkeys.list_keys(owner)]
    except userkeys.UserKeysUnavailable as exc:
        available = False
        error = str(exc)
    except Exception as exc:
        available = False
        print(f"get_account key load failed: {str(exc)[:200]}")
        error = "Could not load saved keys — try again in a moment."
    byok = bool(keys)
    return {
        "email": user.get("email"),
        "mode": "byok" if byok else "shared",
        "byok_available": available,
        "error": error,
        "keys": keys,
        "providers": userkeys.catalog(),
        "quota": _quota(owner, byok),
    }


@router.put("/account/keys/{provider}")
def save_account_key(provider: str, body: KeyIn,
                     user: dict = Depends(require_user)):
    owner = uid(user)
    if not owner:
        raise HTTPException(401, "Sign in to save a key.")
    try:
        row = userkeys.save_key(owner, provider, body.api_key,
                                model=body.model, base_url=body.base_url)
    except userkeys.UserKeysUnavailable as exc:
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        print(f"save_account_key failed: {str(exc)[:200]}")
        raise HTTPException(500, "Could not save the key — try again in a moment.")
    return {"ok": True, "key": row}


@router.delete("/account/keys/{provider}")
def delete_account_key(provider: str, user: dict = Depends(require_user)):
    owner = uid(user)
    if not owner:
        raise HTTPException(401, "Sign in to remove a key.")
    try:
        userkeys.delete_key(owner, provider)
    except userkeys.UserKeysUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        print(f"delete_account_key failed: {str(exc)[:200]}")
        raise HTTPException(500, "Could not remove the key — try again in a moment.")
    return {"ok": True}


@router.post("/account/keys/test")
def test_account_key(body: KeyTestIn, user: dict = Depends(require_user)):
    """Test a key before saving it. 200 with ok=false on provider rejection."""
    owner = uid(user)
    _test_rate(owner)
    try:
        return verify_user_key(body.provider, body.api_key,
                               model=body.model, base_url=body.base_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        msg = str(exc)
        if body.api_key:
            msg = msg.replace(body.api_key, "[redacted]")
        return {"ok": False, "error": msg[:300]}


@router.post("/account/keys/{provider}/test")
def test_saved_key(provider: str, user: dict = Depends(require_user)):
    """Test the saved key without ever sending it back to the browser."""
    owner = uid(user)
    _test_rate(owner)
    try:
        rows = userkeys.list_keys(owner)
    except userkeys.UserKeysUnavailable as exc:
        raise HTTPException(503, str(exc))
    row = next((r for r in rows if r.get("provider") == provider), None)
    if not row:
        raise HTTPException(404, "No key saved for that provider.")
    try:
        return verify_user_key(provider, row["api_key"],
                               model=row.get("model"),
                               base_url=row.get("base_url"))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        msg = str(exc).replace(row["api_key"], "[redacted]")
        return {"ok": False, "error": msg[:300]}
