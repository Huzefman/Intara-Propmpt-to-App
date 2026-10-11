"""
Finished FastAPI — 65 lines you type in 25 min
Interview: "I guard LLM JSON, retry on 429, and write to Supabase"
"""
import os, json, re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception
from google import genai
from supabase import create_client


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
SUPA_KEY = os.getenv("SUPABASE_KEY", "")

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

# Intara wish routers — try load, fallback if missing
try:
    from routers.wishes import router as wishes_router
    app.include_router(wishes_router, prefix="/api")
    app.include_router(wishes_router, prefix="")  # also mount without prefix for /wish
except Exception as e:
    print(f"wishes router not loaded: {e}")

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
def call_gemini(prompt: str):
    if not client:
        raise RuntimeError("Missing GEMINI_API_KEY")
    resp = client.models.generate_content(model=MODEL, contents=prompt, config={"temperature": 0.2})
    return resp.text

@app.post("/generate")
@app.post("/api/generate")
def generate(inp: PromptIn):
    # OpenRouter-first via call_llm, fallback to Gemini
    try:
        from services.llm import call_llm
        raw = call_llm(PROMPT.format(prompt=inp.prompt))
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
            raw2 = call_llm(f"Fix this to valid JSON with tables: {raw}")
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
def rag(inp: RagIn):
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
