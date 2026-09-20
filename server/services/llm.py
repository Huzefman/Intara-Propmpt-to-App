"""
LLM provider — Groq (gsk_*) → Nvidia (nvapi-*) Kimi/vision → OpenRouter (Qwen :free) → Gemini
All OpenAI-compatible via openai SDK
Embeddings: Gemini (others have no stable free embeddings)
"""
import os

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

def _call_groq(prompt: str, model: str, temperature: float = 0.2) -> str:
    client = _groq_client()
    if not client:
        raise RuntimeError("Missing GROQ_API_KEY")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a JSON generator. Return ONLY valid JSON, no markdown, no prose."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        timeout=30.0,
    )
    return (resp.choices[0].message.content or "").strip()

def _nvidia_client():
    key = os.getenv("NVIDIA_API_KEY", "")
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=key, timeout=60.0)
    except Exception as e:
        print(f"nvidia client init failed: {e}")
        return None

def _call_nvidia(prompt: str, model: str, temperature: float = 0.2, stream: bool = False, image_url: str | None = None, reasoning_effort: str | None = None) -> str:
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
    kwargs: dict = {"model": model, "messages": messages, "temperature": temperature, "timeout": 60.0}
    if is_nemotron:
        # Nemotron uses chat_template_kwargs.enable_thinking and top_p
        kwargs["max_tokens"] = 16384
        kwargs["top_p"] = 0.95
        kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": True}}
        if stream:
            kwargs["stream"] = True
    else:
        if image_url is None:
            kwargs["max_tokens"] = 16384
            if reasoning_effort:
                kwargs["extra_body"] = {"reasoning_effort": reasoning_effort}
        else:
            kwargs["max_tokens"] = 4096
        if stream:
            kwargs["stream"] = True
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
    resp = client.chat.completions.create(**kwargs)  # type: ignore
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

def _call_openrouter(prompt: str, model: str, temperature: float = 0.2) -> str:
    client = _openrouter_client()
    if not client:
        raise RuntimeError("Missing OPENROUTER_API_KEY")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a JSON generator. Return ONLY valid JSON, no markdown, no prose."},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            timeout=30.0,
        )
        content = resp.choices[0].message.content or ""
        return content.strip()
    except Exception as e:
        raise

def call_llm(prompt: str, temperature: float = 0.2) -> str:
    """
    DeepSeek (deepseek-*) → Nvidia Kimi (nvapi-*) → Groq → OpenRouter → Gemini — fail-fast on 429
    User requested DeepSeek as primary
    """
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    nvidia_model = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-flash-0731")
    groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    or_primary = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    or_fallback = os.getenv("OPENROUTER_FALLBACK", "openrouter/free")

    # 0. DeepSeek direct (primary as requested)
    if os.getenv("DEEPSEEK_API_KEY"):
        try:
            return _call_deepseek(prompt, deepseek_model, temperature)
        except Exception as e:
            print(f"deepseek {deepseek_model} failed: {e}")
            if "429" in str(e).lower():
                pass
            # fall through

    # 1. Nvidia Kimi
    if os.getenv("NVIDIA_API_KEY"):
        try:
            is_analyzer = "AppSpec" in prompt or "Analyzer" in prompt
            return _call_nvidia(prompt, nvidia_model, temperature, reasoning_effort="high" if is_analyzer else None)
        except Exception as e:
            print(f"nvidia {nvidia_model} failed: {e}")
            if "429" in str(e).lower():
                pass

    # 2. Groq
    if os.getenv("GROQ_API_KEY"):
        try:
            return _call_groq(prompt, groq_model, temperature)
        except Exception as e:
            msg = str(e).lower()
            print(f"groq {groq_model} failed: {e}")
            if "429" in msg and "quota" in msg:
                pass

    # 2. OpenRouter
    if os.getenv("OPENROUTER_API_KEY"):
        try:
            return _call_openrouter(prompt, or_primary, temperature)
        except Exception as e:
            msg = str(e).lower()
            is_retryable = "429" in msg or "quota" in msg or "rate" in msg or "402" in msg
            print(f"openrouter primary {or_primary} failed: {e} (retryable={is_retryable})")
            if or_fallback and or_fallback != or_primary:
                try:
                    print(f"trying openrouter fallback {or_fallback}")
                    return _call_openrouter(prompt, or_fallback, temperature)
                except Exception as e2:
                    print(f"openrouter fallback {or_fallback} failed: {e2}")
                    if "429" in str(e2) or "429" in str(e):
                        raise RuntimeError(f"429 OpenRouter quota exhausted: {e2}")
                    pass
            if is_retryable and "429" in msg:
                raise RuntimeError(f"429 OpenRouter quota exhausted: {e}")

    # 3. Gemini
    try:
        from main import call_gemini
        return call_gemini(prompt)
    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower():
            raise RuntimeError(f"429 Gemini quota exhausted: {e}")
        raise

