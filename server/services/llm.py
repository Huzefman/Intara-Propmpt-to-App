"""
LLM provider — Gemini → OpenRouter → Groq → Nvidia → DeepSeek.
Structured output: json_mode requests response_format/response_mime_type where
supported, with per-(provider, model) cached fallback to plain mode.
Fallback chain: if one provider's quota is exhausted, the next is tried automatically
until all are exhausted; per-provider 60s cooldown avoids hammering, expired entries
are retried so refreshed quota is reused. Embeddings: Gemini (others have no stable free embeddings)
"""
import os
import time

PROVIDER_ORDER = ["gemini", "openrouter", "groq", "nvidia", "deepseek"]

# Negative capability cache: (provider, model) pairs known NOT to support
# structured output. Avoids re-paying a failing attempt on every call.
_NO_JSON_MODE: set = set()


def _structured_unsupported(e: Exception) -> bool:
    """True when the error clearly means 'this model rejects response_format'."""
    m = str(e).lower()
    if _is_quota(e):
        return False  # quota is handled by the chain, never downgrade on it
    markers = ("response_format", "response_mime_type", "json mode", "json_mode",
               "not supported", "unsupported", "unknown parameter", "invalid parameter")
    return any(x in m for x in markers)

# Per-provider quota-exhaustion cooldown: name -> unix timestamp until which we skip it.
# In-memory only (resets on restart); keeps latency low when a provider is down while
# still auto-reusing it once the cooldown expires / quota refreshes.
_COOLDOWN: dict = {}


def _cooldown_seconds() -> float:
    try:
        return float(os.getenv("LLM_COOLDOWN_SECONDS", "60"))
    except Exception:
        return 60.0


def _in_cooldown(name: str) -> bool:
    try:
        return time.time() < float(_COOLDOWN.get(name, 0))
    except Exception:
        return False


def _mark_cooldown(name: str) -> None:
    try:
        _COOLDOWN[name] = time.time() + _cooldown_seconds()
    except Exception:
        pass


def _clear_cooldown(name: str) -> None:
    try:
        _COOLDOWN.pop(name, None)
    except Exception:
        pass


def _is_quota(e: Exception) -> bool:
    """Single choke point for quota detection (429/quota/rate/402/resource_exhausted)."""
    try:
        from utils.json_parse import is_quota_error
        return is_quota_error(e)
    except Exception:
        m = str(e).lower()
        return "429" in m or "quota" in m or "resource_exhausted" in m or "exhausted" in m


def has_any_llm() -> bool:
    """True if ANY allowed chat provider key is configured (respects LLM_ONLY)."""
    return any(
        _allowed(name) and os.getenv(key)
        for name, key in (
            ("openrouter", "OPENROUTER_API_KEY"),
            ("gemini", "GEMINI_API_KEY"),
            ("groq", "GROQ_API_KEY"),
            ("nvidia", "NVIDIA_API_KEY"),
            ("deepseek", "DEEPSEEK_API_KEY"),
        )
    )


def _only_set() -> set | None:
    """LLM_ONLY=gemini (or comma list like 'gemini,groq') constrains the chain to
    those providers. Unset/empty = all configured providers. Unknown names match nothing."""
    raw = os.getenv("LLM_ONLY", "")
    if not raw.strip():
        return None
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def _allowed(name: str) -> bool:
    only = _only_set()
    return True if only is None else name in only

def _groq_client():
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key, timeout=30.0)
    except Exception as e:
        print(f"groq client init failed: {e}")
        return None

def _finish_reason_openai(resp) -> str | None:
    try:
        return resp.choices[0].finish_reason or None
    except Exception:
        return None


def _usage_openai(resp, info: dict | None) -> None:
    """Best-effort token counts from an OpenAI-compatible response."""
    if info is None:
        return
    try:
        u = getattr(resp, "usage", None)
        if u is not None:
            info["tokens_in"] = getattr(u, "prompt_tokens", None)
            info["tokens_out"] = getattr(u, "completion_tokens", None)
    except Exception:
        pass


def _maybe_json_kwargs(provider: str, model: str, kwargs: dict, json_mode: bool) -> bool:
    """Attach response_format when requested and not known-unsupported.
    Returns True if structured mode was attempted."""
    if json_mode and (provider, model) not in _NO_JSON_MODE:
        kwargs["response_format"] = {"type": "json_object"}
        return True
    return False


