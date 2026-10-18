"""
RAG archives tests — no network, no keys (fake clients + monkeypatched LLM).

Covers:
- corpus sanity (curated project chunks, no stale v1 text)
- chunker overlap and edges
- BM25 lexical ranking (pure function)
- embed() refuses zero vectors / wrong counts (EmbeddingUnavailable)
- answer(): vector path, lexical fallback, demo mode, synthesis failure
- reseed: aborts before DB touch when embeddings fail; refuses partial delete;
  inserts in batches and verifies count
Run: pytest tests/test_rag.py -v
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)


# ———————————————————————— fakes ————————————————————————

class _Exec:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _Table:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def delete(self):
        return self

    def neq(self, *a, **k):
        return self

    def insert(self, rows):
        self.rows = self.rows + (rows if isinstance(rows, list) else [rows])
        return _Exec([])

    def execute(self):
        return _Exec(self.rows)


class FakeSupa:
    def __init__(self, docs=None, rpc_res=None, match_error=None, dim_errors=None):
        self.docs = docs or []
        self.rpc_res = rpc_res or []
        self.match_error = match_error
        self.dim_errors = dim_errors or {}  # embedding length -> error message
        self.match_calls = []

    def table(self, name):
        return _Table(self.docs)

    def rpc(self, fn, args):
        self.match_calls.append((fn, args))
        dim = len(args["query_embedding"])
        if dim in self.dim_errors:
            raise RuntimeError(self.dim_errors[dim])
        if self.match_error:
            raise self.match_error
        return _Exec(self.rpc_res)


class _ReseedClient:
    def __init__(self, rows_before=5, delete_works=True, insert_dim_errors=None):
        self.rows = [{"id": str(i)} for i in range(rows_before)]
        self.delete_works = delete_works
        self.insert_dim_errors = insert_dim_errors or {}  # embedding length -> error message
        self.deleted = False
        self.wipes = 0
        self.inserted_batches = []

    def table(self, name):
        return self

    def select(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def delete(self):
        self.deleted = True
        return self

    def neq(self, *a, **k):
        self.wipes += 1
        if self.delete_works:
            self.rows = []
        return self

    def insert(self, rows):
        dim_err = self.insert_dim_errors.get(len(rows[0]["embedding"]))
        if dim_err:
            raise RuntimeError(dim_err)
        self.inserted_batches.append(rows)
        self.rows.extend(rows)
        return _Exec([])

    def execute(self):
        return _Exec(self.rows)


@pytest.fixture(autouse=True)
def _reset_rag_cache():
    """Keep dimension/cosine caches from leaking across tests."""
    import rag
    rag._resolved_dim = None
    rag._client_cosine = False
    rag._cosine_rows = None
    yield
    rag._resolved_dim = None
    rag._client_cosine = False
    rag._cosine_rows = None


# ———————————————————————— corpus ————————————————————————

def test_corpus_sanity():
    from rag_corpus import PROJECT_DOCS
    assert len(PROJECT_DOCS) >= 30, "corpus should cover the project broadly"
    assert len(set(PROJECT_DOCS)) == len(PROJECT_DOCS), "no duplicate chunks"
    for text in PROJECT_DOCS:
        assert isinstance(text, str)
        assert 40 <= len(text) <= 600, f"chunk too short/long: {text[:60]}"
        assert text.strip() == text
    joined = " ".join(PROJECT_DOCS)
    assert "Intara" in joined
    for stale in ("DhiWise", "Rocket.new", "Prisma"):
        assert stale not in joined, f"stale v1 text leaked into the corpus: {stale}"


def test_chunk_overlap_and_edges():
    from rag import chunk
    text = "abcdefghij" * 100  # 1000 chars
    chunks = chunk(text, size=400, overlap=50)
    assert len(chunks) == 3
    assert len(chunks[0]) == 400
    assert chunks[0][-50:] == chunks[1][:50]  # overlap preserved
    assert chunk("") == []
    assert chunk("short") == ["short"]


# ———————————————————————— lexical ————————————————————————

def test_bm25_ranks_the_relevant_doc():
    from rag import bm25_rank
    docs = [
        {"content": "The formula language is a hand-written parser with no eval."},
        {"content": "Free-tier quota dominates failures; 429s are the top cause."},
        {"content": "The demo gallery bundles ten gold apps for the browser."},
    ]
    top = bm25_rank("how does the formula language work", docs, top_k=1)
    assert top and "formula" in top[0]["content"]


def test_bm25_empty_and_limit():
    from rag import bm25_rank
    docs = [{"content": "alpha beta"}, {"content": "gamma delta"}]
    assert bm25_rank("", docs) == []
    assert bm25_rank("!!!!", docs) == []
    assert len(bm25_rank("alpha gamma", docs, top_k=2)) == 2
    assert bm25_rank("nothingmatcheshere zzz", docs) == []


# ———————————————————————— embed guard ————————————————————————

def test_embed_raises_on_zero_vectors(monkeypatch):
    import rag
    monkeypatch.setattr(rag, "_embed_via_chain", lambda texts: [[0.0] * 3072 for _ in texts])
    with pytest.raises(rag.EmbeddingUnavailable):
        rag.embed(["hello"])


def test_embed_raises_on_wrong_count(monkeypatch):
    import rag
    monkeypatch.setattr(rag, "_embed_via_chain", lambda texts: [[0.5] * 3072])
    with pytest.raises(rag.EmbeddingUnavailable):
        rag.embed(["a", "b"])


def test_embed_passes_through(monkeypatch):
    import rag
    monkeypatch.setattr(rag, "_embed_via_chain", lambda texts: [[1.5] * 4 for _ in texts])
    out = rag.embed(["a", "b"])
    assert len(out) == 2 and out[0][0] == 1.5


# ———————————————————————— answer() ————————————————————————

def _patch_llm(monkeypatch, text="Grounded answer [1].", meta=None, raises=None):
    import services.llm as llm

    calls = {}

    def fake(prompt, temperature=0.2, **kw):
        calls["prompt"] = prompt
        if raises:
            raise raises
        return text, (meta or {"source": "groq", "model": "openai/gpt-oss-20b"})

    monkeypatch.setattr(llm, "call_llm_with_meta", fake)
    return calls


def test_answer_lexical_fallback(monkeypatch):
    import rag
    sup = FakeSupa(docs=[
        {"content": "Intara runs on free-tier providers with quota-aware fallback."},
        {"content": "The runtime executes validated specs in the browser."},
    ])
    monkeypatch.setattr(rag, "supabase", sup)
    monkeypatch.setattr(rag, "_has_llm", lambda: True)
    monkeypatch.setattr(rag, "embed", lambda texts: (_ for _ in ()).throw(rag.EmbeddingUnavailable("no keys")))

    calls = _patch_llm(monkeypatch)
    res = rag.answer("Which providers does Intara use?")
    assert res["retrieval"] == "lexical"
    assert res["provider"] == "groq"
    assert res["cites"] and "free-tier" in res["cites"][0]
    assert "[1]" in calls["prompt"] and "Which providers does Intara use?" in calls["prompt"]


def test_answer_vector_path(monkeypatch):
    import rag
    docs = [{"content": f"fact {i}"} for i in range(5)]
    sup = FakeSupa(docs=[], rpc_res=docs)
    monkeypatch.setattr(rag, "supabase", sup)
    monkeypatch.setattr(rag, "_has_llm", lambda: True)
    monkeypatch.setattr(rag, "embed", lambda texts: [[0.2] * 3072 for _ in texts])

    _patch_llm(monkeypatch)
    res = rag.answer("anything")
    assert res["retrieval"] == "vector"
    assert res["retrieval_detail"] == "match_docs"
    assert len(res["cites"]) == 5
    fn, args = sup.match_calls[0]
    assert fn == "match_docs" and args["match_count"] == 5 and len(args["query_embedding"]) == 3072


def test_answer_lexical_when_match_errors(monkeypatch):
    import rag
    sup = FakeSupa(docs=[{"content": "quota 429 quota 429"}, {"content": "unrelated"}],
                   match_error=RuntimeError("match_docs rpc exploded"))
    monkeypatch.setattr(rag, "supabase", sup)
    monkeypatch.setattr(rag, "_has_llm", lambda: True)
    monkeypatch.setattr(rag, "embed", lambda texts: [[0.2] * 3072 for _ in texts])

    _patch_llm(monkeypatch)
    res = rag.answer("what about quota?")
    assert res["retrieval"] == "lexical"
    assert "quota" in res["cites"][0]


def test_vector_search_adapts_to_live_dim(monkeypatch):
    """Live docs table may be vector(1536) while migrations say 3072."""
    import rag
    docs = [{"content": "dim-adaptive fact"}]
    sup = FakeSupa(rpc_res=docs, dim_errors={3072: "expected 1536 dimensions, not 3072"})
    monkeypatch.setattr(rag, "supabase", sup)
    monkeypatch.setattr(rag, "_has_llm", lambda: True)
    monkeypatch.setattr(rag, "embed", lambda texts: [[0.2] * 3072 for _ in texts])

    _patch_llm(monkeypatch)
    res = rag.answer("anything")
    assert res["retrieval"] == "vector"
    assert res["retrieval_detail"] == "match_docs"
    assert len(sup.match_calls) == 2, "should retry once with the DB's reported dimension"
    assert len(sup.match_calls[0][1]["query_embedding"]) == 3072
    assert len(sup.match_calls[1][1]["query_embedding"]) == 1536
    assert rag._resolved_dim == 1536


def test_schema_drift_falls_back_to_client_cosine(monkeypatch):
    """match_docs(3072) over a 1536 column: no query dim can work — cosine client-side."""
    import rag
    sup = FakeSupa(
        docs=[
            {"content": "near fact", "embedding": "[1.0, 0.0, 0.0]"},
            {"content": "far fact", "embedding": "[0.0, 1.0, 0.0]"},
        ],
        dim_errors={3072: "different vector dimensions 1536 and 3072"},
    )
    monkeypatch.setattr(rag, "supabase", sup)
    monkeypatch.setattr(rag, "_has_llm", lambda: True)
    monkeypatch.setattr(rag, "embed", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])

    _patch_llm(monkeypatch)
    res = rag.answer("which fact is near?")
    assert res["retrieval"] == "vector"
    assert res["retrieval_detail"] == "client-cosine"
    assert res["cites"] == ["near fact"], "cosine ranking must put the aligned vector first"
    assert rag._client_cosine is True
    # second question short-circuits match_docs entirely (mode cached)
    n_calls = len(sup.match_calls)
    rag.answer("again")
    assert len(sup.match_calls) == n_calls


def test_parse_embedding_and_cosine():
    import rag
    assert rag._parse_embedding([1, 2.5]) == [1.0, 2.5]
    assert rag._parse_embedding("[1.0,2.0,3.0]") == [1.0, 2.0, 3.0]
    assert rag._parse_embedding("[1e-05,2.0]")[0] == 1e-05
    assert rag._parse_embedding(None) == []
    assert rag._parse_embedding("") == []
    assert rag._cosine([1, 0], [1, 0]) == 1.0
    assert rag._cosine([1, 0], [0, 1]) == 0.0
    assert rag._cosine([], [1]) == 0.0


def test_clean_answer_unwraps_envelopes():
    import rag
    assert rag._clean_answer('{"answer": "Unwrapped [1]."}') == "Unwrapped [1]."
    assert rag._clean_answer('```json\n{"answer": "Fenced [2]."}\n```') == "Fenced [2]."
    assert rag._clean_answer("Plain prose [3].") == "Plain prose [3]."
    assert rag._clean_answer('{"unrelated": 1}') == '{"unrelated": 1}'
    assert rag._clean_answer("") == ""


def test_answer_unwraps_json_envelope(monkeypatch):
    import rag
    sup = FakeSupa(docs=[{"content": "anything about envelopes"}])
    monkeypatch.setattr(rag, "supabase", sup)
    monkeypatch.setattr(rag, "_has_llm", lambda: True)
    monkeypatch.setattr(rag, "embed", lambda texts: (_ for _ in ()).throw(rag.EmbeddingUnavailable("x")))
    _patch_llm(monkeypatch, text='{"text": "Enveloped fact [1]."}')
    res = rag.answer("anything")
    assert res["answer"] == "Enveloped fact [1]."


def test_answer_demo_mode_without_keys(monkeypatch):
    import rag
    monkeypatch.setattr(rag, "supabase", None)
    monkeypatch.setattr(rag, "_has_llm", lambda: False)
    res = rag.answer("What is Intara?")
    assert "configure" in res["answer"].lower()
    assert res["cites"] == [] and res["retrieval"] is None


def test_answer_with_empty_archive(monkeypatch):
    import rag
    sup = FakeSupa(docs=[], rpc_res=[])
    monkeypatch.setattr(rag, "supabase", sup)
    monkeypatch.setattr(rag, "_has_llm", lambda: True)
    monkeypatch.setattr(rag, "embed", lambda texts: [[0.2] * 3072 for _ in texts])
    res = rag.answer("anything")
    assert "seed_rag" in res["answer"]


def test_answer_survives_synthesis_failure(monkeypatch):
    import rag
    sup = FakeSupa(docs=[{"content": "Intara telemetry records llm_calls."}])
    monkeypatch.setattr(rag, "supabase", sup)
    monkeypatch.setattr(rag, "_has_llm", lambda: True)
    monkeypatch.setattr(rag, "embed", lambda texts: (_ for _ in ()).throw(rag.EmbeddingUnavailable("x")))
    _patch_llm(monkeypatch, raises=RuntimeError("all providers exhausted"))
    res = rag.answer("telemetry?")
    assert "could not be consulted" in res["answer"]
    assert res["cites"], "cites still returned even when synthesis fails"


# ———————————————————————— reseed ————————————————————————

def test_reseed_aborts_before_db_when_embeddings_fail(monkeypatch):
    import rag
    fake = _ReseedClient()
    monkeypatch.setattr(rag, "supabase", fake)
    monkeypatch.setattr(rag, "_service_supabase", lambda: fake)
    monkeypatch.setattr(rag, "embed", lambda texts: (_ for _ in ()).throw(rag.EmbeddingUnavailable("down")))
    assert rag.reseed_docs(verbose=False) == 3
    assert not fake.deleted, "no DB write may happen before embeddings succeed"
    assert fake.inserted_batches == []


def test_reseed_refuses_partial_delete(monkeypatch):
    import rag
    from rag_corpus import PROJECT_DOCS
    fake = _ReseedClient(delete_works=False)
    monkeypatch.setattr(rag, "supabase", fake)
    monkeypatch.setattr(rag, "_service_supabase", lambda: fake)
    monkeypatch.setattr(rag, "embed", lambda texts: [[0.1] * 8 for _ in texts])
    assert rag.reseed_docs(verbose=False) == 4
    assert fake.inserted_batches == [], "must not insert into a non-empty docs table"


def test_reseed_happy_path_batches_and_verifies(monkeypatch):
    import rag
    from rag_corpus import PROJECT_DOCS
    fake = _ReseedClient(rows_before=17)
    monkeypatch.setattr(rag, "supabase", fake)
    monkeypatch.setattr(rag, "_service_supabase", lambda: fake)
    monkeypatch.setattr(rag, "embed", lambda texts: [[0.1] * 8 for _ in texts])
    assert rag.reseed_docs(verbose=False) == 0
    assert len(fake.rows) == len(PROJECT_DOCS)
    assert len(fake.inserted_batches) == (len(PROJECT_DOCS) + 9) // 10
    assert all(len(b) <= 10 for b in fake.inserted_batches)


def test_reseed_adapts_insert_dim(monkeypatch):
    """First batch rejected on dim mismatch → wipe partials → refit → retry."""
    import rag
    from rag_corpus import PROJECT_DOCS
    fake = _ReseedClient(rows_before=17,
                         insert_dim_errors={3072: "expected 1536 dimensions, not 3072"})
    monkeypatch.setattr(rag, "supabase", fake)
    monkeypatch.setattr(rag, "_service_supabase", lambda: fake)
    monkeypatch.setattr(rag, "embed", lambda texts: [[0.1] * 8 for _ in texts])
    assert rag.reseed_docs(verbose=False) == 0
    assert len(fake.rows) == len(PROJECT_DOCS)
    assert rag._resolved_dim == 1536
    assert all(len(b[0]["embedding"]) == 1536 for b in fake.inserted_batches)


def test_reseed_insert_failure_returns_5(monkeypatch):
    import rag
    fake = _ReseedClient(rows_before=3,
                         insert_dim_errors={3072: "connection reset by peer",
                                            1536: "connection reset by peer"})
    monkeypatch.setattr(rag, "supabase", fake)
    monkeypatch.setattr(rag, "_service_supabase", lambda: fake)
    monkeypatch.setattr(rag, "embed", lambda texts: [[0.1] * 8 for _ in texts])
    assert rag.reseed_docs(verbose=False) == 5
    assert fake.inserted_batches == []
