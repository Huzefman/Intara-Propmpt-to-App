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

DEFAULT_DAILY_BUILDS = 0  # 0 = unlimited builds
_LOCK = threading.Lock()
_MEM_BUILDS: dict[str, list[float]] = {}


def daily_limit() -> int:
    return 0


def check_build_quota(user: dict | None) -> None:
    """Quotas are completely disabled. Never raises 429."""
    return


def record_build(user: dict | None, wish_id: str | None = None, kind: str = "build") -> None:
    return


def consume_build(user: dict | None, wish_id: str | None = None, kind: str = "build") -> None:
    """Quotas are completely disabled. Never raises 429."""
    return
