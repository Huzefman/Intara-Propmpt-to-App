"""
RAG — the Intara Archives.

Ask a question about the project; get a grounded answer with citations.

    question → embed (OpenRouter or Gemini via the provider chain)
             → pgvector cosine top-k (match_docs)
             → synthesize with whichever free LLM has quota, cites enforced

Design rules (learned the hard way in this repo):
- Never a silent zero-vector search: if embeddings are unavailable, retrieval
  falls back to in-process BM25 lexical ranking over the same docs, and the
  response labels the mode (`retrieval: "vector" | "lexical"`).
- Dimension-adaptive: migrations define docs.embedding as vector(3072) but
  older live projects may still be vector(1536) — insert/query fit to whatever
  the DB reports (parsed from its "expected N dimensions" error) and cache it.
- Schema-drift rescue: if match_docs and the column dimension disagree outright
  ("different vector dimensions ..."), retrieval computes cosine client-side
  over the stored vectors instead (`retrieval_detail: "client-cosine"`).
  Applying `supabase/migrations/011_fix_docs_embedding_dim.sql` restores the
  server-side path; the fallback is labelled either way, never silent.
- Answers are grounded strictly in retrieved docs; if the docs don't cover it,
  the model is told to say so instead of inventing facts.
- Corpus lives in `rag_corpus.py` (project facts, curated); reseed with
  `python scripts/seed_rag.py` — which refuses to write zero vectors.
"""
from __future__ import annotations

import json
import math
import os
import re

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPA_URL = os.getenv("SUPABASE_URL", "")
SUPA_KEY = os.getenv("SUPABASE_KEY", "")
SUPA_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

supabase = create_client(SUPA_URL, SUPA_KEY) if SUPA_URL and SUPA_KEY else None


class EmbeddingUnavailable(RuntimeError):
    """Embedding providers (OpenRouter/Gemini) both unavailable — use lexical."""


# ———————————————————————— dimension fitting ————————————————————————
# Schema drift guard: migrations create docs.embedding as vector(3072), but
# older live projects may still be vector(1536). Embedding providers return
# 3072-d vectors (Gemini) — we fit to whatever the DB actually reports,
# parsing "expected N dimensions" from the first error and caching N.

_EMBED_DIMS = [3072, 1536]
_resolved_dim: int | None = None
_EXPECT_DIM_RE = re.compile(r"expected (\d+) dimensions")
_MIXED_DIM_RE = re.compile(r"different vector dimensions (\d+) and (\d+)")
_client_cosine = False          # match_docs unusable (function/column mismatch)
_cosine_rows: list[dict] | None = None


def _fit(vec: list[float], dim: int) -> list[float]:
    v = [float(x) for x in vec][:dim]
    if len(v) < dim:
        v = v + [0.0] * (dim - len(v))
    return v


def _dim_from_error(e: Exception) -> int | None:
    m = _EXPECT_DIM_RE.search(str(e))
    return int(m.group(1)) if m else None


# ———————————————————————— embedding ————————————————————————

def _embed_via_chain(texts: list[str]) -> list[list[float]]:
    from services.llm import embed_texts
    return embed_texts(texts)


def embed(texts: list[str]) -> list[list[float]]:
    """Embed via the provider chain. Raises EmbeddingUnavailable instead of
    returning zero vectors — a zero vector is not an embedding."""
    try:
        vecs = _embed_via_chain(texts)
    except Exception as e:  # provider chain failed entirely
        raise EmbeddingUnavailable(f"provider chain failed: {e}") from e
    clean: list[list[float]] = []
    for v in vecs or []:
        vals = [float(x) for x in (v or [])]
        if not any(x != 0.0 for x in vals):
            raise EmbeddingUnavailable("provider returned a zero vector")
        clean.append(vals)
    if len(clean) != len(texts):
        raise EmbeddingUnavailable(f"got {len(clean)} vectors for {len(texts)} texts")
    return clean


