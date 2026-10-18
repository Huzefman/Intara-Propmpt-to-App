"""
LLM telemetry — best-effort recording of gateway calls into llm_calls.

Fail-soft contract: recording must NEVER break an LLM call or a build.
- Missing credentials/table → skip (and permanently disable for table-missing,
  which cannot self-heal within a process lifetime).
- Prompts are NEVER stored (no PII); only routing, usage, timing, outcomes.
"""
from __future__ import annotations

_disabled = False

_PARSE_OUTCOMES = ("ok", "repaired", "llm_repaired", "failed")


def record_llm_call(*, provider: str, model: str | None = None,
                    tokens_in: int | None = None, tokens_out: int | None = None,
                    latency_ms: int | None = None, finish_reason: str | None = None,
                    json_mode: bool | None = None,
                    wish_id: str | None = None, step_key: str | None = None,
                    agent: str | None = None, prompt_version: str | None = None,
                    parse_outcome: str | None = None, repair_used: bool = False,
                    fallback_reason: str | None = None,
                    info_out: dict | None = None) -> bool:
    """Insert one llm_calls row. Returns True on success, False otherwise.

    info_out, when given, receives `telemetry_id` (the inserted row id) so the
    caller can later attribute the *parse* outcome of this call — parsing
    happens after the response arrives, so it cannot be known at insert time.
    """
    global _disabled
    if _disabled:
        return False
    try:
        from db.wishes import _client
        supa = _client()
        payload: dict = {
            "provider": provider,
            "model": model or "unknown",
            "tokens_in": _as_int(tokens_in),
            "tokens_out": _as_int(tokens_out),
            "latency_ms": _as_int(latency_ms),
            "finish_reason": str(finish_reason)[:64] if finish_reason is not None else None,
            "parse_outcome": parse_outcome,
            "repair_used": bool(repair_used),
            "fallback_reason": str(fallback_reason)[:500] if fallback_reason else None,
        }
        if wish_id:
            payload["wish_id"] = wish_id
        if step_key:
            payload["step_key"] = step_key
        if agent:
            payload["agent"] = agent
        if prompt_version:
            payload["prompt_version"] = prompt_version
        res = supa.table("llm_calls").insert(payload).execute()
        row_id = None
        try:
            rows = getattr(res, "data", None) or []
            row_id = rows[0].get("id") if rows and isinstance(rows[0], dict) else None
        except Exception:
            row_id = None
        if info_out is not None and row_id is not None:
            info_out["telemetry_id"] = row_id
        return True
    except Exception as e:
        msg = str(e)
        # Table/config problems cannot self-heal: stop trying this process.
        if "does not exist" in msg or "PGRST204" in msg or "42501" in msg:
            _disabled = True
            print(f"llm telemetry disabled for process: {msg[:160]}")
        else:
            print(f"llm telemetry skipped: {msg[:160]}")
        return False


def set_parse_outcome(row_id, parse_outcome: str, repair_used: bool = False) -> bool:
    """Best-effort UPDATE of a recorded call's parse outcome (fail-soft).

    Attribution happens after JSON parsing, so it needs its own write. Invalid
    outcomes are rejected locally (the DB check constraint would just noise).
    Requires migration 010 (narrow update policy); without it PostgREST matches
    zero rows and this returns False with a loud print — never a silent no-op.
    """
    global _disabled
    if _disabled or not row_id or parse_outcome not in _PARSE_OUTCOMES:
        return False
    try:
        from db.wishes import _client
        supa = _client()
        res = (supa.table("llm_calls")
               .update({"parse_outcome": parse_outcome, "repair_used": bool(repair_used)})
               .eq("id", row_id)
               .select("id")
               .execute())
        rows = getattr(res, "data", None) or []
        if not rows:
            print("llm telemetry outcome update matched 0 rows — is migration "
                  "010 (llm calls attribute outcome) applied?")
            return False
        return True
    except Exception as e:
        msg = str(e)
        if "does not exist" in msg or "PGRST204" in msg or "42501" in msg:
            _disabled = True
            print(f"llm telemetry disabled for process: {msg[:160]}")
        else:
            print(f"llm telemetry outcome update skipped: {msg[:160]}")
        return False


def _as_int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except Exception:
        return None


def reset_for_tests() -> None:
    """Re-enable recording (tests only)."""
    global _disabled
    _disabled = False
