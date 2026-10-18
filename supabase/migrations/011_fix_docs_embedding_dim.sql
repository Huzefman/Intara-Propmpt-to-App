-- 011 — repair docs.embedding dimension drift.
--
-- Why this exists: v1 shipped docs.embedding as vector(1536). Migration 002
-- tried to widen it to vector(3072) (matching match_docs and Gemini's native
-- output) but wrapped the ALTER in `exception when others then null` — the
-- cast failed silently on the non-empty table, leaving the column at 1536
-- while match_docs was recreated for 3072. Result: every vector query dies
-- with "different vector dimensions 1536 and 3072".
--
-- Safe to run anytime: the archives corpus is fully re-seedable with
-- `python scripts/seed_rag.py` (delete + re-embed + insert), so dropping the
-- old rows here costs nothing.

delete from docs;

-- Empty table → the USING clause is vacuous; no cast can fail.
alter table docs
  alter column embedding type vector(3072)
  using embedding::text::vector(3072);

create or replace function match_docs(query_embedding vector(3072), match_count int)
returns table(id uuid, content text, similarity float)
language sql stable as $$
  select id, content, 1 - (embedding <=> query_embedding) as similarity
  from docs
  order by embedding <=> query_embedding
  limit match_count;
$$;