# ———————————————————————— chunking ————————————————————————

def chunk(text: str, size: int = 400, overlap: int = 50) -> list[str]:
    """400-char windows with 50-char overlap — good embedding recall."""
    out: list[str] = []
    for i in range(0, len(text), size - overlap):
        c = text[i:i + size].strip()
        if c:
            out.append(c)
    return out


# ———————————————————————— lexical retrieval ————————————————————————

_STOP = {
    "the", "is", "a", "an", "of", "to", "and", "or", "in", "on", "for", "with",
    "what", "how", "does", "do", "why", "are", "it", "its", "be", "by", "from",
    "as", "that", "this", "at", "was", "were", "can", "you", "your", "about",
    "into", "there", "which", "when", "who", "where", "will", "would", "should",
}


def _tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 1]


def bm25_rank(query: str, docs: list[dict], top_k: int = 5) -> list[dict]:
    """Okapi BM25 over doc contents. Pure function — unit-testable, no network."""
    q = [t for t in _tokens(query) if t not in _STOP]
    if not q or not docs:
        return []
    toks = [_tokens(d.get("content", "")) for d in docs]
    n = len(toks)
    avgdl = sum(len(t) for t in toks) / n if n else 1.0
    df: dict[str, int] = {}
    for t in toks:
        for term in set(t):
            df[term] = df.get(term, 0) + 1
    k1, b = 1.2, 0.75
    scored: list[tuple[float, int]] = []
    for i, t in enumerate(toks):
        if not t:
            continue
        tf: dict[str, int] = {}
        for term in t:
            tf[term] = tf.get(term, 0) + 1
        s = 0.0
        for term in q:
            f = tf.get(term)
            if not f:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(t) / avgdl))
        if s > 0.0:
            scored.append((s, i))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [docs[i] for _, i in scored[:top_k]]


# ———————————————————————— retrieval ————————————————————————

def _all_docs() -> list[dict]:
    rows = supabase.table("docs").select("id,content").limit(1000).execute().data or []
    return [r for r in rows if isinstance(r, dict) and (r.get("content") or "").strip()]


def _parse_embedding(v) -> list[float]:
    """pgvector comes back as a JSON-ish string from PostgREST; accept both."""
    if isinstance(v, list):
        return [float(x) for x in v]
    if isinstance(v, str) and v.strip():
        try:
            parsed = json.loads(v)
            if isinstance(parsed, list):
                return [float(x) for x in parsed]
        except Exception:
            pass
        return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", v)]
    return []


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    num = sum(a[i] * b[i] for i in range(n))
    da = math.sqrt(sum(x * x for x in a[:n]))
    db = math.sqrt(sum(x * x for x in b[:n]))
    return num / (da * db) if da and db else 0.0


def _client_cosine_search(qvec: list[float], top_k: int) -> list[dict]:
    """Cosine over stored embeddings, fetched once per process.

    Used when the live DB's match_docs and column dimensions disagree and no
    query dimension can satisfy both. Same vectors, same metric — just computed
    here instead of in Postgres."""
    global _cosine_rows
    if _cosine_rows is None or _count_docs(supabase) != len(_cosine_rows):
        rows = supabase.table("docs").select("content,embedding").limit(1000).execute().data or []
        _cosine_rows = [r for r in rows if isinstance(r, dict) and (r.get("content") or "").strip()]
    scored: list[tuple[float, dict]] = []
    for r in _cosine_rows:
        vec = _parse_embedding(r.get("embedding"))
        if vec:
            scored.append((_cosine(_fit(qvec, len(vec)), vec), r))
    scored.sort(key=lambda x: -x[0])
    return [{**r, "similarity": s} for s, r in scored[:top_k] if s > 0.0]