def _call_groq(prompt: str, model: str, temperature: float = 0.2, *, json_mode: bool = False, max_output_tokens: int | None = None, info: dict | None = None) -> str:
    client = _groq_client()
    if not client:
        raise RuntimeError("Missing GROQ_API_KEY")
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a JSON generator. Return ONLY valid JSON, no markdown, no prose."},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "timeout": 30.0,
    }
    if max_output_tokens:
        kwargs["max_tokens"] = max_output_tokens
    tried_structured = _maybe_json_kwargs("groq", model, kwargs, json_mode)
    try:
        resp = client.chat.completions.create(**kwargs)  # type: ignore
    except Exception as e:
        if tried_structured and _structured_unsupported(e):
            _NO_JSON_MODE.add(("groq", model))
            kwargs.pop("response_format", None)
            resp = client.chat.completions.create(**kwargs)  # type: ignore
        else:
            raise
    if info is not None:
        info.update({"provider": "groq", "model": model,
                     "finish_reason": _finish_reason_openai(resp),
                     "json_mode": tried_structured})
        _usage_openai(resp, info)
    return (resp.choices[0].message.content or "").strip()

def _nvidia_timeout() -> float:
    # Ultra-550b with thinking mode needs headroom on big prompts (Analyzer).
    try:
        return float(os.getenv("NVIDIA_TIMEOUT_SECONDS", "120"))
    except Exception:
        return 120.0


def _nvidia_client():
    key = os.getenv("NVIDIA_API_KEY", "")
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=key, timeout=_nvidia_timeout())
    except Exception as e:
        print(f"nvidia client init failed: {e}")
        return None

def _call_nvidia(prompt: str, model: str, temperature: float = 0.2, stream: bool = False, image_url: str | None = None, reasoning_effort: str | None = None, *, json_mode: bool = False, max_output_tokens: int | None = None, info: dict | None = None) -> str:
    client = _nvidia_client()
    if not client:
        raise RuntimeError("Missing NVIDIA_API_KEY")
    # Nemotron 3 Ultra requires enable_thinking via chat_template_kwargs
    is_nemotron = "nemotron" in model.lower()
    if image_url:
        content: list = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": image_url}}]
        messages = [{"role": "user", "content": content}]
    else:
        messages = [
            {"role": "system", "content": "You are a JSON generator. Return ONLY valid JSON, no markdown, no prose."},
            {"role": "user", "content": prompt},
        ]
    kwargs: dict = {"model": model, "messages": messages, "temperature": temperature, "timeout": _nvidia_timeout()}
    if max_output_tokens:
        kwargs["max_tokens"] = max_output_tokens
    if is_nemotron:
        # Nemotron uses chat_template_kwargs.enable_thinking and top_p
        kwargs.setdefault("max_tokens", 16384)
        kwargs["top_p"] = 0.95
        kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": True}}
        if stream:
            kwargs["stream"] = True
    else:
        if image_url is None:
            kwargs.setdefault("max_tokens", 16384)
            if reasoning_effort:
                kwargs["extra_body"] = {"reasoning_effort": reasoning_effort}
        else:
            kwargs.setdefault("max_tokens", 4096)
        if stream:
            kwargs["stream"] = True
    tried_structured = False
    if json_mode and not stream and ("nvidia", model) not in _NO_JSON_MODE:
        kwargs["response_format"] = {"type": "json_object"}
        tried_structured = True

    def _finish(resp) -> str | None:
        return _finish_reason_openai(resp)

    if stream:
        resp = client.chat.completions.create(**kwargs)  # type: ignore
        out = ""
        reasoning_out = ""
        for chunk in resp:  # type: ignore
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            # Nemotron returns reasoning in reasoning_content
            reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
            if reasoning:
                reasoning_out += reasoning
            if delta.content is not None:
                out += delta.content
        return (reasoning_out + out).strip() if reasoning_out else out.strip()
    try:
        resp = client.chat.completions.create(**kwargs)  # type: ignore
    except Exception as e:
        if tried_structured and _structured_unsupported(e):
            _NO_JSON_MODE.add(("nvidia", model))
            kwargs.pop("response_format", None)
            resp = client.chat.completions.create(**kwargs)  # type: ignore
        else:
            raise
    if info is not None:
        info.update({"provider": "nvidia", "model": model,
                     "finish_reason": _finish(resp), "json_mode": tried_structured})
        _usage_openai(resp, info)
    # Handle reasoning for Nemotron non-streaming
    content = resp.choices[0].message.content or ""
    reasoning = getattr(resp.choices[0].message, "reasoning_content", None) or getattr(resp.choices[0].message, "reasoning", None)
    if reasoning and is_nemotron:
        return (reasoning + "\n" + content).strip()
    return content.strip()

