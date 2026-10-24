"""
JSON-mode gateway + parse ladder tests — no network, no keys needed.
Covers P1.1/P1.2 acceptance fixtures: unescaped newlines, tabs in
strings, trailing commas, fenced+prose, truncated, BOM, smart quotes,
invalid escapes, empty input, repair-once semantics, truncation gating,
structured-mode attach/fallback/cache, finish_reason + token plumbing.
Run: pytest tests/test_json_parse.py -v
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


def _install_main_stub():
    """Install a kwargs-compatible `main` stub BEFORE any test imports it.

    services.llm does `from main import call_gemini` lazily; without this the
    import pulls the real server/main.py (which load_dotenv()s real keys and
    would burn live quota). Compatible with test_llm_fallback.py, which reuses
    an existing stub carrying _is_test_stub.
    """
    mod = sys.modules.get("main")
    if mod is None or not getattr(mod, "_is_test_stub", False):
        mod = types.ModuleType("main")
        mod._is_test_stub = True
        mod.call_gemini = lambda prompt, **kw: (_ for _ in ()).throw(RuntimeError("Missing GEMINI_API_KEY"))
        mod.parse_json = lambda text: json.loads(text)
        sys.modules["main"] = mod
    return mod


_install_main_stub()


def _fresh_llm(monkeypatch, env):
    for k in ["OPENROUTER_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY",
              "DEEPSEEK_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_FALLBACK",
              "GROQ_MODEL", "NVIDIA_MODEL", "DEEPSEEK_MODEL", "GEMINI_MODEL",
              "LLM_COOLDOWN_SECONDS", "LLM_ONLY", "LLM_TELEMETRY", "LLM_CASSETTES",
              "LLM_CASSETTE_DIR"]:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # Telemetry/cassettes stay off in gateway unit tests (no Supabase writes, no disk).
    monkeypatch.setenv("LLM_TELEMETRY", "0")
    monkeypatch.setenv("LLM_CASSETTES", "off")
    import services.llm as llm
    importlib.reload(llm)
    llm._COOLDOWN.clear()
    llm._NO_JSON_MODE.clear()
    return llm


# ---------- parse ladder fixtures ----------

def test_valid_json_direct():
    from utils.json_parse import parse_json
    assert parse_json('{"a": 1}') == {"a": 1}


def test_fenced_prose():
    from utils.json_parse import parse_json
    assert parse_json('Here you go:\n```json\n{"a": 1,}\n```\nDone.') == {"a": 1}


def test_trailing_commas():
    from utils.json_parse import parse_json
    assert parse_json('{"a": [1, 2,], "b": 3,}') == {"a": [1, 2], "b": 3}


def test_unescaped_newline_in_string():
    from utils.json_parse import parse_json
    assert parse_json('{"readme": "line one\nline two"}') == {"readme": "line one\nline two"}


def test_tab_in_string():
    from utils.json_parse import parse_json
    assert parse_json('{"code": "a\tb"}') == {"code": "a\tb"}


def test_invalid_escapes_repaired():
    from utils.json_parse import parse_json
    # \U and \x are not valid JSON escapes; lone backslash must be doubled
    assert parse_json(r'{"path": "C:\Users\x41"}') == {"path": "C:\\Users\\x41"}
    assert parse_json('{"a": "100\\% sure"}') == {"a": "100\\% sure"}


def test_bom_stripped():
    from utils.json_parse import parse_json
    assert parse_json('\ufeff{"a": 1}') == {"a": 1}


def test_smart_quotes():
    from utils.json_parse import parse_json
    assert parse_json('{\u201ca\u201d: 1}') == {"a": 1}


def test_truncated_object_repaired():
    from utils.json_parse import parse_json
    data = parse_json('{"tables": [{"name": "users"}, {"name": "task', truncated=True)
    assert data["tables"][0] == {"name": "users"}


def test_truncated_false_skips_repair():
    from utils.json_parse import parse_json
    with pytest.raises(json.JSONDecodeError):
        parse_json('{"tables": [{"name": "users"}, {"name": "task', truncated=False)


def test_empty_and_prose_raise():
    from utils.json_parse import parse_json
    with pytest.raises(Exception):
        parse_json('')
    with pytest.raises(Exception):
        parse_json('Sorry, I cannot do that as a language model.')


def test_detect_truncation():
    from utils.json_parse import detect_truncation
    assert detect_truncation("length") is True
    assert detect_truncation("MAX_TOKENS") is True
    assert detect_truncation("stop") is False
    assert detect_truncation(None) is None
    assert detect_truncation("STOP") is False


def test_repair_called_once_on_failure():
    from utils.json_parse import parse_json_with_repair
    calls = []

    def repair(err, bad):
        calls.append((err, bad))
        return '{"fixed": true}'

    data, repaired = parse_json_with_repair('not json at all {{{', repair)
    assert data == {"fixed": True} and repaired is True
    assert len(calls) == 1
    assert len(calls[0][1]) <= 4000


def test_repair_passthrough_and_failure():
    from utils.json_parse import parse_json_with_repair
    data, repaired = parse_json_with_repair('{"a": 1}', lambda e, t: (_ for _ in ()).throw(AssertionError("must not be called")))
    assert data == {"a": 1} and repaired is False
    with pytest.raises(json.JSONDecodeError):
        parse_json_with_repair('{{{nope', lambda e, t: '{"still": broken')
    with pytest.raises(json.JSONDecodeError):
        parse_json_with_repair('{{{nope', lambda e, t: (_ for _ in ()).throw(RuntimeError("llm down")))


def test_repair_snippet_capped():
    from utils.json_parse import parse_json_with_repair
    seen = []

    def repair(err, bad):
        seen.append(bad)
        return '{"a": 1}'

    parse_json_with_repair('x' * 9000 + '{{{', repair, max_repair_chars=100)
    assert len(seen[0]) <= 100


# ---------- gateway structured-mode behavior (mocked transports) ----------

class _FakeCompletions:
    def __init__(self, fn):
        self.fn = fn
        self.seen_kwargs = []

    def create(self, **kwargs):
        self.seen_kwargs.append(kwargs)
        return self.fn(kwargs)


class _FakeChoice:
    def __init__(self, content, finish_reason="stop"):
        self.message = types.SimpleNamespace(content=content)
        self.finish_reason = finish_reason


class _FakeResp:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [_FakeChoice(content, finish_reason)]


def _fake_openai_client(comp):
    client = types.SimpleNamespace()
    client.chat = types.SimpleNamespace(completions=comp)
    return client


def test_json_mode_attaches_response_format(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"GROQ_API_KEY": "g"})
    comp = _FakeCompletions(lambda kw: _FakeResp('{"a": 1}'))
    monkeypatch.setattr(llm, "_groq_client", lambda key=None: _fake_openai_client(comp))
    info: dict = {}
    out = llm._call_groq("hi", "m", json_mode=True, info=info)
    assert out == '{"a": 1}'
    assert comp.seen_kwargs[0].get("response_format") == {"type": "json_object"}
    assert info == {"provider": "groq", "model": "m", "finish_reason": "stop", "json_mode": True}


def test_json_mode_unsupported_falls_back_and_caches(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"GROQ_API_KEY": "g"})

    def fail_then_ok(kw):
        if kw.get("response_format"):
            raise RuntimeError("400 Unknown parameter: 'response_format' is not supported by this model")
        return _FakeResp('{"a": 2}')

    comp = _FakeCompletions(fail_then_ok)
    monkeypatch.setattr(llm, "_groq_client", lambda key=None: _fake_openai_client(comp))
    out = llm._call_groq("hi", "m", json_mode=True)
    assert out == '{"a": 2}'
    assert ("groq", "m") in llm._NO_JSON_MODE
    # second call goes plain immediately (cached), single transport call
    comp2 = _FakeCompletions(lambda kw: _FakeResp('{"a": 3}'))
    monkeypatch.setattr(llm, "_groq_client", lambda key=None: _fake_openai_client(comp2))
    assert llm._call_groq("hi", "m", json_mode=True) == '{"a": 3}'
    assert len(comp2.seen_kwargs) == 1 and "response_format" not in comp2.seen_kwargs[0]


def test_json_mode_quota_never_downgrades(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"GROQ_API_KEY": "g"})

    def quota(kw):
        raise RuntimeError("429 quota exhausted")

    comp = _FakeCompletions(quota)
    monkeypatch.setattr(llm, "_groq_client", lambda key=None: _fake_openai_client(comp))
    with pytest.raises(RuntimeError, match="429"):
        llm._call_groq("hi", "m", json_mode=True)
    assert ("groq", "m") not in llm._NO_JSON_MODE
    assert len(comp.seen_kwargs) == 1  # no plain retry on quota


def test_max_output_tokens_forwarded(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"GROQ_API_KEY": "g"})
    comp = _FakeCompletions(lambda kw: _FakeResp('{"a": 1}'))
    monkeypatch.setattr(llm, "_groq_client", lambda key=None: _fake_openai_client(comp))
    llm._call_groq("hi", "m", max_output_tokens=512)
    assert comp.seen_kwargs[0].get("max_tokens") == 512


def test_call_llm_forwards_json_mode_and_info(monkeypatch):
    llm = _fresh_llm(monkeypatch, {"GROQ_API_KEY": "g"})
    seen = {}

    def fake_groq(prompt, model, temperature=0.2, **kw):
        seen.update(kw)
        info = kw.get("info")
        if info is not None:
            info.update({"provider": "groq", "model": model, "finish_reason": "stop", "json_mode": True})
        return '{"ok": true}'

    monkeypatch.setattr(llm, "_call_groq", fake_groq)
    info: dict = {}
    out = llm.call_llm("hi", json_mode=True, max_output_tokens=256, info=info)
    assert out == '{"ok": true}'
    assert seen.get("json_mode") is True and seen.get("max_output_tokens") == 256
    assert info["provider"] == "groq" and info["finish_reason"] == "stop" and info["attempts"] == 1


def test_call_gemini_structured_config(monkeypatch):
    # Real main module (deps installed); fake only the genai client object.
    sys.modules.pop("main", None)
    import main as main_mod
    assert not getattr(main_mod, "_is_test_stub", False)

    seen = {}

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            seen.update(config=config, model=model)
            msg = types.SimpleNamespace(content='{"a": 9}')
            choice = types.SimpleNamespace(message=msg, finish_reason="STOP")
            return types.SimpleNamespace(text='{"a": 9}', candidates=[choice])

    monkeypatch.setattr(main_mod, "client", types.SimpleNamespace(models=FakeModels()))
    info: dict = {}
    out = main_mod.call_gemini("hi", response_mime_type="application/json",
                               max_output_tokens=128, info=info)
    assert out == '{"a": 9}'
    assert seen["config"]["response_mime_type"] == "application/json"
    assert seen["config"]["max_output_tokens"] == 128
    assert info == {"provider": "gemini", "model": seen["model"],
                    "finish_reason": "STOP", "json_mode": True}


def test_wishes_health_beats_wid_pattern():
    """Regression: /api/wishes/health must match before /wishes/{wid}."""
    from fastapi.testclient import TestClient
    sys.modules.pop("main", None)  # drop stub if present; need the real app
    import main as main_mod
    assert not getattr(main_mod, "_is_test_stub", False)
    c = TestClient(main_mod.app, raise_server_exceptions=False)
    r = c.get("/api/wishes/health")
    assert r.status_code == 200, r.text[:200]
    assert r.json() == {"ok": True, "wishes": True}
