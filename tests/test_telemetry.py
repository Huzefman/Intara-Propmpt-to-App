"""
LLM telemetry + cassettes tests — no network, no keys needed.
Covers AGENT.md P2.1/P2.2/P2.3 acceptance:
- record_llm_call payload shape (routing/usage/timing/outcome, NO prompt text)
- fail-soft: missing table disables recorder for the process, never raises
- gateway wrapper records on success incl. fallback_reason attribution
- LLM_TELEMETRY=0 kill-switch
- cassette record → replay round-trip, replay miss falls through to live
- /api/health/llm-stats aggregates by provider/model
- migration 006a is additive-only
Run: pytest tests/test_telemetry.py -v
"""
import importlib
import json
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)


def _ensure_main_stub():
    mod = sys.modules.get("main")
    if mod is None or not getattr(mod, "_is_test_stub", False):
        mod = types.ModuleType("main")
        mod._is_test_stub = True
        mod.call_gemini = lambda prompt, **kw: (_ for _ in ()).throw(RuntimeError("Missing GEMINI_API_KEY"))
        mod.parse_json = lambda text: json.loads(text)
        sys.modules["main"] = mod
    return mod


_ensure_main_stub()


def _fresh_llm(monkeypatch, env):
    for k in ["OPENROUTER_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY",
              "DEEPSEEK_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_FALLBACK",
              "GROQ_MODEL", "NVIDIA_MODEL", "DEEPSEEK_MODEL", "GEMINI_MODEL",
              "LLM_COOLDOWN_SECONDS", "LLM_ONLY", "LLM_TELEMETRY", "LLM_CASSETTES",
              "LLM_CASSETTE_DIR"]:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import services.llm as llm
    importlib.reload(llm)
    llm._COOLDOWN.clear()
    return llm


class _FakeExec:
    def __init__(self, data=None, error=None):
        self._data = data or []
        self._error = error

    def execute(self):
        if self._error:
            raise self._error
        return self

    @property
    def data(self):
        return self._data


class _FakeTable:
    def __init__(self, error=None):
        self.inserted: list = []
        self.updated: list = []
        self._error = error

    def insert(self, payload):
        if self._error:
            raise self._error
        self.inserted.append(payload)
        return _FakeExec(data=[{"id": 1}])

    def update(self, payload):
        if self._error:
            raise self._error
        self.updated.append(payload)
        return self

    def eq(self, *a):
        return self

    def select(self, *a):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a):
        return self

    def execute(self):
        if self._error:
            raise self._error
        return self

    @property
    def data(self):
        return getattr(self, "_rows", [])


def _patch_db_client(monkeypatch, fake):
    import db.wishes as wishes
    monkeypatch.setattr(wishes, "_client", lambda: types.SimpleNamespace(table=lambda name: fake))


# ---------- P2.1 write path ----------

def test_record_payload_shape_no_prompt_text(monkeypatch):
    import services.telemetry as tm
    importlib.reload(tm)
    tm.reset_for_tests()
    fake = _FakeTable()
    _patch_db_client(monkeypatch, fake)
    ok = tm.record_llm_call(provider="groq", model="openai/gpt-oss-20b",
                            tokens_in=120, tokens_out=40, latency_ms=900,
                            finish_reason="stop", wish_id="w-1", step_key="analyzer",
                            agent="analyzer", prompt_version="spec-v2",
                            parse_outcome="repaired", repair_used=True,
                            fallback_reason="429 gemini exhausted")
    assert ok is True
    assert len(fake.inserted) == 1
    p = fake.inserted[0]
    assert p["provider"] == "groq" and p["model"] == "openai/gpt-oss-20b"
    assert p["tokens_in"] == 120 and p["tokens_out"] == 40 and p["latency_ms"] == 900
    assert p["wish_id"] == "w-1" and p["agent"] == "analyzer" and p["parse_outcome"] == "repaired"
    assert p["repair_used"] is True and "429" in p["fallback_reason"]
    assert "prompt" not in p and "prompt_text" not in p, "prompt text must never be stored"


