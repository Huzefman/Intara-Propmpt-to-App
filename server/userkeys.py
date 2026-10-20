"""Per-account LLM API keys — encrypted storage and request identity.

The API key is encrypted before it reaches Postgres and is never returned to the
browser after saving. Only the backend's service-key client can read the table
(migration 013 enables RLS with no policies).

BYOK policy: if an account has at least one saved key, builds use *only* those
keys — there is no silent fallback to the shared app pool. That makes the
"unlimited builds with your own key" promise safe: a bad key fails loudly
instead of spending the shared budget.
"""
from __future__ import annotations

import base64
import contextvars
import hashlib
import ipaddress
import os
import socket
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

# Request-scoped identity. `auth.require_user` sets this in the async
# dependency, so endpoints, asyncio tasks and thread-pool work inherit it.
_CURRENT_USER: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "intara_current_user", default=None
)


def set_current_user(user_id: str | None) -> None:
    _CURRENT_USER.set(str(user_id) if user_id else None)


def current_user() -> str | None:
    return _CURRENT_USER.get()


# Build-planning/build tasks run for minutes across many LLM calls. Pinning the
# key set at task start keeps a whole build consistent (and honest: removing a
# key mid-build cannot silently push later calls onto the shared pool).
_BYOK_SNAPSHOT: contextvars.ContextVar[list[dict] | None] = contextvars.ContextVar(
    "intara_byok_snapshot", default=None
)


def set_byok_snapshot(rows: list[dict] | None) -> None:
    _BYOK_SNAPSHOT.set(list(rows) if rows is not None else None)


def byok_snapshot() -> list[dict] | None:
    return _BYOK_SNAPSHOT.get()


def snapshot_for(owner: str | None) -> list[dict]:
    """Load and pin the account's keys for the current task. Never raises."""
    rows: list[dict] = []
    if owner:
        try:
            rows = list_keys(owner)
        except Exception as exc:
            print(f"BYOK snapshot failed: {str(exc)[:160]}")
            rows = []
    set_byok_snapshot(rows)
    return rows


PROVIDERS: dict[str, dict] = {
    "gemini": {
        "label": "Google Gemini",
        "docs_url": "https://aistudio.google.com/app/apikey",
        "placeholder": "AIza…",
        "description": "Gemini models through Google AI Studio.",
        "default_model": "gemini-3.6-flash",
        "needs_base_url": False,
    },
    "openrouter": {
        "label": "OpenRouter",
        "docs_url": "https://openrouter.ai/keys",
        "placeholder": "sk-or-v1-…",
        "description": "One key for hundreds of models from many providers.",
        "default_model": "openrouter/free",
        "needs_base_url": False,
    },
    "groq": {
        "label": "Groq",
        "docs_url": "https://console.groq.com/keys",
        "placeholder": "gsk_…",
        "description": "Very fast open models (Llama, GPT-OSS, Qwen).",
        "default_model": "openai/gpt-oss-20b",
        "needs_base_url": False,
    },
    "nvidia": {
        "label": "NVIDIA NIM",
        "docs_url": "https://build.nvidia.com/",
        "placeholder": "nvapi-…",
        "description": "NVIDIA's hosted NIM endpoints (DeepSeek, Kimi, Nemotron).",
        "default_model": "deepseek-ai/deepseek-v4-flash-0731",
        "needs_base_url": False,
    },
    "deepseek": {
        "label": "DeepSeek",
        "docs_url": "https://platform.deepseek.com/api_keys",
        "placeholder": "sk-…",
        "description": "DeepSeek's native API.",
        "default_model": "deepseek-chat",
        "needs_base_url": False,
    },
    "openai": {
        "label": "OpenAI",
        "docs_url": "https://platform.openai.com/api-keys",
        "placeholder": "sk-…",
        "description": "GPT models through the OpenAI API.",
        "default_model": "gpt-4o-mini",
        "needs_base_url": False,
    },
    "anthropic": {
        "label": "Anthropic",
        "docs_url": "https://console.anthropic.com/settings/keys",
        "placeholder": "sk-ant-…",
        "description": "Claude models through the Anthropic Messages API.",
        "default_model": "claude-3-5-haiku-latest",
        "needs_base_url": False,
    },
    "custom": {
        "label": "Custom / OpenAI-compatible",
        "docs_url": "",
        "placeholder": "your-api-key",
        "description": "Any public OpenAI-compatible endpoint (Together, Fireworks, a hosted vLLM, …).",
        "default_model": "",
        "needs_base_url": True,
    },
}


