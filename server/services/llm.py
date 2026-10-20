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


class ByokError(RuntimeError):
    """The account's own key failed. Do not mask it with mock/template fallbacks."""

    byok_error = True


def is_byok_error(exc: BaseException) -> bool:
    return bool(getattr(exc, "byok_error", False))


def has_any_llm() -> bool:
    """True if ANY allowed chat provider is configured (respects LLM_ONLY).

    Also true when the current account has a saved BYOK key, so a deployment
    with no shared pool can still build for users who brought their own key.
    """
    if any(
        _allowed(name) and os.getenv(key)
        for name, key in (
            ("openrouter", "OPENROUTER_API_KEY"),
            ("gemini", "GEMINI_API_KEY"),
            ("groq", "GROQ_API_KEY"),
            ("nvidia", "NVIDIA_API_KEY"),
            ("deepseek", "DEEPSEEK_API_KEY"),
        )
    ):
        return True
    try:
        from userkeys import using_byok
        return using_byok()
    except Exception:
        return False


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

def _groq_client(key: str | None = None):
    key = (key or os.getenv("GROQ_API_KEY", "")).strip()
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


def _call_groq(prompt: str, model: str, temperature: float = 0.2, *, json_mode: bool = False, max_output_tokens: int | None = None, info: dict | None = None, key: str | None = None) -> str:
    client = _groq_client(key)
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


def _nvidia_client(key: str | None = None):
    key = (key or os.getenv("NVIDIA_API_KEY", "")).strip()
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=key, timeout=_nvidia_timeout())
    except Exception as e:
        print(f"nvidia client init failed: {e}")
        return None

def _call_nvidia(prompt: str, model: str, temperature: float = 0.2, stream: bool = False, image_url: str | None = None, reasoning_effort: str | None = None, *, json_mode: bool = False, max_output_tokens: int | None = None, info: dict | None = None, key: str | None = None) -> str:
    client = _nvidia_client(key)
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

def _openrouter_client(key: str | None = None):
    key = (key or os.getenv("OPENROUTER_API_KEY", "")).strip()
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key, timeout=30.0)
    except Exception as e:
        print(f"openrouter client init failed: {e}")
        return None

def _call_openrouter(prompt: str, model: str, temperature: float = 0.2, max_tokens: int | None = None, *, json_mode: bool = False, max_output_tokens: int | None = None, info: dict | None = None, key: str | None = None) -> str:
    client = _openrouter_client(key)
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

def _call_openai_compatible(prompt: str, model: str, api_key: str, base_url: str,
                            temperature: float = 0.2, *, json_mode: bool = False,
                            max_output_tokens: int | None = None,
                            info: dict | None = None,
                            provider_name: str = "custom") -> str:
    """Generic OpenAI-compatible chat call used by BYOK OpenAI/custom keys."""
    if not api_key:
        raise RuntimeError(f"Missing {provider_name} API key")
    if not base_url:
        raise RuntimeError(f"Missing {provider_name} base URL")
    from openai import OpenAI
    client_kwargs: dict = {"base_url": base_url, "api_key": api_key, "timeout": 60.0}
    if provider_name == "custom":
        import httpx
        # The endpoint is user-supplied: never follow redirects, or a public
        # HTTPS host could bounce the backend to an internal address (SSRF).
        client_kwargs["http_client"] = httpx.Client(follow_redirects=False, timeout=60.0)
    client = OpenAI(**client_kwargs)
    system = ("You are a JSON generator. Return ONLY valid JSON, no markdown, no prose."
              if json_mode else "You are a precise software planning assistant.")
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "timeout": 60.0,
    }
    if max_output_tokens:
        kwargs["max_tokens"] = max_output_tokens
    tried_structured = _maybe_json_kwargs(provider_name, model, kwargs, json_mode)
    try:
        try:
            resp = client.chat.completions.create(**kwargs)  # type: ignore
        except Exception as e:
            if tried_structured and _structured_unsupported(e):
                _NO_JSON_MODE.add((provider_name, model))
                kwargs.pop("response_format", None)
                resp = client.chat.completions.create(**kwargs)  # type: ignore
            else:
                raise
        if info is not None:
            info.update({"provider": provider_name, "model": model,
                         "finish_reason": _finish_reason_openai(resp),
                         "json_mode": tried_structured})
            _usage_openai(resp, info)
        return (resp.choices[0].message.content or "").strip()
    finally:
        if provider_name == "custom":
            client.close()


