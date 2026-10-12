"""
Prompt/response cassettes — offline record/replay for gateway evals (Phase 2).

Modes via LLM_CASSETTES: off (default) | record | replay.
- record: live calls are saved as {key}.json under the cassette dir.
- replay: saved responses are served without hitting providers; a replay MISS
  falls through to a live call (safe default — never fail a build for a
  missing cassette).

Fail-soft contract: every function swallows its own errors and degrades to
live behavior. Cassettes are keyed by prompt + sampling params; they store
prompts (dev fixtures only — never production user data).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _mode() -> str:
    return os.getenv("LLM_CASSETTES", "off").strip().lower()


def _dir() -> Path:
    raw = os.getenv("LLM_CASSETTE_DIR", "evals/cassettes")
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


def make_key(prompt: str, *, temperature: float = 0.2, json_mode: bool = False,
             max_output_tokens: int | None = None, max_tokens: int | None = None) -> str:
    raw = json.dumps({"p": prompt, "t": temperature, "j": bool(json_mode),
                      "m": max_output_tokens, "mt": max_tokens}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def replay_lookup(prompt: str, *, temperature: float = 0.2, json_mode: bool = False,
                  max_output_tokens: int | None = None,
                  max_tokens: int | None = None) -> dict | None:
    """Return saved {"text","meta"} in replay mode, else None. Never raises."""
    try:
        if _mode() != "replay":
            return None
        key = make_key(prompt, temperature=temperature, json_mode=json_mode,
                       max_output_tokens=max_output_tokens, max_tokens=max_tokens)
        fp = _dir() / f"{key}.json"
        if not fp.exists():
            return None
        entry = json.loads(fp.read_text())
        if not isinstance(entry, dict) or "text" not in entry:
            return None
        return {"text": entry["text"], "meta": entry.get("meta") or {}}
    except Exception as e:
        print(f"cassette replay skipped: {e!r}"[:160])
        return None


def record_save(prompt: str, text: str, *, meta: dict | None = None,
                temperature: float = 0.2, json_mode: bool = False,
                max_output_tokens: int | None = None,
                max_tokens: int | None = None) -> bool:
    """Save one prompt→response cassette in record mode. Never raises."""
    try:
        if _mode() != "record":
            return False
        d = _dir()
        d.mkdir(parents=True, exist_ok=True)
        key = make_key(prompt, temperature=temperature, json_mode=json_mode,
                       max_output_tokens=max_output_tokens, max_tokens=max_tokens)
        (d / f"{key}.json").write_text(json.dumps({
            "text": text,
            "meta": meta or {},
            "params": {"temperature": temperature, "json_mode": bool(json_mode),
                       "max_output_tokens": max_output_tokens, "max_tokens": max_tokens},
        }))
        return True
    except Exception as e:
        print(f"cassette record skipped: {e!r}"[:160])
        return False