def call_nvidia_vision(prompt: str, image_url: str, model: str | None = None, reasoning_effort: str = "max", stream: bool = False) -> str:
    """Direct Kimi vision helper — uses moonshotai/kimi-k3 by default, supports image_url + reasoning_effort"""
    mdl = model or os.getenv("NVIDIA_MODEL", "moonshotai/kimi-k3")
    # Kimi K3 is vision+reasoning, use max reasoning for image tasks
    return _call_nvidia(prompt, mdl, temperature=1.0, stream=stream, image_url=image_url, reasoning_effort=reasoning_effort)

def _openrouter_client():
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key, timeout=30.0)
    except Exception as e:
        print(f"openrouter client init failed: {e}")
        return None

def _call_openrouter(prompt: str, model: str, temperature: float = 0.2, max_tokens: int | None = None, *, json_mode: bool = False, max_output_tokens: int | None = None, info: dict | None = None) -> str:
    client = _openrouter_client()
    if not client:
        raise RuntimeError("Missing OPENROUTER_API_KEY")
    try:
        kwargs: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a JSON generator. Return ONLY valid JSON, no markdown, no prose."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "timeout": 30.0,
        }
        limit = max_output_tokens if max_output_tokens else max_tokens
        if limit:
            kwargs["max_tokens"] = limit
        tried_structured = _maybe_json_kwargs("openrouter", model, kwargs, json_mode)
        try:
            resp = client.chat.completions.create(**kwargs)  # type: ignore
        except Exception as e:
            if tried_structured and _structured_unsupported(e):
                _NO_JSON_MODE.add(("openrouter", model))
                kwargs.pop("response_format", None)
                resp = client.chat.completions.create(**kwargs)  # type: ignore
            else:
                raise
        if info is not None:
            info.update({"provider": "openrouter", "model": model,
                         "finish_reason": _finish_reason_openai(resp),
                         "json_mode": tried_structured})
            _usage_openai(resp, info)
        content = resp.choices[0].message.content or ""
        return content.strip()
    except Exception as e:
        raise

