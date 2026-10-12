"""
Content-addressed artifact store (Phase 3, P3.1).

Every build-step's FULL content (file trees with real code, scaffolds,
previews) is stored here by sha256 of its canonical JSON. Step rows keep a
small summary + content_sha; resume restores accumulators from the store
instead of regenerating — kills/restarts never lose work.

Write discipline is fail-FAST (put raises: a step must fail rather than
persist a hollow path-only row). Reads are fail-SOFT (get returns None on
miss/error: resume degrades to the legacy regen path).
"""
from __future__ import annotations

import hashlib
import json
import os


def _max_bytes() -> int:
    try:
        return int(os.getenv("ARTIFACT_MAX_BYTES", "20000000"))
    except Exception:
        return 20000000


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode()


def digest(obj: dict) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def put(obj: dict) -> str:
    """Store content, return its sha256. Raises on oversize or DB failure."""
    raw = canonical(obj)
    if len(raw) > _max_bytes():
        raise RuntimeError(f"artifact too large: {len(raw)} > {_max_bytes()} bytes")
    sha = hashlib.sha256(raw).hexdigest()
    from db.wishes import _client
    supa = _client()
    res = supa.table("artifact_contents").upsert(
        {"sha256": sha, "content": obj, "byte_size": len(raw)},
        on_conflict="sha256").execute()
    if not res.data:
        raise RuntimeError("artifact_contents upsert returned no data")
    return sha


def get(sha: str | None) -> dict | None:
    """Fetch content by sha. Returns None on miss or any error (never raises)."""
    if not sha:
        return None
    try:
        from db.wishes import _client
        supa = _client()
        res = (supa.table("artifact_contents").select("content")
               .eq("sha256", sha).limit(1).execute())
        rows = res.data or []
        if not rows:
            return None
        content = rows[0].get("content")
        return content if isinstance(content, dict) else None
    except Exception as e:
        print(f"artifact resolve skipped: {str(e)[:160]}")
        return None
