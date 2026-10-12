"""
Exemplar retrieval (Phase 5, P5.2/P5.3).

Few-shot for the planner: embed the wish, cosine-scan the exemplar corpus,
return the nearest specs (with tag filters). Vectors are 768-d per guide
(free-tier frugality); the live path truncates the 3072-d provider vectors.

Held-out domains (guide Appendix D #6–10) are NEVER indexed — the builder
refuses them, so generalisation is measured honestly (P5.3).

Deviation (AGENT.md): vectors live in a versioned JSON index
(evals/retrieval_index.json), not in Supabase — the exemplars table pins
specs; the index file keeps dims flexible and diffs reviewable. DB-backed
vectors land when retrieval serves production traffic.
"""
from __future__ import annotations

import json
import math

DIM = 768

# Appendix D #6–10: held OUT of the corpus, used only to measure generalisation.
HELDOUT_DOMAINS = {
    "invoicing",
    "restaurant_orders",
    "gym_membership",
    "school_fees",
    "helpdesk",
}


def text_of_spec(spec: dict) -> str:
    """Embeddable text for one App Spec (names, domain, entities, pages, reqs)."""
    app = spec.get("app") or {}
    parts = [str(app.get("name") or ""), str(app.get("tagline") or ""),
             str(app.get("domain") or "")]
    for e in (spec.get("model") or {}).get("entities") or []:
        parts.append(str(e.get("label") or e.get("id") or ""))
        for f in e.get("fields") or []:
            parts.append(str(f.get("id") or ""))
    for p in (spec.get("ui") or {}).get("pages") or []:
        parts.append(str(p.get("title") or p.get("id") or ""))
    for r in spec.get("requirements") or []:
        parts.append(str(r.get("text") or ""))
    return " ".join(p for p in parts if p)


def tags_of_spec(spec: dict) -> list:
    app = spec.get("app") or {}
    tags = []
    if app.get("domain"):
        tags.append(str(app["domain"]))
    arch = ((spec.get("ui") or {}).get("theme") or {}).get("archetype")
    if arch:
        tags.append(str(arch))
    return sorted(set(tags))


def _fit_dim(vec: list) -> list:
    """Truncate/pad any vector to DIM (prefix keeps Matryoshka order)."""
    try:
        xs = [float(x) for x in (vec or [])]
    except Exception:
        xs = []
    if len(xs) >= DIM:
        return xs[:DIM]
    return xs + [0.0] * (DIM - len(xs))


def embed_texts_768(texts: list, embed_fn=None) -> list:
    """Embed to DIM-d vectors. embed_fn(texts)->vectors injects fakes (tests)."""
    if embed_fn is not None:
        return [_fit_dim(v) for v in embed_fn(texts)]
    try:
        from services.llm import embed_texts
        return [_fit_dim(v) for v in embed_texts(texts)]
    except Exception as e:
        print(f"retrieval embed failed, zero vectors: {e}")
        return [[0.0] * DIM for _ in texts]


def _norm(vec: list) -> list:
    n = math.sqrt(sum(x * x for x in vec))
    if n == 0:
        return vec
    return [x / n for x in vec]


def cosine(a: list, b: list) -> float:
    return sum(x * y for x, y in zip(_norm(a), _norm(b)))


def build_index(items: list, embed_fn=None) -> dict:
    """items: [{id, domain, tags, text}]. Refuses held-out domains (fail-fast)."""
    for it in items:
        if (it.get("domain") or "") in HELDOUT_DOMAINS:
            raise ValueError(f"held-out domain {it['domain']!r} must never be indexed")
    texts = [it.get("text") or "" for it in items]
    vecs = embed_texts_768(texts, embed_fn=embed_fn)
    return {"dim": DIM,
            "items": [{"id": it["id"], "domain": it.get("domain"),
                       "tags": it.get("tags") or [], "vector": v}
                      for it, v in zip(items, vecs)]}


def search(index: dict, query_text: str, *, tags=None, top_k: int = 3,
           embed_fn=None) -> list:
    """Cosine scan over the index; optional tag filter (any-match)."""
    qv = embed_texts_768([query_text], embed_fn=embed_fn)[0]
    if all(x == 0 for x in qv):
        return []
    scored = []
    for it in index.get("items") or []:
        if tags and not (set(tags) & set(it.get("tags") or [])):
            continue
        scored.append({"id": it["id"], "domain": it.get("domain"),
                       "tags": it.get("tags") or [],
                       "score": round(cosine(qv, it.get("vector") or []), 4)})
    scored.sort(key=lambda h: h["score"], reverse=True)
    return scored[:top_k]


def index_to_json(index: dict) -> str:
    return json.dumps(index, separators=(",", ":"))


def index_from_json(raw: str) -> dict:
    idx = json.loads(raw)
    if idx.get("dim") != DIM:
        raise ValueError(f"index dim {idx.get('dim')} != {DIM}")
    return idx