def _call_llm_inner(prompt: str, temperature: float = 0.2, max_tokens: int | None = None, *, json_mode: bool = False, max_output_tokens: int | None = None, info: dict | None = None) -> str:
    """Chain core — see call_llm (public wrapper adds cassettes + telemetry)."""
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    nvidia_model = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-flash-0731")
    groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    or_primary = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    or_fallback = os.getenv("OPENROUTER_FALLBACK", "openrouter/free")

    last_err: Exception | None = None
    saw_quota = False
    tried_any = False
    attempts = 0

    def _track(sub: dict | None):
        # Attribute fallthrough: when an earlier provider failed, stamp its
        # error on the winning call so telemetry can record fallback_reason.
        if sub is not None and last_err is not None:
            sub["fallback_reason"] = str(last_err)[:500]
        if info is not None:
            attempts_local = info.get("attempts", 0) + 1
            info.update({"attempts": attempts_local})
            if sub:
                info.update(sub)

    # 0. Gemini first (primary) — falls through on quota/failure
    if _allowed("gemini") and not _in_cooldown("gemini"):
        tried_any = True
        try:
            from main import call_gemini
            sub: dict = {}
            text = call_gemini(prompt, response_mime_type="application/json" if json_mode else None,
                               max_output_tokens=max_output_tokens, info=sub)
            _track(sub)
            _clear_cooldown("gemini")
            return text
        except Exception as e:
            last_err = e
            if _is_quota(e):
                saw_quota = True
                _mark_cooldown("gemini")
                print(f"gemini quota exhausted: {e} — trying next provider")
            else:
                print(f"gemini failed, trying openrouter: {e}")
    elif _allowed("gemini"):
        print("gemini in cooldown — skipping to next provider")

    # 1. OpenRouter (free daily pool) — primary then fallback model
    if _allowed("openrouter") and os.getenv("OPENROUTER_API_KEY") and not _in_cooldown("openrouter"):
        tried_any = True
        try:
            sub = {}
            text = _call_openrouter(prompt, or_primary, temperature, max_tokens,
                                    json_mode=json_mode, max_output_tokens=max_output_tokens, info=sub)
            _track(sub)
            _clear_cooldown("openrouter")
            return text
        except Exception as e:
            last_err = e
            if _is_quota(e):
                saw_quota = True
            print(f"openrouter primary {or_primary} failed ({type(e).__name__}): {e} — trying fallback/next")
            if or_fallback and or_fallback != or_primary:
                try:
                    print(f"trying openrouter fallback {or_fallback}")
                    sub = {}
                    text = _call_openrouter(prompt, or_fallback, temperature, max_tokens,
                                            json_mode=json_mode, max_output_tokens=max_output_tokens, info=sub)
                    _track(sub)
                    _clear_cooldown("openrouter")
                    return text
                except Exception as e2:
                    last_err = e2
                    if _is_quota(e2):
                        saw_quota = True
                    print(f"openrouter fallback {or_fallback} failed: {e2} — trying next provider")
            if _is_quota(last_err):
                _mark_cooldown("openrouter")
            # fall through to Groq (do NOT raise yet)
    elif _allowed("openrouter") and os.getenv("OPENROUTER_API_KEY"):
        print("openrouter in cooldown — skipping to next provider")

    # 2. Groq (low token budget remaining)
    if _allowed("groq") and os.getenv("GROQ_API_KEY") and not _in_cooldown("groq"):
        tried_any = True
        try:
            sub = {}
            text = _call_groq(prompt, groq_model, temperature,
                              json_mode=json_mode, max_output_tokens=max_output_tokens, info=sub)
            _track(sub)
            _clear_cooldown("groq")
            return text
        except Exception as e:
            last_err = e
            if _is_quota(e):
                saw_quota = True
                _mark_cooldown("groq")
            print(f"groq {groq_model} failed: {e} — trying next provider")
    elif _allowed("groq") and os.getenv("GROQ_API_KEY"):
        print("groq in cooldown — skipping to next provider")

    # 3. Nvidia (degraded: frequent timeouts, capped at 30s)
    if _allowed("nvidia") and os.getenv("NVIDIA_API_KEY") and not _in_cooldown("nvidia"):
        tried_any = True
        try:
            is_analyzer = "AppSpec" in prompt or "Analyzer" in prompt
            sub = {}
            text = _call_nvidia(prompt, nvidia_model, temperature, reasoning_effort="high" if is_analyzer else None,
                                json_mode=json_mode, max_output_tokens=max_output_tokens, info=sub)
            _track(sub)
            _clear_cooldown("nvidia")
            return text
        except Exception as e:
            last_err = e
            if _is_quota(e):
                saw_quota = True
                _mark_cooldown("nvidia")
            print(f"nvidia {nvidia_model} failed: {e} — trying next provider")
    elif _allowed("nvidia") and os.getenv("NVIDIA_API_KEY"):
        print("nvidia in cooldown — skipping to next provider")

    # 4. DeepSeek (inactive unless a key is added — free skip)
    if _allowed("deepseek") and os.getenv("DEEPSEEK_API_KEY") and not _in_cooldown("deepseek"):
        tried_any = True
        try:
            sub = {}
            text = _call_deepseek(prompt, deepseek_model, temperature,
                                  json_mode=json_mode, max_output_tokens=max_output_tokens, info=sub)
            _track(sub)
            _clear_cooldown("deepseek")
            return text
        except Exception as e:
            last_err = e
            if _is_quota(e):
                saw_quota = True
                _mark_cooldown("deepseek")
            print(f"deepseek {deepseek_model} failed: {e}")
            # fall through
    elif _allowed("deepseek") and os.getenv("DEEPSEEK_API_KEY"):
        print("deepseek in cooldown — no providers left")

    if not tried_any and not has_any_llm():
        raise RuntimeError("All LLM providers unconfigured (gemini→openrouter→groq→nvidia→deepseek)")
    if saw_quota:
        raise RuntimeError(f"429 All LLM providers exhausted (gemini→openrouter→groq→nvidia→deepseek): {last_err}")
    raise RuntimeError(f"All LLM providers failed (gemini→openrouter→groq→nvidia→deepseek): {last_err}")