def test_record_disables_on_missing_table(monkeypatch):
    import services.telemetry as tm
    importlib.reload(tm)
    tm.reset_for_tests()
    fake = _FakeTable(error=RuntimeError("relation llm_calls does not exist"))
    _patch_db_client(monkeypatch, fake)
    assert tm.record_llm_call(provider="groq") is False
    # second call short-circuits without touching the client
    assert tm.record_llm_call(provider="groq") is False
    tm.reset_for_tests()


def test_record_threads_row_id_into_info_out(monkeypatch):
    import services.telemetry as tm
    importlib.reload(tm)
    tm.reset_for_tests()
    fake = _FakeTable()
    _patch_db_client(monkeypatch, fake)
    out: dict = {}
    assert tm.record_llm_call(provider="groq", info_out=out) is True
    assert out["telemetry_id"] == 1


def test_set_parse_outcome_updates_row(monkeypatch):
    import services.telemetry as tm
    importlib.reload(tm)
    tm.reset_for_tests()
    fake = _FakeTable()
    fake._rows = [{"id": 7}]  # PostgREST returns updated rows on .select("id")
    _patch_db_client(monkeypatch, fake)
    assert tm.set_parse_outcome(7, "repaired", True) is True
    assert fake.updated == [{"parse_outcome": "repaired", "repair_used": True}]
    # invalid enum rejected locally (DB check constraint would just noise)
    assert tm.set_parse_outcome(7, "bogus") is False
    assert tm.set_parse_outcome(None, "ok") is False
    assert len(fake.updated) == 1


def test_set_parse_outcome_zero_rows_warns(monkeypatch, capsys):
    """RLS without migration 010 → update matches 0 rows → loud False, not silent."""
    import services.telemetry as tm
    importlib.reload(tm)
    tm.reset_for_tests()
    fake = _FakeTable()  # _rows defaults to [] — the no-op case
    _patch_db_client(monkeypatch, fake)
    assert tm.set_parse_outcome(7, "ok") is False
    assert "migration" in capsys.readouterr().out.lower()


def test_set_parse_outcome_fail_soft(monkeypatch):
    import services.telemetry as tm
    importlib.reload(tm)
    tm.reset_for_tests()
    fake = _FakeTable(error=RuntimeError("network down"))
    _patch_db_client(monkeypatch, fake)
    assert tm.set_parse_outcome(1, "ok") is False  # never raises
    tm.reset_for_tests()


def test_gateway_records_success_with_context(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"GROQ_API_KEY": "x", "LLM_TELEMETRY": "1"})
    seen = {}

    def fake_inner(prompt, temperature=0.2, max_tokens=None, *, json_mode=False,
                   max_output_tokens=None, info=None):
        if info is not None:
            info.update({"provider": "groq", "model": "m-groq", "tokens_in": 10,
                         "tokens_out": 5, "finish_reason": "stop", "json_mode": json_mode,
                         "attempts": 1})
        return '{"ok": true}'

    monkeypatch.setattr(llm, "_call_llm_inner", fake_inner)
    import services.telemetry as tm
    monkeypatch.setattr(tm, "record_llm_call",
                        lambda **kw: seen.update(kw) or True)
    out = llm.call_llm("hi", json_mode=True,
                       telemetry={"wish_id": "w-9", "agent": "planner", "prompt_version": "v1"})
    assert out == '{"ok": true}'
    assert seen["provider"] == "groq" and seen["model"] == "m-groq"
    assert seen["tokens_in"] == 10 and seen["tokens_out"] == 5
    assert seen["wish_id"] == "w-9" and seen["agent"] == "planner"
    assert isinstance(seen["latency_ms"], int) and seen["latency_ms"] >= 0