def call_llm_with_meta(prompt: str, temperature: float = 0.2) -> tuple[str, dict]:
    """Returns (text, meta) where meta has source/model for _meta badge — DeepSeek primary"""
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    if os.getenv("DEEPSEEK_API_KEY"):
        try:
            text = _call_deepseek(prompt, deepseek_model, temperature)
            return text, {"source": "deepseek", "model": deepseek_model}
        except Exception as e:
            if "429" in str(e).lower():
                raise
            print(f"deepseek with_meta {deepseek_model} failed: {e}, trying nvidia")
    nvidia_model = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-flash-0731")
    if os.getenv("NVIDIA_API_KEY"):
        try:
            is_analyzer = "AppSpec" in prompt or "Analyzer" in prompt
            text = _call_nvidia(prompt, nvidia_model, temperature, reasoning_effort="high" if is_analyzer else None)
            return text, {"source": "nvidia", "model": nvidia_model}
        except Exception as e:
            if "429" in str(e).lower():
                raise
            print(f"nvidia with_meta {nvidia_model} failed: {e}, trying groq")
    groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    if os.getenv("GROQ_API_KEY"):
        try:
            text = _call_groq(prompt, groq_model, temperature)
            return text, {"source": "groq", "model": groq_model}
        except Exception as e:
            if "429" in str(e).lower():
                raise
            print(f"groq with_meta {groq_model} failed: {e}, trying openrouter")
    primary = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    if os.getenv("OPENROUTER_API_KEY"):
        try:
            text = _call_openrouter(prompt, primary, temperature)
            return text, {"source": "openrouter", "model": primary}
        except Exception as e:
            if "429" in str(e).lower():
                raise
            fallback = os.getenv("OPENROUTER_FALLBACK", "openrouter/free")
            if fallback and fallback != primary:
                try:
                    text = _call_openrouter(prompt, fallback, temperature)
                    return text, {"source": "openrouter", "model": fallback}
                except: pass
    try:
        from main import call_gemini
        text = call_gemini(prompt)
        return text, {"source": "gemini", "model": os.getenv("GEMINI_MODEL", "gemini-3.6-flash")}
    except Exception as e:
        raise

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
            return [[0.0]*1536 for _ in texts]
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

def _call_deepseek(prompt: str, model: str, temperature: float = 0.2) -> str:
    client = _deepseek_client()
    if not client:
        raise RuntimeError("Missing DEEPSEEK_API_KEY")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a JSON generator. Return ONLY valid JSON, no markdown, no prose."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        timeout=30.0,
    )
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
    # Priority: DeepSeek (if DEEPSEEK_API_KEY) -> Nvidia Kimi -> Groq -> OpenRouter -> Gemini
    if has_deepseek:
        primary_src = "deepseek"
    elif has_nvidia:
        primary_src = "nvidia"
    elif has_groq:
        primary_src = "groq"
    elif has_or:
        primary_src = "openrouter"
    elif has_gem:
        primary_src = "gemini"
    else:
        primary_src = "none"
    return {
        "deepseek": {"configured": has_deepseek, "model": deepseek_model},
        "groq": {"configured": has_groq, "model": groq_model},
        "nvidia": {"configured": has_nvidia, "model": nvidia_model},
        "openrouter": {"configured": has_or, "model": primary, "fallback": os.getenv("OPENROUTER_FALLBACK", "openrouter/free") if has_or else None, "quota": quota},
        "gemini": {"configured": has_gem, "model": gem_model},
        "primary": primary_src
    }