def _vector_search(qvec: list[float], top_k: int) -> list[dict]:
    """match_docs with dim-adaptive fitting; caches the dimension that works.

    If the function and the column dimensions disagree outright, permanently
    switches this process to client-side cosine (schema drift, migration 011)."""
    global _resolved_dim, _client_cosine
    if _client_cosine:
        return _client_cosine_search(qvec, top_k)
    candidates = [_resolved_dim] if _resolved_dim else list(_EMBED_DIMS)
    last: Exception | None = None
    for dim in candidates:
        try:
            res = supabase.rpc("match_docs", {"query_embedding": _fit(qvec, dim), "match_count": top_k}).execute()
            _resolved_dim = dim
            return [d for d in (res.data or []) if isinstance(d, dict) and (d.get("content") or "").strip()]
        except Exception as e:
            if _MIXED_DIM_RE.search(str(e)):
                print(f"rag: schema drift — match_docs vs column dims ({e}); using client-side cosine")
                _client_cosine = True
                return _client_cosine_search(qvec, top_k)
            expected = _dim_from_error(e)
            if expected:
                last = e
                if expected not in candidates:
                    candidates.append(expected)
                continue
            raise
    raise last or RuntimeError("match_docs failed on every candidate dimension")


def retrieve(question: str, top_k: int = 5) -> tuple[list[dict], str | None, str | None]:
    """(docs, retrieval_mode, retrieval_detail). Never raises.

    mode: 'vector' | 'lexical' | None · detail: 'match_docs' | 'client-cosine' | None"""
    if not supabase:
        return [], None, None
    try:
        qvec = embed([question])[0]
        docs = _vector_search(qvec, top_k)
        if docs:
            return docs, "vector", ("client-cosine" if _client_cosine else "match_docs")
        print("rag: vector search returned no docs → lexical fallback")
    except EmbeddingUnavailable as e:
        print(f"rag: embeddings unavailable ({e}) → lexical fallback")
    except Exception as e:
        print(f"rag: vector search failed ({e}) → lexical fallback")
    docs = bm25_rank(question, _all_docs(), top_k)
    return docs, ("lexical" if docs else None), ("bm25" if docs else None)


# ———————————————————————— synthesis ————————————————————————

DEMO_MSG = (
    "The archives need a backend: configure SUPABASE plus at least one LLM key "
    "(OPENROUTER / GEMINI / GROQ / NVIDIA / DEEPSEEK) to ask questions about Intara."
)


