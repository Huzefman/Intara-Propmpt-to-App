"""Per-account build quotas.

A build can fan out into dozens of LLM calls, and the free provider pool is
shared by every account. The public deploy therefore allows 3 builds per
account per UTC day (configurable with DAILY_BUILD_LIMIT).

Usage is recorded in `build_events` (migration 012, service-key only). Before
that migration is applied the limiter falls back to process memory so local
development and first deploys still honour 3/day; durable numbers need 012.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone

from fastapi import HTTPException

from db.wishes import _client

DEFAULT_DAILY_BUILDS = 3
_LOCK = threading.Lock()
# Until migration 012 is applied, keep the 3/day promise in-process instead of
# blocking every build. Durable once `build_events` exists.
_MEM_BUILDS: dict[str, list[float]] = {}


def _missing_meter(exc: BaseException) -> bool:
    msg = str(exc)
    return "build_events" in msg and (
        "PGRST205" in msg or "schema cache" in msg
        or "does not exist" in msg or "Could not find the table" in msg
    )


def _day_start_ts() -> float:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _memory_used(owner: str) -> int:
    start = _day_start_ts()
    stamps = [t for t in _MEM_BUILDS.get(owner, []) if t >= start]
    _MEM_BUILDS[owner] = stamps
    return len(stamps)


def daily_limit() -> int:
    try:
        value = int(os.getenv("DAILY_BUILD_LIMIT", str(DEFAULT_DAILY_BUILDS)))
    except Exception:
        return DEFAULT_DAILY_BUILDS
    # <= 0 disables the quota (local development / offline tests).
    return value


def _day_start_iso() -> str:
    return datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()


def _require_account(user: dict | None) -> str | None:
    if not user or user.get("dev"):
        return None
    return user.get("id")


def _byok(owner: str) -> bool:
    """True when this account builds with its own key (no shared-pool quota)."""
    raw = os.getenv("AUTH_REQUIRED", "1").strip().lower()
    if raw in ("0", "false", "off", "no"):
        return False
    try:
        from userkeys import has_keys
        return has_keys(owner)
    except Exception:
        return False


def check_build_quota(user: dict | None) -> None:
    """Raise 429 when today's builds are spent; 503 when metering is missing."""
    owner = _require_account(user)
    limit = daily_limit()
    if not owner or limit <= 0:
        return
    try:
        res = (
            _client().table("build_events")
            .select("id", count="exact")
            .eq("owner", owner)
            .gte("created_at", _day_start_iso())
            .execute()
        )
        used = res.count if getattr(res, "count", None) is not None else len(res.data or [])
    except Exception as e:
        if _missing_meter(e):
            print("build quota: build_events missing — in-memory metering until migration 012 is applied")
            used = _memory_used(owner)
        else:
            raise HTTPException(
                503,
                "Build metering is unavailable — run supabase/migrations/"
                "012_accounts_isolation.sql in the Supabase SQL editor. "
                f"Details: {str(e)[:200]}",
            )
    if used >= limit:
        raise HTTPException(
            429,
            f"Daily build limit reached — {limit} builds per day. "
            "The counter resets at midnight UTC.",
        )


def record_build(user: dict | None, wish_id: str | None = None, kind: str = "build") -> None:
    owner = _require_account(user)
    if not owner or daily_limit() <= 0:
        return
    try:
        res = (
            _client().table("build_events")
            .insert({"owner": owner, "wish_id": wish_id, "kind": kind})
            .execute()
        )
        if not getattr(res, "data", None):
            raise RuntimeError("insert returned no data")
    except Exception as e:
        if _missing_meter(e):
            _MEM_BUILDS.setdefault(owner, []).append(time.time())
            return
        raise HTTPException(
            503,
            "Could not record build usage — run supabase/migrations/"
            "012_accounts_isolation.sql in the Supabase SQL editor. "
            f"Details: {str(e)[:200]}",
        )


def consume_build(user: dict | None, wish_id: str | None = None, kind: str = "build") -> None:
    """Atomically check + record (single worker, so a process lock is enough).

    Accounts with a saved BYOK key skip the shared-pool quota entirely: their
    builds use their own key and never fall back to Intara's keys.
    """
    owner = _require_account(user)
    if not owner or daily_limit() <= 0:
        return
    if _byok(owner):
        return
    with _LOCK:
        check_build_quota(user)
        record_build(user, wish_id=wish_id, kind=kind)
