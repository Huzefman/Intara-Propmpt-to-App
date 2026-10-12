"""
LLM fallback chain tests — no network, no keys needed (all providers mocked).
Covers: order fallback, 60s cooldown + reuse, all-exhausted 429, has_any_llm,
status cooldown fields, planner mock+warning on all-exhausted.
Run: pytest tests/test_llm_fallback.py -v
"""
import importlib
import os
import sys
import time
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)


def _ensure_main_stub():
    """Stub `main` (server/main.py pulls fastapi/supabase/google at import).
    services.llm does `from main import call_gemini` lazily, so a sys.modules
    stub keeps these unit tests dependency-free."""
    mod = sys.modules.get("main")
    if mod is None or not getattr(mod, "_is_test_stub", False):
        mod = types.ModuleType("main")
        mod._is_test_stub = True
        mod.call_gemini = lambda prompt, **kw: (_ for _ in ()).throw(RuntimeError("Missing GEMINI_API_KEY"))
        import json as _json
        import re as _re

        def _parse_json(text: str):
            text = text.strip()
            if text.startswith("```"):
                text = _re.sub(r"^```(?:json)?\s*", "", text)
                text = _re.sub(r"\s*```$", "", text)
            m = _re.search(r"\{.*\}", text, _re.S)
            if m:
                text = m.group(0)
            return _json.loads(text)

        mod.parse_json = _parse_json
        sys.modules["main"] = mod
    return mod


def _fresh_llm(monkeypatch, env):
    # Isolate env + cooldown state per test
    for k in ["OPENROUTER_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY",
              "DEEPSEEK_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_FALLBACK",
              "GROQ_MODEL", "NVIDIA_MODEL", "DEEPSEEK_MODEL", "GEMINI_MODEL",
              "LLM_COOLDOWN_SECONDS", "LLM_ONLY"]:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    _ensure_main_stub()
    import services.llm as llm
    importlib.reload(llm)
    llm._COOLDOWN.clear()
    return llm


def test_order_gemini_first_falls_to_openrouter_on_quota(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"OPENROUTER_API_KEY": "x", "GEMINI_API_KEY": "y"})
    main_stub = _ensure_main_stub()
    calls = {"gemini": 0, "or": 0}

    def gemini_quota(prompt, **kw):
        calls["gemini"] += 1
        raise RuntimeError("429 quota exhausted")

    def or_ok(*a, **k):
        calls["or"] += 1
        return '{"ok": true}'

    monkeypatch.setattr(main_stub, "call_gemini", gemini_quota)
    monkeypatch.setattr(llm, "_call_openrouter", or_ok)
    out = llm.call_llm("hello")
    assert out == '{"ok": true}'
    assert calls == {"gemini": 1, "or": 1}
    assert llm._in_cooldown("gemini")
    assert not llm._in_cooldown("openrouter")