def _has_llm() -> bool:
    try:
        from services.llm import has_any_llm
        return has_any_llm()
    except Exception:
        return bool(
            os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")
            or os.getenv("GROQ_API_KEY") or os.getenv("NVIDIA_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
        )


def _clean_answer(text: str) -> str:
    """Providers sometimes wrap prose in fences or {"answer": ...} envelopes —
    same parse-ladder philosophy as the build pipeline: unwrap, never display raw."""
    t = (text or "").strip()
    if not t:
        return t
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    if t.startswith("{"):
        try:
            obj = json.loads(t)
            if isinstance(obj, dict):
                for key in ("answer", "text", "response", "content"):
                    v = obj.get(key)
                    if isinstance(v, str) and v.strip():
                        return v.strip()
        except Exception:
            pass
    return t


def answer(question: str, top_k: int = 5) -> dict:
    """Grounded answer + cites + retrieval mode/detail + answering provider."""
    empty = {"answer": "", "cites": [], "retrieval": None, "retrieval_detail": None,
             "provider": None, "model": None}
    if not supabase or not _has_llm():
        return {**empty, "answer": DEMO_MSG}
    docs, mode, detail = retrieve(question, top_k)
    if not docs:
        return {**empty, "answer": "The archives are empty — run `python scripts/seed_rag.py` to load the Intara project docs."}
    context = "\n\n".join(f"[{i + 1}] {d['content']}" for i, d in enumerate(docs))
    prompt = (
        "You are the Intara archives assistant. Answer the question using ONLY the "
        "numbered context below.\n"
        "Cite the sources you used inline, like [1] or [2]. If the context does not "
        "contain the answer, say you don't know and name what IS covered by the "
        "archives. Keep it factual, 2-5 sentences, no marketing language.\n"
        "Reply with the prose answer only — no JSON, no code fences, no headings.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}"
    )
    cites = [d["content"] for d in docs]
    try:
        from services.llm import call_llm_with_meta
        text, meta = call_llm_with_meta(prompt, temperature=0.2)
    except Exception as e:
        return {**empty, "answer": f"The archives could not be consulted right now — try again in a few seconds. ({e})",
                "cites": cites, "retrieval": mode, "retrieval_detail": detail}
    return {
        "answer": _clean_answer(text),
        "cites": cites,
        "retrieval": mode,
        "retrieval_detail": detail,
        "provider": meta.get("source") or meta.get("provider"),
        "model": meta.get("model"),
    }


# ———————————————————————— reseeding ————————————————————————

def _service_supabase():
    """Service key when configured (docs DELETE needs it); anon otherwise."""
    if SUPA_URL and SUPA_SERVICE_KEY and SUPA_SERVICE_KEY != SUPA_KEY:
        return create_client(SUPA_URL, SUPA_SERVICE_KEY)
    return supabase


def _count_docs(client) -> int:
    return len(client.table("docs").select("id").limit(1000).execute().data or [])


_ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def _wipe_docs(client) -> None:
    client.table("docs").delete().neq("id", _ZERO_UUID).execute()


def _insert_docs(svc, texts: list[str], vecs: list[list[float]]) -> int:
    """Insert in batches with dim-adaptive fitting; returns the dim used.

    On a dimension-mismatch error, wipes partial rows, refits to the DB's
    reported dimension, and retries once; caches the working dimension."""
    global _resolved_dim
    candidates = [_resolved_dim] if _resolved_dim else list(_EMBED_DIMS)
    i = 0
    while i < len(candidates):
        dim = candidates[i]
        try:
            for off in range(0, len(texts), 10):
                rows = [{"content": t, "embedding": _fit(v, dim)}
                        for t, v in zip(texts[off:off + 10], vecs[off:off + 10])]
                svc.table("docs").insert(rows).execute()
            _resolved_dim = dim
            return dim
        except Exception as e:
            expected = _dim_from_error(e)
            _wipe_docs(svc)  # partial batches from the failed attempt
            if expected and expected not in candidates:
                candidates.append(expected)
            i += 1
            if i >= len(candidates):
                raise
    raise RuntimeError("insert failed on every candidate dimension")


def reseed_docs(verbose: bool = True) -> int:
    """Replace the docs corpus with PROJECT_DOCS. 0 = ok, non-zero = failed.

    Order matters: embed first (abort before touching the DB on zero vectors),
    then delete, verify the delete landed, then insert dim-adapted batches."""
    if not supabase:
        print("reseed: SUPABASE_URL/SUPABASE_KEY missing (server/.env)")
        return 2
    from rag_corpus import PROJECT_DOCS
    texts = list(PROJECT_DOCS)
    try:
        vecs = embed(texts)
    except EmbeddingUnavailable as e:
        print(f"reseed aborted before touching the DB — embeddings unavailable: {e}")
        return 3
    svc = _service_supabase()
    before = _count_docs(svc)
    _wipe_docs(svc)
    remaining = _count_docs(svc)
    if remaining:
        print(f"reseed aborted: DELETE matched 0 rows ({remaining} of {before} remain) — "
              f"set SUPABASE_SERVICE_KEY in server/.env")
        return 4
    try:
        dim = _insert_docs(svc, texts, vecs)
        global _cosine_rows
        _cosine_rows = None  # refresh the client-cosine cache on next use
    except Exception as e:
        print(f"reseed failed while inserting: {e}")
        return 5
    after = _count_docs(svc)
    if verbose:
        print(f"reseeded docs: {before} → {after} rows ({len(texts)} project chunks, "
              f"{dim}-d embeddings)")
    return 0 if after == len(texts) else 5


if __name__ == "__main__":
    print(answer("What is Intara?"))
