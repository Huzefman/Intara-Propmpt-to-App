"""
Agent runner (Phase 7, P7.2): one typed LLM call + validation-feedback loop.

run_agent(stage, prompt, output_model, ...):
  1. call_llm_with_meta (json_mode, temperature ≤0.3, telemetry agent+version)
  2. parse ladder + ONE capped LLM repair (parse_json_with_repair)
  3. Pydantic validation + caller gate; on errors re-ask with the error list
     (max_repairs=2, lower temperature each time — guide §8 validation loop)
  4. still failing → deterministic fallback_fn(), marked degraded with
     fallback_reason (never silent, never a throw for content reasons)
Quota exhaustion (429) propagates — the run engine marks the step failed so
a human can retry; burning repairs on empty quota is forbidden.
Inject `caller` in tests (defaults to the real gateway).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AgentResult:
    ok: bool
    output: Any = None            # validated pydantic model (or fallback dict)
    degraded: bool = False
    repair_used: bool = False
    parse_outcome: str | None = None   # ok | repaired | llm_repaired | failed
    fallback_reason: str | None = None
    llm_calls: int = 0
    provider: str | None = None
    model: str | None = None


def _is_quota(e: Exception) -> bool:
    try:
        from utils.json_parse import is_quota_error
        return is_quota_error(e)
    except Exception:
        return "429" in str(e)


def run_agent(*, stage: str, prompt_version: str, prompt: str, output_model,
              fallback_fn: Callable[[], dict],
              gate_fn: Callable[[Any], list[str]] | None = None,
              max_repairs: int = 2, temperature: float = 0.2,
              telemetry_extra: dict | None = None,
              caller: Callable | None = None) -> AgentResult:
    from utils.json_parse import detect_truncation, parse_json_with_repair
    if caller is None:
        from services.llm import call_llm_with_meta as caller  # type: ignore

    tele = {"agent": stage, "prompt_version": prompt_version}
    if telemetry_extra:
        tele.update(telemetry_extra)
    calls = 0

    def _attribute(info: dict, outcome: str, repaired: bool = False) -> None:
        """Best-effort: stamp the parse outcome onto this call's telemetry row."""
        tid = info.get("telemetry_id") if isinstance(info, dict) else None
        if tid is None:
            return
        try:
            from services import telemetry as _tm
            _tm.set_parse_outcome(tid, outcome, repaired)
        except Exception:
            pass

    def _call(prompt_text: str, temp: float):
        nonlocal calls
        info: dict = {}
        try:
            text, meta = caller(prompt_text, temperature=temp, json_mode=True,
                                info=info, telemetry=tele)
        except Exception as e:
            if _is_quota(e):
                raise
            return None, {"error": f"{type(e).__name__}: {e}"}, info
        calls += 1
        trunc = detect_truncation(info.get("finish_reason"))
        repair_rows: list[dict] = []

        def _repair(err: str, bad: str):
            rinfo: dict = {}
            repair_rows.append(rinfo)
            fixed, _ = caller(
                f"Fix this to valid JSON (parse error: {err}): {bad}",
                temperature=0.1, json_mode=True, info=rinfo, telemetry=tele)
            return fixed

        try:
            data, repaired = parse_json_with_repair(text, _repair, truncated=trunc)
            if repaired:
                calls += 1
            _attribute(info, "repaired" if repaired else "ok", repaired)
            for rinfo in repair_rows:
                _attribute(rinfo, "ok")  # its text is the one that parsed
            return data, None, {**info, "repaired": repaired}
        except Exception as e:
            _attribute(info, "failed")
            for rinfo in repair_rows:
                _attribute(rinfo, "failed")
            return None, {"error": f"parse: {e}"}, info

    data, err, info = _call(prompt, temperature)
    if data is None:
        out = fallback_fn()
        return AgentResult(ok=True, output=out, degraded=True, repair_used=False,
                           parse_outcome="failed",
                           fallback_reason=str((err or {}).get("error", "call failed"))[:500],
                           llm_calls=calls, provider=info.get("provider"),
                           model=info.get("model"))

    problems: list[str] = []
    model_obj = None
    try:
        model_obj = output_model.model_validate(data)
    except Exception as e:
        problems.append(f"schema: {e}"[:1000])
    if model_obj is not None and gate_fn is not None:
        try:
            problems.extend(gate_fn(model_obj))
        except Exception as e:
            problems.append(f"gate: {e}"[:500])

    temp = temperature
    repairs = 0
    while problems and repairs < max_repairs:
        repairs += 1
        temp = max(0.0, temp - 0.1)
        fix_prompt = (f"{prompt}\n[REPAIR] Your last output failed validation. "
                      f"Fix ONLY these problems, keep everything else identical:\n"
                      + "\n".join(f"- {p}" for p in problems[:8]))
        data2, err2, info2 = _call(fix_prompt, temp)
        info = info2
        if data2 is None:
            problems = [str((err2 or {}).get("error", "repair call failed"))[:500]]
            continue
        try:
            model_obj = output_model.model_validate(data2)
            data = data2
            problems = gate_fn(model_obj) if gate_fn is not None else []
        except Exception as e:
            problems = [f"schema: {e}"[:1000]]

    if problems:
        out = fallback_fn()
        return AgentResult(
            ok=True, output=out, degraded=True, repair_used=repairs > 0,
            parse_outcome="llm_repaired" if repairs else ("repaired" if info.get("repaired") else "failed"),
            fallback_reason="; ".join(problems)[:500],
            llm_calls=calls, provider=info.get("provider"), model=info.get("model"))
    return AgentResult(
        ok=True, output=model_obj, degraded=False, repair_used=repairs > 0 or bool(info.get("repaired")),
        parse_outcome="llm_repaired" if repairs else ("repaired" if info.get("repaired") else "ok"),
        llm_calls=calls, provider=info.get("provider"), model=info.get("model"))
