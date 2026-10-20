"""
Finished FastAPI — 65 lines you type in 25 min
Interview: "I guard LLM JSON, retry on 429, and write to Supabase"
"""
import os, json, re, time
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception
from google import genai
from supabase import create_client

from auth import require_user


def _gemini_retryable(exc: BaseException) -> bool:
    # Retry transient errors, but NOT quota exhaustion (falls through to next provider fast).
    try:
        from utils.json_parse import is_quota_error
        if is_quota_error(exc):  # type: ignore[arg-type]
            return False
    except Exception:
        m = str(exc).lower()
        if "429" in m or "quota" in m or "exhausted" in m:
            return False
    return True


load_dotenv()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
SUPA_URL = os.getenv("SUPABASE_URL", "")
SUPA_KEY = os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv("SUPABASE_KEY", "")

def _make_gemini_client(api_key: str):
    # Bounded HTTP (60s): an unbounded generate_content can wedge the single
    # uvicorn worker forever, freezing every endpoint mid-build.
    try:
        return genai.Client(api_key=api_key, http_options={"timeout": 60000})
    except Exception as e:
        print(f"gemini client timeout opts unsupported, plain client: {e}")
        return genai.Client(api_key=api_key)


client = _make_gemini_client(GEMINI_KEY) if GEMINI_KEY else None
supabase = create_client(SUPA_URL, SUPA_KEY) if SUPA_URL and SUPA_KEY else None

app = FastAPI(title="Intara — Planet of Wishes")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Public RAG is an LLM-backed endpoint on the landing page; keep it cheap to
# abuse-proof. 20 questions/hour/IP is far above normal demo use.
_RAG_HITS: dict[str, list[float]] = {}
_RAG_LIMIT = 20
_RAG_WINDOW = 3600.0


def _rag_rate_limit(request: Request) -> None:
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (
        request.client.host if request.client else "unknown"
    )
    now = time.time()
    for key, stamps in list(_RAG_HITS.items()):
        _RAG_HITS[key] = [t for t in stamps if now - t < _RAG_WINDOW]
    stamps = _RAG_HITS.get(ip, [])
    if len(stamps) >= _RAG_LIMIT:
        raise HTTPException(429, "Question limit reached for this hour — try again soon.")
    stamps.append(now)
    _RAG_HITS[ip] = stamps

# NOTE: routers are mounted at the END of this file (after all direct routes)
# so /api/wishes/health etc. match before the router's /wishes/{wid} pattern.

class PromptIn(BaseModel):
    prompt: str
class RagIn(BaseModel):
    question: str

PROMPT = """You are a schema generator. Given a prompt, return ONLY JSON:
{"tables": [{"name": "users", "fields": [{"name": "email", "type": "text"}]}]}
Prompt: {prompt}
Rules: 1-3 tables, 2-5 fields each, types: text/integer/timestamp/boolean.
Return JSON only, no markdown."""

def parse_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.S)
    if m: text = m.group(0)
    return json.loads(text)

@retry(wait=wait_exponential(min=1, max=8), stop=stop_after_attempt(3), retry=retry_if_exception(_gemini_retryable))
def call_gemini(prompt: str, *, response_mime_type: str | None = None, max_output_tokens: int | None = None, info: dict | None = None):
    if not client:
        raise RuntimeError("Missing GEMINI_API_KEY")
    config: dict = {"temperature": 0.2}
    if response_mime_type:
        config["response_mime_type"] = response_mime_type
    if max_output_tokens:
        config["max_output_tokens"] = max_output_tokens
    resp = client.models.generate_content(model=MODEL, contents=prompt, config=config)
    if info is not None:
        finish = None
        try:
            cands = getattr(resp, "candidates", None) or []
            if cands:
                finish = getattr(cands[0], "finish_reason", None)
                finish = str(finish).split(".")[-1] if finish is not None else None
        except Exception:
            finish = None
        info.update({"provider": "gemini", "model": MODEL,
                     "finish_reason": finish,
                     "json_mode": bool(response_mime_type)})
        try:
            u = getattr(resp, "usage_metadata", None)
            if u is not None:
                info["tokens_in"] = getattr(u, "prompt_token_count", None)
                info["tokens_out"] = getattr(u, "candidates_token_count", None)
        except Exception:
            pass
    return resp.text

