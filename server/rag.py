"""
RAG — 45 lines you type in 20 min
Interview: "I chunk → embed → pgvector match → synthesize with citations"
"""
import os, re
from dotenv import load_dotenv
from google import genai
from supabase import create_client

load_dotenv()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
SUPA_URL = os.getenv("SUPABASE_URL", "")
SUPA_KEY = os.getenv("SUPABASE_KEY", "")

client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None
supabase = create_client(SUPA_URL, SUPA_KEY) if SUPA_URL and SUPA_KEY else None

def chunk(text: str, size=400, overlap=50):
    # 400 chars ~ 100 tokens, good for embedding recall
    chunks=[]
    for i in range(0, len(text), size-overlap):
        c=text[i:i+size].strip()
        if c: chunks.append(c)
    return chunks

def embed(texts: list[str]):
    if not client:
        # fallback: fake embedding for demo without key
        return [[0.0]*1536 for _ in texts]
    # Gemini embeddings: model text-embedding-004
    out=[]
    for t in texts:
        r=client.models.embed_content(model="gemini-embedding-001", contents=t)
        vals=getattr(r, 'embeddings', [{}])[0]
        vals=getattr(vals, 'values', [0]*3072) if hasattr(vals,'values') else vals.get('values',[0]*3072) if isinstance(vals, dict) else [0]*3072
        if len(vals) > 1536: vals = vals[:1536]
        elif len(vals) < 1536: vals = vals + [0.0]*(1536-len(vals))
        out.append(vals)
    return out

def answer(question: str, top_k=5):
    if not supabase or not client:
        return {"answer": "Demo mode: configure GEMINI_API_KEY + SUPABASE to enable RAG. Question was: "+question, "cites": []}
    # 1. embed question
    q_emb = embed([question])[0]
    # 2. vector search
    res = supabase.rpc("match_docs", {"query_embedding": q_emb, "match_count": top_k}).execute()
    docs = res.data or []
    context = "\n\n".join([d["content"] for d in docs]) or "No docs found."
    cites = [d["content"][:120] for d in docs]
    # 3. synthesize with citations
    prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer concisely and cite sources. If no context, say you don't know."
    resp = client.models.generate_content(model=MODEL, contents=prompt, config={"temperature": 0.2})
    text = resp.text.strip()
    return {"answer": text, "cites": cites}

# Seed helper (run once)
def seed_docs():
    if not supabase: return
    texts = [
        "DhiWise builds Rocket.new — prompt to app with DB/auth/API and deployment.",
        "Supabase pgvector enables vector search via match_docs RPC with cosine similarity.",
        "Gemini 3.6 flash handles schema generation with JSON guard and retry."
    ]
    for t in texts:
        emb = embed([t])[0]
        supabase.table("docs").insert({"content": t, "embedding": emb}).execute()
    print("seeded")

if __name__ == "__main__":
    print(answer("What stack does DhiWise use?"))
