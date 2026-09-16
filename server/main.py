"""
Finished FastAPI — 65 lines you type in 25 min
Interview: "I guard LLM JSON, retry on 429, and write to Supabase"
"""
import os, json, re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from google import genai
from supabase import create_client

load_dotenv()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
SUPA_URL = os.getenv("SUPABASE_URL", "")
SUPA_KEY = os.getenv("SUPABASE_KEY", "")

client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None
supabase = create_client(SUPA_URL, SUPA_KEY) if SUPA_URL and SUPA_KEY else None

app = FastAPI(title="Prompt → App")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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

@retry(wait=wait_exponential(min=1, max=8), stop=stop_after_attempt(3), retry=retry_if_exception_type(Exception))
def call_gemini(prompt: str):
    if not client:
        raise RuntimeError("Missing GEMINI_API_KEY")
    resp = client.models.generate_content(model=MODEL, contents=prompt, config={"temperature": 0.2})
    return resp.text

@app.post("/generate")
@app.post("/api/generate")
def generate(inp: PromptIn):
    raw = call_gemini(PROMPT.format(prompt=inp.prompt))
    try:
        data = parse_json(raw)
        if "tables" not in data:
            raise ValueError("no tables")
    except Exception as e:
        # repair pass
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
    return {"ok": True, "model": MODEL, "supabase": bool(supabase)}