class UserKeysUnavailable(RuntimeError):
    """Migration 013 is missing or the key table is unreachable."""


# provider -> fixed OpenAI-compatible base URL (None for native Gemini/Anthropic)
OPENAI_COMPATIBLE_BASE = {
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
}

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 60.0
_CACHE_MAX = 500
_CACHE_LOCK = threading.Lock()
_FERNET_CACHE: dict[str, object] = {}


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------
def _fernet():
    secret = os.getenv("KEY_ENCRYPTION_SECRET", "").strip()
    material = secret or os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv(
        "SUPABASE_KEY", ""
    )
    if not material:
        raise RuntimeError(
            "KEY_ENCRYPTION_SECRET is not configured on the server."
        )
    cache_key = hashlib.sha256(material.encode()).hexdigest()
    with _CACHE_LOCK:
        cached = _FERNET_CACHE.get(cache_key)
        if cached is not None:
            return cached
        from cryptography.fernet import Fernet

        if secret:
            try:
                f = Fernet(secret.encode())
            except Exception:
                f = Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))
        else:
            # No dedicated secret: derive one from the server-only service key.
            # Keys survive restarts but not a service-key rotation; set
            # KEY_ENCRYPTION_SECRET in production to decouple them.
            f = Fernet(base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest()))
        _FERNET_CACHE[cache_key] = f
        return f


def encrypt_key(api_key: str) -> str:
    return _fernet().encrypt(api_key.encode()).decode()


def decrypt_key(enc: str) -> str:
    return _fernet().decrypt(enc.encode()).decode()


def mask_key(api_key: str) -> str:
    tail = api_key[-4:] if len(api_key) >= 8 else ""
    return f"••••{tail}"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _host_is_public(host: str) -> bool:
    if host in ("localhost", "localhost.localdomain"):
        return False
    if host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def validate_base_url(raw: str) -> str:
    """Custom endpoints must be public HTTPS URLs (basic SSRF guard)."""
    url = (raw or "").strip().rstrip("/")
    if not url:
        raise ValueError("Base URL is required for a custom provider.")
    if len(url) > 300:
        raise ValueError("Base URL is too long.")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Base URL must start with https://")
    if parsed.username or parsed.password:
        raise ValueError("Base URL must not contain credentials.")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("Base URL is missing a host.")
    if not _host_is_public(host):
        raise ValueError("Base URL must point to a public host.")
    return url


def validate_key(provider: str, api_key: str, model: str | None = None,
                 base_url: str | None = None) -> tuple[str, str | None, str | None]:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}.")
    key = (api_key or "").strip()
    if len(key) < 8:
        raise ValueError("That API key looks too short.")
    if len(key) > 500:
        raise ValueError("That API key is too long.")
    if any(ch.isspace() for ch in key):
        raise ValueError("API keys cannot contain spaces or newlines.")
    clean_model = (model or "").strip() or None
    if clean_model and len(clean_model) > 120:
        raise ValueError("Model name is too long.")
    if provider == "custom":
        if not clean_model:
            raise ValueError("A model name is required for a custom provider.")
        clean_base = validate_base_url(base_url or "")
    else:
        clean_base = None
    return key, clean_model, clean_base