def _call_anthropic(prompt: str, model: str, api_key: str,
                    temperature: float = 0.2, *, json_mode: bool = False,
                    max_output_tokens: int | None = None,
                    info: dict | None = None) -> str:
    """Native Anthropic Messages API (BYOK only)."""
    if not api_key:
        raise RuntimeError("Missing Anthropic API key")
    import httpx
    system = ("You are a JSON generator. Return ONLY valid JSON, no markdown, no prose."
              if json_mode else "You are a precise software planning assistant.")
    body = {
        "model": model,
        "max_tokens": max_output_tokens or 4096,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json=body, timeout=60.0,
    )
    if r.status_code >= 400:
        try:
            detail = (r.json().get("error") or {}).get("message") or r.text[:300]
        except Exception:
            detail = r.text[:300]
        raise RuntimeError(f"Anthropic {r.status_code}: {detail}")
    data = r.json()
    blocks = data.get("content") or []
    text = "".join(b.get("text", "") for b in blocks
                   if isinstance(b, dict) and b.get("type") == "text").strip()
    if not text:
        raise RuntimeError("Anthropic returned an empty response")
    if info is not None:
        usage = data.get("usage") or {}
        info.update({"provider": "anthropic", "model": model,
                     "finish_reason": data.get("stop_reason"),
                     "json_mode": json_mode,
                     "tokens_in": usage.get("input_tokens"),
                     "tokens_out": usage.get("output_tokens")})
    return text


def _byok_rows() -> list[dict]:
    """Saved keys for the request's account. Empty when none / table missing.

    Background builds pin a snapshot at task start (see ``userkeys``), which
    also keeps a build from changing keys midway through.
    """
    try:
        from userkeys import UserKeysUnavailable
    except Exception:
        return []
    try:
        from userkeys import byok_snapshot, current_user, list_keys
        snap = byok_snapshot()
        if snap is not None:
            return list(snap)
        return list_keys(current_user())
    except UserKeysUnavailable:
        # Migration 013 not applied: no keys can exist yet -> shared pool.
        return []
    except Exception as e:
        msg = str(e)
        if "013" in msg or "user_llm_keys" in msg:
            return []
        print(f"BYOK lookup failed: {msg[:160]}")
        # We cannot tell whether this account has keys. Fail instead of
        # silently spending the shared budget on their behalf.
        raise ByokError(
            "Could not read your saved LLM key — try again in a moment. "
            "No shared pool was used."
        ) from e