def test_all_exhausted_raises_429(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"OPENROUTER_API_KEY": "x", "GEMINI_API_KEY": "y", "GROQ_API_KEY": "z"})
    main_stub = _ensure_main_stub()
    monkeypatch.setattr(llm, "_call_openrouter", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429 quota")))
    monkeypatch.setattr(main_stub, "call_gemini", lambda prompt, **kw: (_ for _ in ()).throw(RuntimeError("429 Gemini quota")))
    monkeypatch.setattr(llm, "_call_groq", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429 quota exceeded")))
    with pytest.raises(RuntimeError, match="429 All LLM providers exhausted"):
        llm.call_llm("hello")


def test_cooldown_skips_then_reuses(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"OPENROUTER_API_KEY": "x", "GROQ_API_KEY": "g", "LLM_COOLDOWN_SECONDS": "60"})
    _ensure_main_stub()  # gemini key missing -> Missing key (non-quota) falls through
    calls = {"or": 0, "groq": 0}

    def or_fail(*a, **k):
        calls["or"] += 1
        raise RuntimeError("429 quota exhausted")

    def groq_ok(*a, **k):
        calls["groq"] += 1
        return "GROQ-OK"

    monkeypatch.setattr(llm, "_call_openrouter", or_fail)
    monkeypatch.setattr(llm, "_call_groq", groq_ok)
    assert llm.call_llm("hi") == "GROQ-OK"
    assert calls == {"or": 1, "groq": 1}
    # Second call within cooldown: openrouter skipped entirely
    assert llm.call_llm("hi") == "GROQ-OK"
    assert calls == {"or": 1, "groq": 2}
    # After expiry: openrouter retried again
    llm._COOLDOWN["openrouter"] = time.time() - 1
    assert llm.call_llm("hi") == "GROQ-OK"
    assert calls["or"] == 2


def test_with_meta_falls_through_and_reports_source(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"OPENROUTER_API_KEY": "x", "GROQ_API_KEY": "g"})
    main_stub = _ensure_main_stub()
    monkeypatch.setattr(llm, "_call_openrouter", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429 quota")))
    monkeypatch.setattr(main_stub, "call_gemini", lambda prompt, **kw: (_ for _ in ()).throw(RuntimeError("Missing GEMINI_API_KEY")))
    monkeypatch.setattr(llm, "_call_groq", lambda *a, **k: "G")
    text, meta = llm.call_llm_with_meta("hi")
    assert text == "G"
    assert meta["source"] == "groq"


def test_has_any_llm_covers_groq_only(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"GROQ_API_KEY": "g"})
    assert llm.has_any_llm() is True
    llm2 = _fresh_llm(monkeypatch, {})
    assert llm2.has_any_llm() is False


def test_status_reports_cooldown(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"OPENROUTER_API_KEY": "x", "GEMINI_API_KEY": "y"})
    # Avoid network: stub the OpenRouter quota HTTP check
    try:
        import httpx

        class _R:
            status_code = 500

            def json(self):
                return {}

        monkeypatch.setattr(httpx, "get", lambda *a, **k: _R())
    except Exception:
        pass
    llm._mark_cooldown("openrouter")
    st = llm.get_llm_status()
    assert st["openrouter"]["in_cooldown"] is True
    assert st["openrouter"]["cooldown_until"] is not None
    assert st["order"] == ["gemini", "openrouter", "groq", "nvidia", "deepseek"]
    assert st["primary"] == "gemini"


def test_planner_all_exhausted_returns_mock_warning(monkeypatch):
    _ensure_main_stub()
    llm = _fresh_llm(monkeypatch, {"OPENROUTER_API_KEY": "x", "GEMINI_API_KEY": "y"})
    monkeypatch.setattr(llm, "call_llm_with_meta", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429 All LLM providers exhausted")))
    import services.planner as planner
    importlib.reload(planner)
    data = planner.plan_wish("A task tracker with users and tasks")
    assert data["_meta"]["source"] == "mock"
    assert data["_meta"]["reason"] == "all_exhausted"
    assert "warning" in data["_meta"]


def test_only_gemini_skips_other_providers(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"OPENROUTER_API_KEY": "x", "GEMINI_API_KEY": "y", "GROQ_API_KEY": "g", "LLM_ONLY": "gemini"})
    main_stub = _ensure_main_stub()
    calls = {"or": 0, "groq": 0}

    def or_fail(*a, **k):
        calls["or"] += 1
        raise RuntimeError("should not be called")

    def groq_fail(*a, **k):
        calls["groq"] += 1
        raise RuntimeError("should not be called")

    monkeypatch.setattr(llm, "_call_openrouter", or_fail)
    monkeypatch.setattr(llm, "_call_groq", groq_fail)
    monkeypatch.setattr(main_stub, "call_gemini", lambda prompt, **kw: "GEMINI-OK")
    assert llm.call_llm("hi") == "GEMINI-OK"
    assert calls == {"or": 0, "groq": 0}
    assert llm.has_any_llm() is True
    st = llm.get_llm_status()
    assert st["only"] == ["gemini"]


def test_only_unknown_disables_all(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"GEMINI_API_KEY": "y", "LLM_ONLY": "nope"})
    assert llm.has_any_llm() is False
    with pytest.raises(RuntimeError, match="unconfigured"):
        llm.call_llm("hi")
