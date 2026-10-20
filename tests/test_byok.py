"""BYOK — validation, encryption, routing precedence and quota bypass.

No network: provider calls and Supabase are monkeypatched. Run:
    pytest tests/test_byok.py -v
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_validate_key_rejects_bad_input():
    import userkeys

    with pytest.raises(ValueError):
        userkeys.validate_key("gemini", "short")
    with pytest.raises(ValueError):
        userkeys.validate_key("not-a-provider", "k" * 20)
    with pytest.raises(ValueError):
        userkeys.validate_key("groq", "gsk_" + "a" * 8 + " " + "b" * 8)
    with pytest.raises(ValueError):
        userkeys.validate_key("custom", "k" * 20)  # custom needs a model


def test_custom_base_url_must_be_public_https(monkeypatch):
    import userkeys

    monkeypatch.setattr(userkeys, "_host_is_public", lambda host: host == "api.example.com")

    with pytest.raises(ValueError):
        userkeys.validate_key("custom", "k" * 20, model="m", base_url="http://api.example.com/v1")
    with pytest.raises(ValueError):
        userkeys.validate_key("custom", "k" * 20, model="m", base_url="https://localhost/v1")
    with pytest.raises(ValueError):
        userkeys.validate_key("custom", "k" * 20, model="m", base_url="https://user:pw@api.example.com/v1")
    with pytest.raises(ValueError):
        userkeys.validate_key("custom", "k" * 20, model="m", base_url="https://10.0.0.5/v1")

    key, model, base = userkeys.validate_key(
        "custom", "k" * 20, model="my-model", base_url="https://api.example.com/v1/")
    assert key == "k" * 20
    assert model == "my-model"
    assert base == "https://api.example.com/v1"


def test_validate_key_defaults_and_limits():
    import userkeys

    key, model, base = userkeys.validate_key("gemini", "  AIza-abcdefgh123456  ")
    assert key == "AIza-abcdefgh123456"
    assert model is None
    assert base is None

    with pytest.raises(ValueError):
        userkeys.validate_key("gemini", "k" * 501)
    with pytest.raises(ValueError):
        userkeys.validate_key("gemini", "k" * 10, model="m" * 121)


# ---------------------------------------------------------------------------
# Encryption + masking
# ---------------------------------------------------------------------------
def test_key_encryption_roundtrip(monkeypatch):
    from cryptography.fernet import Fernet

    import userkeys

    monkeypatch.setenv("KEY_ENCRYPTION_SECRET", Fernet.generate_key().decode())
    secret = "sk-live-supersecret-123456"
    enc = userkeys.encrypt_key(secret)

    assert enc != secret
    assert secret not in enc
    assert userkeys.decrypt_key(enc) == secret
    assert userkeys.mask_key(secret) == "••••3456"


def test_public_row_never_leaks_the_key():
    import userkeys

    row = {
        "provider": "groq",
        "api_key": "gsk_abcdefghijklmnop",
        "model": "llama-test",
        "base_url": None,
        "created_at": None,
        "updated_at": None,
    }
    out = userkeys.public_row(row)

    assert "api_key" not in out
    assert "gsk_abcdefghijklmnop" not in str(out)
    assert out["masked"] == "••••mnop"
    assert out["model"] == "llama-test"


# ---------------------------------------------------------------------------
# Chat routing: user keys first, no silent shared fallback
# ---------------------------------------------------------------------------
def _pin_user(monkeypatch, rows):
    import userkeys

    monkeypatch.setattr(userkeys, "current_user", lambda: "user-1")
    monkeypatch.setattr(userkeys, "list_keys", lambda owner: list(rows))
    monkeypatch.setattr(userkeys, "byok_snapshot", lambda: None)


def _forbid_shared(monkeypatch):
    import services.llm as llm

    def _boom(name):
        raise AssertionError("shared provider chain must not be touched for BYOK")

    monkeypatch.setattr(llm, "_allowed", _boom)


def test_byok_groq_uses_saved_key_and_model(monkeypatch):
    import services.llm as llm

    _pin_user(monkeypatch, [{"provider": "groq", "api_key": "gsk_user", "model": "llama-test", "base_url": None}])
    _forbid_shared(monkeypatch)
    seen = {}

    def fake_groq(prompt, model, temperature=0.2, **kw):
        seen.update({"key": kw.get("key"), "model": model})
        return "from-byok"

    monkeypatch.setattr(llm, "_call_groq", fake_groq)

    assert llm._call_llm_inner("hi") == "from-byok"
    assert seen == {"key": "gsk_user", "model": "llama-test"}

    info: dict = {}
    text, meta = llm._call_llm_with_meta_inner("hi", info=info)
    assert text == "from-byok"
    assert meta["source"] == "groq"
    assert meta["model"] == "llama-test"


def test_byok_failure_never_falls_back_to_shared(monkeypatch):
    import services.llm as llm

    _pin_user(monkeypatch, [{"provider": "groq", "api_key": "gsk_broken", "model": None, "base_url": None}])
    _forbid_shared(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("401 invalid API key")

    monkeypatch.setattr(llm, "_call_groq", boom)

    with pytest.raises(llm.ByokError) as err:
        llm._call_llm_inner("hi")
    assert "saved LLM key" in str(err.value)
    assert llm.is_byok_error(err.value) is True


def test_byok_error_redacts_the_key(monkeypatch):
    import services.llm as llm

    secret = "gsk_super_secret_value_123456"
    _pin_user(monkeypatch, [{"provider": "groq", "api_key": secret, "model": None, "base_url": None}])
    _forbid_shared(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError(f"upstream rejected api_key={secret}")

    monkeypatch.setattr(llm, "_call_groq", boom)

    with pytest.raises(llm.ByokError) as err:
        llm._call_llm_inner("hi")
    assert secret not in str(err.value)
    assert "[redacted]" in str(err.value)


def test_byok_wish_plan_surfaces_instead_of_mock(monkeypatch):
    import json
    import types

    import services.llm as llm
    from services import analyzer, planner_v2

    # Keep the test offline: planner_v2 imports main.parse_json before its LLM
    # call, and importing the real main would load .env/provider clients.
    stub = types.ModuleType("main")
    stub.parse_json = json.loads
    monkeypatch.setitem(sys.modules, "main", stub)

    # Force the legacy planner path, then fail the first real LLM call as BYOK.
    def analyzer_fails(prompt):
        raise RuntimeError("analyzer unavailable")

    monkeypatch.setattr(analyzer, "analyze_prompt", analyzer_fails)
    monkeypatch.setattr(llm, "has_any_llm", lambda: True)

    def byok_fails(*args, **kwargs):
        raise llm.ByokError("Your saved LLM key could not complete this request. 401")

    monkeypatch.setattr(llm, "call_llm_with_meta", byok_fails)
    monkeypatch.setattr(planner_v2, "mock_build_plan", lambda prompt: (_ for _ in ()).throw(
        AssertionError("must not silently use the mock plan for a BYOK failure")))

    with pytest.raises(llm.ByokError):
        planner_v2.plan_build("a tiny task tracker")


def test_byok_tries_saved_keys_in_order(monkeypatch):
    import services.llm as llm

    _pin_user(monkeypatch, [
        {"provider": "groq", "api_key": "gsk_first", "model": None, "base_url": None},
        {"provider": "deepseek", "api_key": "ds_second", "model": "deepseek-chat", "base_url": None},
    ])
    _forbid_shared(monkeypatch)

    def bad_groq(*args, **kwargs):
        raise RuntimeError("429 quota")

    seen = {}

    def good_deepseek(prompt, model, temperature=0.2, **kw):
        seen.update({"key": kw.get("key"), "model": model})
        return "deepseek-ok"

    monkeypatch.setattr(llm, "_call_groq", bad_groq)
    monkeypatch.setattr(llm, "_call_deepseek", good_deepseek)

    assert llm._call_llm_inner("hi") == "deepseek-ok"
    assert seen == {"key": "ds_second", "model": "deepseek-chat"}


def test_pinned_snapshot_wins_over_live_lookup(monkeypatch):
    import services.llm as llm
    import userkeys

    monkeypatch.setattr(userkeys, "current_user", lambda: "user-1")
    monkeypatch.setattr(userkeys, "list_keys", lambda owner: [{"provider": "groq", "api_key": "live", "model": None, "base_url": None}])
    monkeypatch.setattr(userkeys, "byok_snapshot", lambda: [{"provider": "groq", "api_key": "pinned", "model": None, "base_url": None}])
    _forbid_shared(monkeypatch)
    monkeypatch.setattr(llm, "_call_groq", lambda prompt, model, temperature=0.2, **kw: f"key={kw.get('key')}")

    assert llm._call_llm_inner("hi") == "key=pinned"


def test_pinned_empty_snapshot_skips_byok(monkeypatch):
    import services.llm as llm
    import userkeys

    monkeypatch.setattr(userkeys, "current_user", lambda: "user-1")
    monkeypatch.setattr(userkeys, "list_keys", lambda owner: [{"provider": "groq", "api_key": "live", "model": None, "base_url": None}])
    monkeypatch.setattr(userkeys, "byok_snapshot", lambda: [])

    assert llm._call_byok("hi") is None


def test_custom_provider_passes_base_url(monkeypatch):
    import services.llm as llm

    _pin_user(monkeypatch, [{
        "provider": "custom",
        "api_key": "custom-key-123456",
        "model": "my-model",
        "base_url": "https://api.example.com/v1",
    }])
    _forbid_shared(monkeypatch)
    seen = {}

    def fake_compat(prompt, model, api_key, base_url, temperature=0.2, **kw):
        seen.update({"model": model, "key": api_key, "base": base_url})
        return "custom-ok"

    monkeypatch.setattr(llm, "_call_openai_compatible", fake_compat)

    assert llm._call_llm_inner("hi") == "custom-ok"
    assert seen == {"model": "my-model", "key": "custom-key-123456", "base": "https://api.example.com/v1"}


def test_no_keys_means_shared_chain(monkeypatch):
    import services.llm as llm

    _pin_user(monkeypatch, [])
    assert llm._call_byok("hi") is None


def test_has_any_llm_true_for_byok_even_without_shared_keys(monkeypatch):
    import services.llm as llm
    import userkeys

    for env in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
                "NVIDIA_API_KEY", "DEEPSEEK_API_KEY", "LLM_ONLY"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(userkeys, "using_byok", lambda: True)
    assert llm.has_any_llm() is True

    monkeypatch.setattr(userkeys, "using_byok", lambda: False)
    assert llm.has_any_llm() is False


# ---------------------------------------------------------------------------
# verify_user_key (Account "Test" button)
# ---------------------------------------------------------------------------
def test_verify_user_key_reports_ok(monkeypatch):
    import services.llm as llm

    seen = {}

    def fake_compat(prompt, model, api_key, base_url, temperature=0.2, **kw):
        seen.update({"model": model, "base": base_url})
        return "OK"

    monkeypatch.setattr(llm, "_call_openai_compatible", fake_compat)
    out = llm.verify_user_key("openai", "sk-" + "a" * 30, model="gpt-test")

    assert out["ok"] is True
    assert out["provider"] == "openai"
    assert out["model"] == "gpt-test"
    assert seen["base"] == "https://api.openai.com/v1"


def test_verify_user_key_rejects_bad_provider():
    import services.llm as llm

    with pytest.raises(ValueError):
        llm.verify_user_key("bogus", "k" * 20)


# ---------------------------------------------------------------------------
# Quota bypass
# ---------------------------------------------------------------------------
def test_consume_build_skips_quota_for_byok(monkeypatch):
    import quotas

    calls = []
    monkeypatch.setattr(quotas, "_byok", lambda owner: True)
    monkeypatch.setattr(quotas, "check_build_quota", lambda user: calls.append("check"))
    monkeypatch.setattr(quotas, "record_build", lambda *a, **k: calls.append("record"))

    quotas.consume_build({"id": "user-1"}, wish_id="w1", kind="build")
    assert calls == []


def test_consume_build_meters_without_byok(monkeypatch):
    import quotas

    calls = []
    monkeypatch.setattr(quotas, "_byok", lambda owner: False)
    monkeypatch.setattr(quotas, "check_build_quota", lambda user: calls.append("check"))
    monkeypatch.setattr(quotas, "record_build", lambda *a, **k: calls.append("record"))

    quotas.consume_build({"id": "user-1"}, wish_id="w1", kind="build")
    assert calls == ["check", "record"]


def test_byok_quota_bypass_disabled_in_dev(monkeypatch):
    import quotas

    monkeypatch.setenv("AUTH_REQUIRED", "0")
    monkeypatch.setattr("userkeys.has_keys", lambda owner: True)
    assert quotas._byok("user-1") is False


# ---------------------------------------------------------------------------
# Request identity
# ---------------------------------------------------------------------------
def test_current_user_contextvar_roundtrip():
    import userkeys

    try:
        userkeys.set_current_user("account-123")
        assert userkeys.current_user() == "account-123"
        userkeys.set_current_user(None)
        assert userkeys.current_user() is None
    finally:
        userkeys.set_current_user(None)
        userkeys.set_byok_snapshot(None)


def test_iterate_keeps_byok_error_instead_of_stardust(monkeypatch):
    import services.llm as llm
    from services import iterate

    def boom(*args, **kwargs):
        raise llm.ByokError("Your saved LLM key could not complete this request. 429 quota")

    monkeypatch.setattr(llm, "call_llm", boom)

    with pytest.raises(llm.ByokError) as err:
        iterate._bounded_call("hi", 0.2, "edit")
    assert "stardust" not in str(err.value).lower()


def test_byok_schema_failure_surfaces_instead_of_template(monkeypatch):
    import services.llm as llm
    from prompts import schema_v2
    from services.generators import schema_gen

    monkeypatch.delenv("INTARA_TEMPLATE_ONLY", raising=False)
    monkeypatch.setattr(schema_v2, "build_schema_prompt", lambda prd: "prompt")

    def boom(*args, **kwargs):
        raise llm.ByokError("Your saved LLM key could not complete this request. 401")

    monkeypatch.setattr(llm, "call_llm", boom)

    prd = {
        "entities": [{"name": "Task"}],
        "tables": [{"name": "tasks", "fields": [
            {"name": "title", "type": "text"},
            {"name": "created_at", "type": "timestamp"},
        ]}],
        "appKind": "crud",
    }
    with pytest.raises(llm.ByokError):
        schema_gen.generate_schema(prd)


def test_agent_does_not_mask_byok_with_fallback(monkeypatch):
    import services.llm as llm
    from agents.base import run_agent

    fallback: list = []
    calls = {"n": 0}

    def caller(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return "not valid json", {"provider": "groq", "model": "m"}
        raise llm.ByokError("Your saved LLM key could not complete this request. 401")

    class Dummy:
        pass

    with pytest.raises(llm.ByokError):
        run_agent(
            stage="test", prompt_version="v1", prompt="p", output_model=Dummy,
            fallback_fn=lambda: fallback.append(1) or {},
            caller=caller, max_repairs=1,
        )
    assert fallback == []


def test_iterate_classify_surfaces_byok(monkeypatch):
    import services.llm as llm
    from services import iterate

    def boom(*args, **kwargs):
        raise llm.ByokError("Your saved LLM key could not complete this request. 401")

    monkeypatch.setattr(llm, "call_llm", boom)
    wish = {"prd": {"buildGraph": [
        {"id": "frontend-tasks", "kind": "frontend_page", "ref": "tasks"},
    ]}}

    with pytest.raises(llm.ByokError):
        iterate.resolve_step(wish, None, "make it prettier")


def test_byok_lookup_failure_fails_instead_of_using_shared(monkeypatch):
    import services.llm as llm
    import userkeys

    monkeypatch.setattr(userkeys, "current_user", lambda: "user-1")
    monkeypatch.setattr(userkeys, "byok_snapshot", lambda: None)

    def db_down(owner):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(userkeys, "list_keys", db_down)

    with pytest.raises(llm.ByokError) as err:
        llm._call_llm_inner("hi")
    assert "No shared pool was used" in str(err.value)


def test_byok_missing_table_means_no_keys(monkeypatch):
    import services.llm as llm
    import userkeys

    monkeypatch.setattr(userkeys, "current_user", lambda: "user-1")
    monkeypatch.setattr(userkeys, "byok_snapshot", lambda: None)

    def missing(owner):
        raise userkeys.UserKeysUnavailable("013")

    monkeypatch.setattr(userkeys, "list_keys", missing)
    assert llm._byok_rows() == []