def _call_llm_with_meta_inner(prompt: str, temperature: float = 0.2, max_tokens: int | None = None, *, json_mode: bool = False, max_output_tokens: int | None = None, info: dict | None = None) -> tuple[str, dict]:
    """Chain core — see call_llm_with_meta (public wrapper adds cassettes + telemetry)."""
    primary = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    fallback = os.getenv("OPENROUTER_FALLBACK", "openrouter/free")
    groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    nvidia_model = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-flash-0731")
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    last_err: Exception | None = None
    saw_quota = False
    tried_any = False

    def _track(sub: dict | None):
        # Attribute fallthrough: when an earlier provider failed, stamp its
        # error on the winning call so telemetry can record fallback_reason.
        if sub is not None and last_err is not None:
            sub["fallback_reason"] = str(last_err)[:500]
        if info is not None:
            attempts_local = info.get("attempts", 0) + 1
            info.update({"attempts": attempts_local})
            if sub:
                info.update(sub)

    # 0. Gemini first (primary) — falls through on quota/failure
    try:
        if _allowed("gemini") and not _in_cooldown("gemini"):
            tried_any = True
            from main import call_gemini
            sub: dict = {}
            text = call_gemini(prompt, response_mime_type="application/json" if json_mode else None,
                               max_output_tokens=max_output_tokens, info=sub)
            _track(sub)
            _clear_cooldown("gemini")
            return text, {"source": "gemini", "model": os.getenv("GEMINI_MODEL", "gemini-3.6-flash")}
        if _allowed("gemini"):
            print("gemini in cooldown — skipping to next provider")
    except Exception as e:
        last_err = e
        if _is_quota(e):
            saw_quota = True
            _mark_cooldown("gemini")
            print(f"gemini quota exhausted: {e} — trying next provider")
        else:
            print(f"gemini with_meta failed: {e}, trying openrouter")

    # 1. OpenRouter (free daily pool) — primary then fallback model
    if _allowed("openrouter") and os.getenv("OPENROUTER_API_KEY") and not _in_cooldown("openrouter"):
        tried_any = True
        try:
            sub = {}
            text = _call_openrouter(prompt, primary, temperature, max_tokens,
                                    json_mode=json_mode, max_output_tokens=max_output_tokens, info=sub)
            _track(sub)
            _clear_cooldown("openrouter")
            return text, {"source": "openrouter", "model": primary}
        except Exception as e:
            last_err = e
            if _is_quota(e):
                saw_quota = True
            print(f"openrouter primary {primary} failed: {e} — trying fallback/next")
            if fallback and fallback != primary:
                try:
                    sub = {}
                    text = _call_openrouter(prompt, fallback, temperature, max_tokens,
                                            json_mode=json_mode, max_output_tokens=max_output_tokens, info=sub)
                    _track(sub)
                    _clear_cooldown("openrouter")
                    return text, {"source": "openrouter", "model": fallback}
                except Exception as e2:
                    last_err = e2
                    if _is_quota(e2):
                        saw_quota = True
                    print(f"openrouter fallback {fallback} failed: {e2} — trying next provider")
            if _is_quota(last_err):
                _mark_cooldown("openrouter")
    if _allowed("groq") and os.getenv("GROQ_API_KEY") and not _in_cooldown("groq"):
        tried_any = True
        try:
            sub = {}
            text = _call_groq(prompt, groq_model, temperature,
                              json_mode=json_mode, max_output_tokens=max_output_tokens, info=sub)
            _track(sub)
            _clear_cooldown("groq")
            return text, {"source": "groq", "model": groq_model}
        except Exception as e:
            last_err = e
            if _is_quota(e):
                saw_quota = True
                _mark_cooldown("groq")
            print(f"groq with_meta {groq_model} failed: {e}, trying nvidia")
    elif _allowed("groq") and os.getenv("GROQ_API_KEY"):
        print("groq in cooldown — skipping to next provider")
    if _allowed("nvidia") and os.getenv("NVIDIA_API_KEY") and not _in_cooldown("nvidia"):
        tried_any = True
        try:
            is_analyzer = "AppSpec" in prompt or "Analyzer" in prompt
            sub = {}
            text = _call_nvidia(prompt, nvidia_model, temperature, reasoning_effort="high" if is_analyzer else None,
                                json_mode=json_mode, max_output_tokens=max_output_tokens, info=sub)
            _track(sub)
            _clear_cooldown("nvidia")
            return text, {"source": "nvidia", "model": nvidia_model}
        except Exception as e:
            last_err = e
            if _is_quota(e):
                saw_quota = True
                _mark_cooldown("nvidia")
            print(f"nvidia with_meta {nvidia_model} failed: {e}, trying deepseek")
    elif _allowed("nvidia") and os.getenv("NVIDIA_API_KEY"):
        print("nvidia in cooldown — skipping to next provider")
    if _allowed("deepseek") and os.getenv("DEEPSEEK_API_KEY") and not _in_cooldown("deepseek"):
        tried_any = True
        try:
            sub = {}
            text = _call_deepseek(prompt, deepseek_model, temperature,
                                  json_mode=json_mode, max_output_tokens=max_output_tokens, info=sub)
            _track(sub)
            _clear_cooldown("deepseek")
            return text, {"source": "deepseek", "model": deepseek_model}
        except Exception as e:
            last_err = e
            if _is_quota(e):
                saw_quota = True
                _mark_cooldown("deepseek")
            print(f"deepseek with_meta {deepseek_model} failed: {e}")
    elif _allowed("deepseek") and os.getenv("DEEPSEEK_API_KEY"):
        print("deepseek in cooldown — no providers left")
    if not tried_any and not has_any_llm():
        raise RuntimeError("All LLM providers unconfigured (gemini→openrouter→groq→nvidia→deepseek)")
    if saw_quota:
        raise RuntimeError(f"429 All LLM providers exhausted (gemini→openrouter→groq→nvidia→deepseek): {last_err}")
    raise RuntimeError(f"All LLM providers failed (gemini→openrouter→groq→nvidia→deepseek): {last_err}")