def public_row(row: dict) -> dict:
    provider = row.get("provider", "")
    meta = PROVIDERS.get(provider, {})
    return {
        "provider": provider,
        "label": meta.get("label", provider),
        "masked": mask_key(row.get("api_key") or ""),
        "model": row.get("model") or meta.get("default_model") or None,
        "base_url": row.get("base_url"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "docs_url": meta.get("docs_url", ""),
    }


def catalog() -> list[dict]:
    return [{"id": key, **meta} for key, meta in PROVIDERS.items()]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
def _table():
    from db.wishes import _client
    return _client().table("user_llm_keys")


def _is_missing_table(exc: BaseException) -> bool:
    msg = str(exc)
    return (
        "user_llm_keys" in msg
        and ("PGRST205" in msg or "schema cache" in msg
             or "does not exist" in msg or "Could not find the table" in msg)
    )


def list_keys(owner: str | None, *, use_cache: bool = True) -> list[dict]:
    """Decrypted keys for internal use. Callers must never log the `api_key`."""
    if not owner:
        return []
    now = time.time()
    if use_cache:
        with _CACHE_LOCK:
            hit = _CACHE.get(owner)
            if hit and hit[0] > now:
                return list(hit[1])
    try:
        rows = (
            _table()
            .select("provider,api_key_enc,model,base_url,created_at,updated_at")
            .eq("owner", owner)
            .order("updated_at", desc=True)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        if _is_missing_table(exc):
            raise UserKeysUnavailable(
                "Run supabase/migrations/013_user_llm_keys.sql in the Supabase SQL editor."
            ) from exc
        raise
    out: list[dict] = []
    for row in rows:
        try:
            api_key = decrypt_key(row.get("api_key_enc") or "")
        except Exception as exc:
            print(f"user_llm_keys: could not decrypt {row.get('provider')}: {str(exc)[:120]}")
            continue
        out.append({
            "provider": row.get("provider"),
            "api_key": api_key,
            "model": row.get("model"),
            "base_url": row.get("base_url"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        })
    with _CACHE_LOCK:
        # Decrypted keys are sensitive: keep the in-process cache bounded and
        # drop expired entries instead of accumulating every account forever.
        if len(_CACHE) >= _CACHE_MAX:
            for cached_owner, (expires, _rows) in list(_CACHE.items()):
                if expires <= now:
                    _CACHE.pop(cached_owner, None)
            if len(_CACHE) >= _CACHE_MAX:
                _CACHE.clear()
        _CACHE[owner] = (now + _CACHE_TTL, list(out))
    return out


def has_keys(owner: str | None) -> bool:
    try:
        return bool(list_keys(owner))
    except Exception:
        return False


def using_byok() -> bool:
    """True when the current request's account has at least one saved key.

    Callers use this to forbid direct shared-key fallbacks (e.g. legacy
    `call_gemini` retry paths) while a user's own key is configured.
    """
    return bool(has_keys(current_user()))


def invalidate(owner: str | None) -> None:
    if not owner:
        return
    with _CACHE_LOCK:
        _CACHE.pop(owner, None)


def save_key(owner: str, provider: str, api_key: str,
             model: str | None = None, base_url: str | None = None) -> dict:
    key, clean_model, clean_base = validate_key(provider, api_key, model, base_url)
    enc = encrypt_key(key)
    try:
        res = (
            _table()
            .upsert({
                "owner": owner,
                "provider": provider,
                "api_key_enc": enc,
                "model": clean_model,
                "base_url": clean_base,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="owner,provider")
            .execute()
        )
        if not getattr(res, "data", None):
            raise RuntimeError("key upsert returned no data")
    except Exception as exc:
        if _is_missing_table(exc):
            raise UserKeysUnavailable(
                "Run supabase/migrations/013_user_llm_keys.sql in the Supabase SQL editor."
            ) from exc
        raise
    invalidate(owner)
    meta = PROVIDERS[provider]
    return {
        "provider": provider,
        "label": meta["label"],
        "masked": mask_key(key),
        "model": clean_model or meta.get("default_model") or None,
        "base_url": clean_base,
        "docs_url": meta.get("docs_url", ""),
        "created_at": None,
        "updated_at": None,
    }


def delete_key(owner: str, provider: str) -> None:
    try:
        _table().delete().eq("owner", owner).eq("provider", provider).execute()
    except Exception as exc:
        if _is_missing_table(exc):
            raise UserKeysUnavailable(
                "Run supabase/migrations/013_user_llm_keys.sql in the Supabase SQL editor."
            ) from exc
        raise
    invalidate(owner)