def test_gateway_threads_telemetry_id_into_info(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"GROQ_API_KEY": "x", "LLM_TELEMETRY": "1"})

    def fake_inner(prompt, temperature=0.2, max_tokens=None, *, json_mode=False,
                   max_output_tokens=None, info=None):
        if info is not None:
            info.update({"provider": "groq", "model": "m", "finish_reason": "stop"})
        return "{}"

    monkeypatch.setattr(llm, "_call_llm_inner", fake_inner)
    import services.telemetry as tm

    def fake_record(**kw):
        kw["info_out"]["telemetry_id"] = 42
        return True

    monkeypatch.setattr(tm, "record_llm_call", fake_record)
    info: dict = {}
    assert llm.call_llm("hi", json_mode=True, info=info) == "{}"
    assert info["telemetry_id"] == 42


def test_gateway_attributes_fallback_reason(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"GEMINI_API_KEY": "y", "GROQ_API_KEY": "x",
                                   "LLM_TELEMETRY": "1"})
    main_stub = _ensure_main_stub()
    seen = {}

    def gemini_quota(prompt, **kw):
        raise RuntimeError("429 quota exhausted")

    def groq_ok(prompt, model, temperature=0.2, **kw):
        info = kw.get("info")
        if info is not None:
            info.update({"provider": "groq", "model": model, "finish_reason": "stop",
                         "json_mode": False})
        return "GROQ-OK"

    monkeypatch.setattr(main_stub, "call_gemini", gemini_quota)
    monkeypatch.setattr(llm, "_call_groq", groq_ok)
    import services.telemetry as tm
    monkeypatch.setattr(tm, "record_llm_call",
                        lambda **kw: seen.update(kw) or True)
    assert llm.call_llm("hi") == "GROQ-OK"
    assert seen["provider"] == "groq"
    assert seen.get("fallback_reason") and "429" in seen["fallback_reason"]


def test_telemetry_kill_switch(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"GROQ_API_KEY": "x", "LLM_TELEMETRY": "0"})
    called = []

    def fake_inner(prompt, *a, **k):
        info = k.get("info")
        if info is not None:
            info.update({"provider": "groq", "model": "m"})
        return "ok"

    monkeypatch.setattr(llm, "_call_llm_inner", fake_inner)
    import services.telemetry as tm
    monkeypatch.setattr(tm, "record_llm_call", lambda **kw: called.append(kw) or True)
    assert llm.call_llm("hi") == "ok"
    assert called == []


# ---------- P2.3 cassettes ----------

def test_cassette_record_then_replay(monkeypatch, tmp_path):
    llm = _fresh_llm(monkeypatch, {"GROQ_API_KEY": "x", "LLM_TELEMETRY": "0",
                                   "LLM_CASSETTES": "record",
                                   "LLM_CASSETTE_DIR": str(tmp_path)})
    import services.cassettes as cas
    importlib.reload(cas)

    def fake_inner(prompt, *a, **k):
        info = k.get("info")
        if info is not None:
            info.update({"provider": "groq", "model": "m"})
        return "LIVE-TEXT"

    monkeypatch.setattr(llm, "_call_llm_inner", fake_inner)
    assert llm.call_llm("unique-prompt-1") == "LIVE-TEXT"
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1

    monkeypatch.setenv("LLM_CASSETTES", "replay")

    def boom(prompt, *a, **k):
        raise AssertionError("provider must not be hit on replay")

    monkeypatch.setattr(llm, "_call_llm_inner", boom)
    info: dict = {}
    assert llm.call_llm("unique-prompt-1", info=info) == "LIVE-TEXT"
    assert info.get("provider") == "cassette"


def test_cassette_replay_miss_falls_through_to_live(monkeypatch, tmp_path):
    llm = _fresh_llm(monkeypatch, {"GROQ_API_KEY": "x", "LLM_TELEMETRY": "0",
                                   "LLM_CASSETTES": "replay",
                                   "LLM_CASSETTE_DIR": str(tmp_path)})
    import services.cassettes as cas
    importlib.reload(cas)

    def fake_inner(prompt, *a, **k):
        info = k.get("info")
        if info is not None:
            info.update({"provider": "groq", "model": "m"})
        return "LIVE"

    monkeypatch.setattr(llm, "_call_llm_inner", fake_inner)
    assert llm.call_llm("never-recorded") == "LIVE"