def _record_gateway_call(sub: dict | None, elapsed_s: float, telemetry: dict | None) -> None:
    """Best-effort llm_calls row for one successful chain call. Never raises."""
    try:
        if os.getenv("LLM_TELEMETRY", "1") != "1":
            return
        from services import telemetry as _tm
        ctx = telemetry or {}
        sub = sub or {}
        _tm.record_llm_call(
            provider=sub.get("provider") or "unknown",
            model=sub.get("model"),
            tokens_in=sub.get("tokens_in"),
            tokens_out=sub.get("tokens_out"),
            latency_ms=int(elapsed_s * 1000),
            finish_reason=sub.get("finish_reason"),
            wish_id=ctx.get("wish_id"),
            step_key=ctx.get("step_key"),
            agent=ctx.get("agent"),
            prompt_version=ctx.get("prompt_version"),
            parse_outcome=ctx.get("parse_outcome"),
            repair_used=bool(ctx.get("repair_used", False)),
            fallback_reason=sub.get("fallback_reason") or ctx.get("fallback_reason"),
        )
    except Exception:
        pass


def call_llm(prompt: str, temperature: float = 0.2, max_tokens: int | None = None, *, json_mode: bool = False, max_output_tokens: int | None = None, info: dict | None = None, telemetry: dict | None = None) -> str:
    """
    Gemini → OpenRouter → Groq → Nvidia → DeepSeek — fall through until all exhausted.
    Gemini is primary; others are fallback in that order.
    Quota-exhausted providers get a 60s cooldown (LLM_COOLDOWN_SECONDS) then are retried,
    so refreshed quota is reused automatically. Raises 429 only when every configured
    provider is exhausted/cooldown; raises unconfigured only when no key is set at all.
    max_tokens bounds OpenRouter output (reasoning dribble guard); other providers ignore it.
    json_mode requests structured output where supported (auto-fallback per model).
    max_output_tokens caps output on every provider that accepts it.
    info, when given, is populated with {provider, model, finish_reason, json_mode, attempts}.
    telemetry, when given, carries {wish_id, step_key, agent, prompt_version} context
    recorded into llm_calls (kill-switch: LLM_TELEMETRY=0). Cassettes: LLM_CASSETTES=
    record saves prompt→response under evals/cassettes; replay serves saved responses
    without hitting providers (miss falls through to live).
    """
    from services import cassettes as _cas
    hit = _cas.replay_lookup(prompt, temperature=temperature, json_mode=json_mode,
                             max_output_tokens=max_output_tokens, max_tokens=max_tokens)
    if hit is not None:
        if info is not None:
            info.update({"attempts": info.get("attempts", 0) + 1, "provider": "cassette",
                         "model": (hit.get("meta") or {}).get("model") or "replay",
                         "finish_reason": "replay", "json_mode": json_mode})
        return hit["text"]
    t0 = time.perf_counter()
    sub: dict = {}
    text = _call_llm_inner(prompt, temperature, max_tokens, json_mode=json_mode,
                           max_output_tokens=max_output_tokens, info=sub)
    if info is not None:
        info.update(sub)
    _cas.record_save(prompt, text, meta={"provider": sub.get("provider"), "model": sub.get("model")},
                     temperature=temperature, json_mode=json_mode,
                     max_output_tokens=max_output_tokens, max_tokens=max_tokens)
    _record_gateway_call(sub, time.perf_counter() - t0, telemetry)
    return text