def _byok_model(provider: str, model: str | None) -> str:
    if model:
        return model
    if provider == "gemini":
        return os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    if provider == "openrouter":
        return os.getenv("OPENROUTER_MODEL", "openrouter/free")
    if provider == "groq":
        return os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    if provider == "nvidia":
        return os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-flash-0731")
    if provider == "deepseek":
        return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    if provider == "openai":
        return os.getenv("BYOK_OPENAI_MODEL", "gpt-4o-mini")
    if provider == "anthropic":
        return os.getenv("BYOK_ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
    return ""


def _call_byok(prompt: str, temperature: float = 0.2,
               max_tokens: int | None = None, *, json_mode: bool = False,
               max_output_tokens: int | None = None,
               info: dict | None = None) -> str | None:
    """Try the account's own keys first. Returns None when the account has none.

    When keys ARE configured, there is deliberately no fallback to the shared
    app-key chain: a broken key fails loudly instead of quietly spending the
    shared budget and bypassing the 3/day quota.
    """
    rows = _byok_rows()
    if not rows:
        return None
    from userkeys import OPENAI_COMPATIBLE_BASE
    last: Exception | None = None
    for row in rows:
        provider = (row.get("provider") or "").strip()
        key = row.get("api_key") or ""
        model = _byok_model(provider, row.get("model"))
        sub: dict = {}
        try:
            if provider == "gemini":
                from main import call_gemini
                text = call_gemini(
                    prompt,
                    response_mime_type="application/json" if json_mode else None,
                    max_output_tokens=max_output_tokens,
                    info=sub, api_key=key, model=model,
                )
            elif provider == "anthropic":
                text = _call_anthropic(
                    prompt, model, key, temperature, json_mode=json_mode,
                    max_output_tokens=max_output_tokens, info=sub,
                )
            elif provider == "custom":
                text = _call_openai_compatible(
                    prompt, model, key, row.get("base_url") or "",
                    temperature, json_mode=json_mode,
                    max_output_tokens=max_output_tokens, info=sub,
                    provider_name="custom",
                )
            elif provider == "openrouter":
                text = _call_openrouter(
                    prompt, model, temperature, max_tokens, json_mode=json_mode,
                    max_output_tokens=max_output_tokens, info=sub, key=key,
                )
            elif provider == "groq":
                text = _call_groq(
                    prompt, model, temperature, json_mode=json_mode,
                    max_output_tokens=max_output_tokens, info=sub, key=key,
                )
            elif provider == "nvidia":
                text = _call_nvidia(
                    prompt, model, temperature, json_mode=json_mode,
                    max_output_tokens=max_output_tokens, info=sub, key=key,
                )
            elif provider == "deepseek":
                text = _call_deepseek(
                    prompt, model, temperature, json_mode=json_mode,
                    max_output_tokens=max_output_tokens, info=sub, key=key,
                )
            elif provider in OPENAI_COMPATIBLE_BASE:
                text = _call_openai_compatible(
                    prompt, model, key, OPENAI_COMPATIBLE_BASE[provider],
                    temperature, json_mode=json_mode,
                    max_output_tokens=max_output_tokens, info=sub,
                    provider_name=provider,
                )
            else:
                raise RuntimeError(f"Unsupported provider {provider!r}")
            if not (text or "").strip():
                raise RuntimeError("provider returned an empty response")
            # Guarantee attribution even if a caller didn't populate `info`.
            sub.setdefault("provider", provider)
            sub.setdefault("model", model)
            sub["byok"] = True
            if info is not None:
                info.update(sub)
            return text
        except Exception as e:
            # Provider errors can echo credentials (especially custom
            # OpenAI-compatible endpoints); never log or return the key.
            detail = str(e)
            if key:
                detail = detail.replace(key, "[redacted]")
            last = RuntimeError(detail[:300])
            print(f"BYOK {provider} failed: {detail[:220]}")
            continue
    raise ByokError(
        "Your saved LLM key could not complete this request. "
        f"{str(last)[:300]} — check the key/model in Account, or remove all "
        "saved keys to use Intara's shared pool."
    )


def verify_user_key(provider: str, api_key: str, model: str | None = None,
                    base_url: str | None = None) -> dict:
    """Cheap live check for the Account 'Test' button (never stores the key)."""
    from userkeys import OPENAI_COMPATIBLE_BASE, validate_key
    key, clean_model, clean_base = validate_key(provider, api_key, model, base_url)
    mdl = _byok_model(provider, clean_model)
    prompt = "Reply with the single word OK."
    # A little headroom: reasoning-style models can spend a tiny 16-token cap
    # before emitting any visible text, which would look like a bad key.
    test_tokens = 128
    if provider == "gemini":
        from main import call_gemini
        text = call_gemini(prompt, max_output_tokens=test_tokens, api_key=key, model=mdl)
    elif provider == "anthropic":
        text = _call_anthropic(prompt, mdl, key, 0.2, max_output_tokens=test_tokens)
    elif provider == "custom":
        text = _call_openai_compatible(
            prompt, mdl, key, clean_base or "", 0.2,
            max_output_tokens=test_tokens, provider_name="custom",
        )
    else:
        base = OPENAI_COMPATIBLE_BASE.get(provider)
        if not base:
            raise RuntimeError(f"Unsupported provider {provider!r}")
        text = _call_openai_compatible(
            prompt, mdl, key, base, 0.2,
            max_output_tokens=test_tokens, provider_name=provider,
        )
    if not (text or "").strip():
        raise RuntimeError("The provider returned an empty response.")
    return {"ok": True, "provider": provider, "model": mdl,
            "sample": text.strip()[:40]}


def _call_llm_inner(prompt: str, temperature: float = 0.2, max_tokens: int | None = None, *, json_mode: bool = False, max_output_tokens: int | None = None, info: dict | None = None) -> str:
    """Chain core — see call_llm (public wrapper adds cassettes + telemetry)."""
    byok = _call_byok(prompt, temperature, max_tokens, json_mode=json_mode,
                      max_output_tokens=max_output_tokens, info=info)
    if byok is not None:
        return byok
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
    meta_info = info if info is not None else {}
    byok = _call_byok(prompt, temperature, max_tokens, json_mode=json_mode,
                      max_output_tokens=max_output_tokens, info=meta_info)
    if byok is not None:
        return byok, {"source": meta_info.get("provider") or "byok",
                      "model": meta_info.get("model")}
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
        from userkeys import current_user
        ctx = telemetry or {}
        sub = sub or {}
        _tm.record_llm_call(
            provider=sub.get("provider") or "unknown",
            model=sub.get("model"),
            user_id=current_user(),
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
            info_out=sub,  # sub["telemetry_id"] lets the agent attribute parse outcome
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
    if info is not None and sub.get("telemetry_id") is not None:
        info["telemetry_id"] = sub["telemetry_id"]
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
    if info is not None and sub.get("telemetry_id") is not None:
        info["telemetry_id"] = sub["telemetry_id"]
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
        # One batched request when available (fewer quota units for seeding),
        # per-text loop as fallback — same normalization either way.
        if len(texts) > 1:
            try:
                rb = client.models.embed_content(model="gemini-embedding-001", contents=list(texts))
                embs = list(getattr(rb, "embeddings", None) or [])
                if len(embs) == len(texts):
                    batched = []
                    for e in embs:
                        vals = getattr(e, 'values', None)
                        if vals is None and isinstance(e, dict):
                            vals = e.get('values')
                        vals = [float(x) for x in (vals or [])]
                        if len(vals) > 3072: vals = vals[:3072]
                        elif len(vals) < 3072: vals = vals + [0.0]*(3072-len(vals))
                        batched.append(vals)
                    if batched and all(any(x != 0.0 for x in v) for v in batched):
                        return batched
                    print("gemini embed batch returned zero vectors, per-text fallback")
            except Exception as e:
                print(f"gemini embed batch failed, per-text fallback: {e}")
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

def _deepseek_client(key: str | None = None):
    key = (key or os.getenv("DEEPSEEK_API_KEY", "")).strip()
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url="https://api.deepseek.com/v1", api_key=key, timeout=30.0)
    except Exception as e:
        print(f"deepseek client init failed: {e}")
        return None

def _call_deepseek(prompt: str, model: str, temperature: float = 0.2, *, json_mode: bool = False, max_output_tokens: int | None = None, info: dict | None = None, key: str | None = None) -> str:
    client = _deepseek_client(key)
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
