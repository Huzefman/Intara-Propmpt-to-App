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
        # fallback: fake embedding — match existing Supabase docs dim 1536 (truncate 3072)
        return [[0.0]*1536 for _ in texts]
    # Gemini embeddings: gemini-embedding-001 is 3072d, but Supabase docs may be 1536 (legacy) or 3072 (new)
    # Return 3072 full, but caller should handle dim mismatch via fallback truncation
    out=[]
    for t in texts:
        r=client.models.embed_content(model="gemini-embedding-001", contents=t)
        vals=getattr(r, 'embeddings', [{}])[0]
        vals=getattr(vals, 'values', [0]*3072) if hasattr(vals,'values') else vals.get('values',[0]*3072) if isinstance(vals, dict) else [0]*3072
        # keep 3072 full
        if len(vals) > 3072: vals = vals[:3072]
        elif len(vals) < 3072: vals = vals + [0.0]*(3072-len(vals))
        out.append(vals)
    return out

def _embed_for_supabase(texts: list[str]):
    """Return embeddings truncated to 1536 to match legacy Supabase docs table if needed."""
    full = embed(texts)
    # If Supabase docs is 1536 (most common), truncate to 1536 for inserts
    # We try 3072 first, fallback to 1536 handled in seed_docs
    return [v[:1536] for v in full]

def answer(question: str, top_k=5):
    if not supabase or not client:
        return {"answer": "Demo mode: configure GEMINI_API_KEY + SUPABASE to enable RAG. Question was: "+question, "cites": []}
    try:
        # 1. embed question (3072d)
        q_emb = embed([question])[0]
        # 2. vector search — handle dim mismatch fallback to 1536
        try:
            res = supabase.rpc("match_docs", {"query_embedding": q_emb, "match_count": top_k}).execute()
        except Exception as e:
            msg = str(e).lower()
            if "dimensions" in msg or "3072" in msg or "1536" in msg:
                # fallback: try truncated 1536 if docs are still 1536
                try:
                    q_emb_1536 = q_emb[:1536]
                    res = supabase.rpc("match_docs", {"query_embedding": q_emb_1536, "match_count": top_k}).execute()
                except Exception as e2:
                    print(f"match_docs both dims failed: {e2}, using empty docs")
                    # fallback to direct table fetch without vector
                    try:
                        fallback = supabase.table("docs").select("content").limit(top_k).execute()
                        docs = [{"content": row["content"]} for row in (fallback.data or [])]
                        context = "\n\n".join([d["content"] for d in docs]) or "No docs found."
                        cites = [d["content"][:120] for d in docs]
                        prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer concisely and cite sources. If no context, say you don't know."
                        resp = client.models.generate_content(model=MODEL, contents=prompt, config={"temperature": 0.2})
                        return {"answer": resp.text.strip(), "cites": cites}
                    except Exception as e3:
                        print(f"fallback docs fetch failed: {e3}")
                        raise e
            else:
                raise
        docs = res.data or []
        context = "\n\n".join([d["content"] for d in docs]) or "No docs found."
        cites = [d["content"][:120] for d in docs]
        # 3. synthesize with citations
        prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer concisely and cite sources. If no context, say you don't know."
        resp = client.models.generate_content(model=MODEL, contents=prompt, config={"temperature": 0.2})
        text = resp.text.strip()
        return {"answer": text, "cites": cites}
    except Exception as e:
        print(f"RAG answer failed, fallback: {e}")
        # ultimate fallback: no RAG, just answer directly
        try:
            prompt = f"Question: {question}\n\nAnswer concisely. If you don't know, say you don't know."
            resp = client.models.generate_content(model=MODEL, contents=prompt, config={"temperature": 0.2})
            return {"answer": resp.text.strip(), "cites": []}
        except Exception as e2:
            return {"answer": f"RAG failed: {e2}", "cites": []}

# Seed helper (run once)
def seed_docs():
    if not supabase: return
    texts = [
        "DhiWise builds Rocket.new — prompt to app with DB/auth/API and deployment.",
        "Supabase pgvector enables vector search via match_docs RPC with cosine similarity.",
        "Gemini 3.6 flash handles schema generation with JSON guard and retry.",
        # Intara lore
        "Intara is a fictional planet 3.7 light years beyond the heliopause, the Planet of Wishes. It weaves stardust into schemas, frontend, backend, and specs.",
        "Intara forges: schemas (prisma+sql), frontend (Vite React+TS+Tailwind), backend (FastAPI+Pydantic), scroll (PRD+OpenAPI+cites). Runnable zip, shareable link.",
        "Intara stack: Vite React 18 + TypeScript + Tailwind, FastAPI, Supabase pgvector, Prisma, Gemini free tier. No preview/deploy v1.",
        "Constellation: each wish becomes a star, hashed id for position, appName for size, forming Intara sigil.",
    ]
    for t in texts:
        # try 3072 first, fallback to 1536 truncated, then no embedding
        emb = embed([t])[0]
        try:
            supabase.table("docs").insert({"content": t, "embedding": emb}).execute()
        except Exception as e:
            # try truncated 1536 for legacy table
            try:
                emb1536 = emb[:1536]
                supabase.table("docs").insert({"content": t, "embedding": emb1536}).execute()
            except Exception as e2:
                print(f"seed insert failed (dim 3072 & 1536): {e} | {e2}")
                try: supabase.table("docs").insert({"content": t}).execute()
                except Exception as e3: print(f"seed fallback failed: {e3}")
    print("seeded")

if __name__ == "__main__":
    print(answer("What stack does DhiWise use?"))