def call_llm_with_meta(prompt: str, temperature: float = 0.2, max_tokens: int | None = None, *, json_mode: bool = False, max_output_tokens: int | None = None, info: dict | None = None, telemetry: dict | None = None) -> tuple[str, dict]:
    """Returns (text, meta) where meta has source/model for _meta badge — same chain,
    cooldown, info, telemetry and cassette behavior as call_llm."""
    from services import cassettes as _cas
    hit = _cas.replay_lookup(prompt, temperature=temperature, json_mode=json_mode,
                             max_output_tokens=max_output_tokens, max_tokens=max_tokens)
    if hit is not None:
        meta = dict(hit.get("meta") or {})
        meta.setdefault("source", "cassette")
        meta.setdefault("model", "replay")
        if info is not None:
            info.update({"attempts": info.get("attempts", 0) + 1, "provider": "cassette",
                         "model": meta.get("model"), "finish_reason": "replay",
                         "json_mode": json_mode})
        return hit["text"], meta
    t0 = time.perf_counter()
    sub: dict = {}
    text, meta = _call_llm_with_meta_inner(prompt, temperature, max_tokens, json_mode=json_mode,
                                           max_output_tokens=max_output_tokens, info=sub)
    if info is not None:
        info.update(sub)
    _cas.record_save(prompt, text, meta=meta,
                     temperature=temperature, json_mode=json_mode,
                     max_output_tokens=max_output_tokens, max_tokens=max_tokens)
    _record_gateway_call(sub, time.perf_counter() - t0, telemetry)
    return text, meta


def embed_texts(texts: list[str]) -> list[list[float]]:
    """OpenRouter embeddings first, then Gemini. Returns list of vectors (3072d padded/truncated for pgvector)."""
    # Try OpenRouter embeddings only if explicitly configured and model exists
    # Default embed model is empty to avoid calling non-existent qwen/qwen3-embedding:free
    embed_model = os.getenv("OPENROUTER_EMBED_MODEL", "")
    if os.getenv("OPENROUTER_API_KEY") and embed_model and embed_model.strip():
        try:
            client = _openrouter_client()
            if client:
                resp = client.embeddings.create(model=embed_model, input=texts)
                out = []
                for item in resp.data:
                    vals = getattr(item, 'embedding', None) or getattr(item, 'values', None) or []
                    if isinstance(item, dict):
                        vals = item.get('embedding') or item.get('values') or []
                    if len(vals) > 3072: vals = vals[:3072]
                    elif len(vals) < 3072: vals = vals + [0.0]*(3072-len(vals))
                    out.append(vals)
                if out:
                    return out
        except Exception as e:
            print(f"openrouter embed {embed_model} failed, fallback to gemini: {e}")
    # Fallback to Gemini direct (avoid circular import via rag)
    try:
        from google import genai
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            return [[0.0]*3072 for _ in texts]
        try:
            client = genai.Client(api_key=key, http_options={"timeout": 60000})
        except Exception:
            client = genai.Client(api_key=key)
        out = []
        for t in texts:
            r = client.models.embed_content(model="gemini-embedding-001", contents=t)
            vals = getattr(r, 'embeddings', [{}])[0]
            vals = getattr(vals, 'values', [0]*3072) if hasattr(vals,'values') else vals.get('values',[0]*3072) if isinstance(vals, dict) else [0]*3072
            if len(vals) > 3072: vals = vals[:3072]
            elif len(vals) < 3072: vals = vals + [0.0]*(3072-len(vals))
            out.append(vals)
        return out
    except Exception as e:
        print(f"gemini embed fallback failed: {e}")
        return [[0.0]*3072 for _ in texts]

