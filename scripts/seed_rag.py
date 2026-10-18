#!/usr/bin/env python3
"""
Reseed the RAG archives (Supabase `docs`) with the current project corpus.

    python scripts/seed_rag.py

- Embeds every chunk from `server/rag_corpus.py` first — and ABORTS before
  touching the DB if embeddings are unavailable or come back as zero vectors.
- Then deletes the old rows (needs SUPABASE_SERVICE_KEY for the DELETE policy;
  falls back to the anon key with a clear error if the delete matches 0 rows).
- Then inserts in batches and verifies the final count.

Exit codes: 0 ok · 2 no supabase config · 3 embeddings unavailable · 4 delete
blocked · 5 verification failed.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "server" / ".env")

from rag import reseed_docs  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(reseed_docs())