def test_cassette_with_meta_replay_keeps_meta(monkeypatch, tmp_path):
    llm = _fresh_llm(monkeypatch, {"GROQ_API_KEY": "x", "LLM_TELEMETRY": "0",
                                   "LLM_CASSETTES": "record",
                                   "LLM_CASSETTE_DIR": str(tmp_path)})
    import services.cassettes as cas
    importlib.reload(cas)

    def fake_inner(prompt, *a, **k):
        info = k.get("info")
        if info is not None:
            info.update({"provider": "groq", "model": "m"})
        return "T", {"source": "groq", "model": "m"}

    monkeypatch.setattr(llm, "_call_llm_with_meta_inner", fake_inner)
    text, meta = llm.call_llm_with_meta("meta-prompt")
    assert (text, meta["source"]) == ("T", "groq")

    monkeypatch.setenv("LLM_CASSETTES", "replay")

    def boom(prompt, *a, **k):
        raise AssertionError("must not hit provider on replay")

    monkeypatch.setattr(llm, "_call_llm_with_meta_inner", boom)
    text2, meta2 = llm.call_llm_with_meta("meta-prompt")
    assert text2 == "T" and meta2["source"] == "groq"


# ---------- P2.2 endpoint ----------

def test_llm_stats_endpoint_aggregates(monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    pytest.importorskip("starlette.testclient")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "real_main_for_stats", os.path.join(SRV, "main.py"))
    real_main = importlib.util.module_from_spec(spec)
    rows = [
        {"provider": "gemini", "model": "gemini-3.6-flash", "tokens_in": 100,
         "tokens_out": 50, "latency_ms": 1000, "parse_outcome": "ok", "repair_used": False},
        {"provider": "gemini", "model": "gemini-3.6-flash", "tokens_in": 200,
         "tokens_out": 60, "latency_ms": 3000, "parse_outcome": "repaired", "repair_used": True},
        {"provider": "groq", "model": "m-groq", "tokens_in": 10,
         "tokens_out": 5, "latency_ms": 500, "parse_outcome": "failed", "repair_used": False},
    ]
    fake = _FakeTable()
    fake._rows = rows
    _patch_db_client(monkeypatch, fake)
    old_main = sys.modules.get("main")
    sys.modules["main"] = real_main
    try:
        spec.loader.exec_module(real_main)
    finally:
        if old_main is not None:
            sys.modules["main"] = old_main
        else:
            sys.modules.pop("main", None)
    from fastapi.testclient import TestClient
    client = TestClient(real_main.app)
    r = client.get("/api/health/llm-stats")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["n"] == 3
    gem = body["by_provider"]["gemini"]
    assert gem["calls"] == 2 and gem["tokens_in"] == 300 and gem["tokens_out"] == 110
    assert gem["avg_latency_ms"] == 2000 and gem["repaired"] == 1
    assert body["by_provider"]["groq"]["failed"] == 1
    assert body["by_model"]["gemini-3.6-flash"]["calls"] == 2


# ---------- migration guard ----------

def test_migration_006a_additive_only():
    fp = os.path.join(ROOT, "supabase", "migrations", "006a_llm_calls.sql")
    sql = open(fp).read().lower()
    assert "create table if not exists llm_calls" in sql
    for banned in ("alter table wishes", "alter table wish_steps", "drop table", "delete from"):
        assert banned not in sql, f"migration must not contain: {banned}"


def test_migration_010_narrow_update_only():
    """Parse-outcome attribution: update on exactly two columns, nothing else."""
    fp = os.path.join(ROOT, "supabase", "migrations",
                      "010_llm_calls_outcome_attribution.sql")
    sql = open(fp).read().lower()
    assert "for update using (true) with check (true)" in sql
    assert "grant update (parse_outcome, repair_used) on llm_calls" in sql
    assert "revoke update on llm_calls from anon, authenticated" in sql
    for banned in ("alter table wishes", "alter table wish_steps", "drop table",
                   "delete from", "drop policy if exists \"llm calls append\""):
        assert banned not in sql, f"migration must not contain: {banned}"