def _deepseek_client():
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url="https://api.deepseek.com/v1", api_key=key, timeout=30.0)
    except Exception as e:
        print(f"deepseek client init failed: {e}")
        return None

def _call_deepseek(prompt: str, model: str, temperature: float = 0.2, *, json_mode: bool = False, max_output_tokens: int | None = None, info: dict | None = None) -> str:
    client = _deepseek_client()
    if not client:
        raise RuntimeError("Missing DEEPSEEK_API_KEY")
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a JSON generator. Return ONLY valid JSON, no markdown, no prose."},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "timeout": 30.0,
    }
    if max_output_tokens:
        kwargs["max_tokens"] = max_output_tokens
    tried_structured = _maybe_json_kwargs("deepseek", model, kwargs, json_mode)
    try:
        resp = client.chat.completions.create(**kwargs)  # type: ignore
    except Exception as e:
        if tried_structured and _structured_unsupported(e):
            _NO_JSON_MODE.add(("deepseek", model))
            kwargs.pop("response_format", None)
            resp = client.chat.completions.create(**kwargs)  # type: ignore
        else:
            raise
    if info is not None:
        info.update({"provider": "deepseek", "model": model,
                     "finish_reason": _finish_reason_openai(resp),
                     "json_mode": tried_structured})
        _usage_openai(resp, info)
    return (resp.choices[0].message.content or "").strip()

def get_llm_status() -> dict:
    """For /health: which provider is configured and reachable"""
    has_deepseek = bool(os.getenv("DEEPSEEK_API_KEY"))
    has_groq = bool(os.getenv("GROQ_API_KEY"))
    has_nvidia = bool(os.getenv("NVIDIA_API_KEY"))
    has_or = bool(os.getenv("OPENROUTER_API_KEY"))
    has_gem = bool(os.getenv("GEMINI_API_KEY"))
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat") if has_deepseek else None
    groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b") if has_groq else None
    nvidia_model = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-flash-0731") if has_nvidia else None
    primary = os.getenv("OPENROUTER_MODEL", "openrouter/free") if has_or else None
    gem_model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash") if has_gem else None
    quota = None
    if has_or:
        try:
            import httpx
            key = os.getenv("OPENROUTER_API_KEY", "")
            r = httpx.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}, timeout=3.0)
            if r.status_code == 200:
                j = r.json()
                quota = {"raw": j.get("data", j) if isinstance(j, dict) else str(j)[:500]}
        except Exception as e:
            quota = {"error": str(e)[:200]}
    # Priority: Gemini first, then OpenRouter -> Groq -> Nvidia -> DeepSeek
    if has_gem:
        primary_src = "gemini"
    elif has_or:
        primary_src = "openrouter"
    elif has_groq:
        primary_src = "groq"
    elif has_nvidia:
        primary_src = "nvidia"
    elif has_deepseek:
        primary_src = "deepseek"
    else:
        primary_src = "none"
    def _cd(name: str):
        try:
            until = float(_COOLDOWN.get(name, 0))
            now = time.time()
            return {"in_cooldown": now < until, "cooldown_until": until if now < until else None}
        except Exception:
            return {"in_cooldown": False, "cooldown_until": None}
    return {
        "deepseek": {"configured": has_deepseek, "model": deepseek_model, **_cd("deepseek")},
        "groq": {"configured": has_groq, "model": groq_model, **_cd("groq")},
        "nvidia": {"configured": has_nvidia, "model": nvidia_model, **_cd("nvidia")},
        "openrouter": {"configured": has_or, "model": primary, "fallback": os.getenv("OPENROUTER_FALLBACK", "openrouter/free") if has_or else None, "quota": quota, **_cd("openrouter")},
        "gemini": {"configured": has_gem, "model": gem_model, **_cd("gemini")},
        "primary": primary_src,
        "order": PROVIDER_ORDER,
        "cooldown_seconds": _cooldown_seconds(),
        "only": sorted(_only_set()) if _only_set() is not None else None,
    }
