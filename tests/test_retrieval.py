"""
Retrieval + held-out eval — Phase 5 P5.2/P5.3. No network, no keys.
Fake embedder (deterministic bag-of-words) proves the machinery; the live
path reuses services.llm.embed_texts (truncated to 768-d).
- build/search/tag-filter/JSON round-trip
- held-out domains refused at build, never returned at search
- hit-rate on in-corpus domains recorded (asserted ≥ 4/5 top-1)
Run: pytest tests/test_retrieval.py -v
"""
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)

from services.retrieval import (  # noqa: E402
    DIM, HELDOUT_DOMAINS, build_index, cosine, embed_texts_768,
    index_from_json, index_to_json, search, tags_of_spec, text_of_spec,
)


def bow_embed(texts):
    """Deterministic bag-of-words vectors (test double for the embedder)."""
    vecs = []
    for t in texts:
        v = [0.0] * DIM
        for tok in re.findall(r"[a-z]+", (t or "").lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM] += 1.0
        vecs.append(v)
    return vecs


CORPUS = [
    ("repair-tracker", "repair_shop"),
    ("booking", "appointment_booking"),
    ("crm-leads", "crm"),
    ("inventory", "retail_inventory"),
    ("leave-hr", "hr_leave"),
]

QUERIES = [
    ("salon bookings free slots services reminders", "appointment_booking"),
    ("leads pipeline board sales activities deals", "crm"),
    ("stock items reorder warehouse quantities", "retail_inventory"),
    ("repair jobs parts tracker technician billing", "repair_shop"),
    ("leave requests approval employees time off", "hr_leave"),
]

HELDOUT_QUERIES = [
    "invoices line items payments due",
    "restaurant table orders kitchen board",
    "gym memberships expiry recurring payments",
    "school fees students installments",
    "support tickets sla priority assignment",
]


def _corpus_index():
    import json
    items = []
    for name, domain in CORPUS:
        spec = json.load(open(os.path.join(
            ROOT, "packages", "spec", "exemplars", f"{name}.json")))
        assert (spec.get("app") or {}).get("domain") == domain, name
        items.append({"id": name, "domain": domain,
                      "tags": tags_of_spec(spec), "text": text_of_spec(spec)})
    return build_index(items, embed_fn=bow_embed)


def test_embed_dim_and_cosine():
    vecs = embed_texts_768(["hello world", "hello world"], embed_fn=bow_embed)
    assert len(vecs[0]) == DIM
    assert abs(cosine(vecs[0], vecs[1]) - 1.0) < 1e-9
    assert cosine([1.0] + [0.0] * (DIM - 1), [0.0, 1.0] + [0.0] * (DIM - 2)) == 0.0


def test_search_tag_filter_and_round_trip():
    idx = _corpus_index()
    hits = search(idx, "leads pipeline board", embed_fn=bow_embed)
    assert hits and hits[0]["id"] == "crm-leads"
    crm_only = search(idx, "anything at all", tags=["crm"], embed_fn=bow_embed)
    assert crm_only and all(h["id"] == "crm-leads" for h in crm_only)
    assert search(idx, "anything", tags=["nope"], embed_fn=bow_embed) == []
    assert index_from_json(index_to_json(idx))["items"][0]["id"] == "repair-tracker"


def test_hit_rate_on_corpus_domains():
    idx = _corpus_index()
    hits = 0
    for query, want in QUERIES:
        top = search(idx, query, embed_fn=bow_embed, top_k=1)
        got = top[0]["domain"] if top else None
        print(f"query {query[:40]!r:44} -> {got} (want {want})")
        hits += got == want
    print(f"HIT RATE top-1: {hits}/{len(QUERIES)}")
    assert hits >= 4, "hit-rate recorded below bar"


def test_heldout_never_indexed_never_returned():
    assert len(HELDOUT_DOMAINS) == 5, "guide: keep 5 domains out"
    import pytest
    with pytest.raises(ValueError):
        build_index([{"id": "x", "domain": "invoicing",
                      "tags": [], "text": "invoices"}], embed_fn=bow_embed)
    idx = _corpus_index()
    assert not any(i["domain"] in HELDOUT_DOMAINS for i in idx["items"])
    for q in HELDOUT_QUERIES:
        for h in search(idx, q, embed_fn=bow_embed):
            assert h["domain"] not in HELDOUT_DOMAINS
            assert h["id"] in [c[0] for c in CORPUS]