@app.post("/generate")
@app.post("/api/generate")
def generate(inp: PromptIn, user: dict = Depends(require_user)):
    # Legacy schema endpoint — signed-in callers only (it spends LLM quota).
    # OpenRouter-first via call_llm, fallback to Gemini
    try:
        from services.llm import call_llm
        raw = call_llm(PROMPT.format(prompt=inp.prompt), json_mode=True)
    except Exception:
        raw = call_gemini(PROMPT.format(prompt=inp.prompt))
    try:
        data = parse_json(raw)
        if "tables" not in data:
            raise ValueError("no tables")
    except Exception as e:
        # repair pass — OpenRouter first
        try:
            from services.llm import call_llm
            raw2 = call_llm(f"Fix this to valid JSON with tables: {raw}", json_mode=True)
        except Exception:
            raw2 = call_gemini(f"Fix this to valid JSON with tables: {raw}")
        try:
            data = parse_json(raw2)
        except:
            raise HTTPException(500, f"LLM JSON failed: {e}")
    # persist (optional if supabase configured)
    if supabase:
        try:
            supabase.table("schemas").insert({"prompt": inp.prompt, "tables": data["tables"]}).execute()
        except Exception as e:
            print("supabase insert failed:", e)
    return data

@app.post("/rag")
@app.post("/api/rag")
def rag(inp: RagIn, request: Request):
    _rag_rate_limit(request)
    # import here to avoid circular
    from rag import answer
    try:
        res = answer(inp.question)
        return res
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/health")
@app.get("/api/health")
def health():
    try:
        from services.llm import get_llm_status
        llm = get_llm_status()
    except Exception as e:
        llm = {"error": str(e)[:200]}
    return {"ok": True, "model": MODEL, "supabase": bool(supabase), "planet": "intara", "llm": llm}

@app.get("/api/wishes/health")
def wishes_health():
    return {"ok": True, "wishes": True}

@app.on_event("startup")
def _sweep_orphaned_builds():
    # Fresh boot owns no builds: requeue steps orphaned by kill/crash so no
    # wish stays stuck in `building`. Fail-soft — never blocks boot.
    try:
        from services.sweeper import sweep_orphans, sweep_v2_orphans
        sweep_orphans()
        sweep_v2_orphans()
    except Exception as e:
        print(f"startup sweep skipped: {e}")

@app.get("/api/health/llm-stats")
def llm_stats():
    """Per-provider/model aggregates from llm_calls (Phase 2 telemetry).
    Fail-soft: missing table/creds → ok False with empty aggregates, never 500."""
    try:
        from db.wishes import _client
        supa = _client()
        rows = (supa.table("llm_calls")
                .select("provider,model,tokens_in,tokens_out,latency_ms,parse_outcome,repair_used")
                .order("created_at", desc=True).limit(2000).execute().data or [])
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "n": 0, "by_provider": {}, "by_model": {}}
    by_provider: dict = {}
    by_model: dict = {}
    for r in rows:
        for bucket, key in ((by_provider, r.get("provider") or "unknown"),
                            (by_model, r.get("model") or "unknown")):
            b = bucket.setdefault(key, {"calls": 0, "tokens_in": 0, "tokens_out": 0,
                                        "latency_ms_sum": 0, "latency_ms_n": 0,
                                        "repaired": 0, "failed": 0})
            b["calls"] += 1
            try:
                if r.get("tokens_in") is not None:
                    b["tokens_in"] += int(r["tokens_in"])
                if r.get("tokens_out") is not None:
                    b["tokens_out"] += int(r["tokens_out"])
            except Exception:
                pass
            try:
                if r.get("latency_ms") is not None:
                    b["latency_ms_sum"] += int(r["latency_ms"])
                    b["latency_ms_n"] += 1
            except Exception:
                pass
            if (r.get("parse_outcome") or "") in ("repaired", "llm_repaired") or r.get("repair_used"):
                b["repaired"] += 1
            if (r.get("parse_outcome") or "") == "failed":
                b["failed"] += 1
    for bucket in (by_provider, by_model):
        for b in bucket.values():
            n = b.pop("latency_ms_n")
            s = b.pop("latency_ms_sum")
            b["avg_latency_ms"] = round(s / n) if n else None
    return {"ok": True, "n": len(rows), "by_provider": by_provider, "by_model": by_model}


# Intara wish routers — mounted LAST so direct routes above take precedence
# over router path params (e.g. /api/wishes/health must not match /wishes/{wid}).
try:
    from routers.runs import router as runs_router
    app.include_router(runs_router, prefix="/api")
    app.include_router(runs_router, prefix="")  # also mount without prefix for /runs
except Exception as e:
    print(f"runs router not loaded: {e}")
try:
    from routers.wishes import router as wishes_router
    app.include_router(wishes_router, prefix="/api")
    app.include_router(wishes_router, prefix="")  # also mount without prefix for /wish
except Exception as e:
    print(f"wishes router not loaded: {e}")
try:
    from routers.accounts import router as accounts_router
    app.include_router(accounts_router, prefix="/api")
except Exception as e:
    print(f"accounts router not loaded: {e}")
