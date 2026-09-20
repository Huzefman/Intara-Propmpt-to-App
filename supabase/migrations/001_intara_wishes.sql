-- Intara — Planet of Wishes — Migration 001
-- Extends original schema.sql with wishes table and fixes vector dim

-- 1. Fix docs embedding dim: gemini-embedding-001 is 3072d, not 1536
-- If docs already exists with 1536, alter it. Keep backward compat by recreating.
alter table if exists docs alter column embedding type vector(3072) using embedding::text::vector(3072);

-- Ensure vector extension still exists
create extension if not exists vector;

-- Recreate match_docs to use 3072
create or replace function match_docs(query_embedding vector(3072), match_count int)
returns table(id uuid, content text, similarity float)
language sql stable as $$
  select id, content, 1 - (embedding <=> query_embedding) as similarity
  from docs
  order by embedding <=> query_embedding
  limit match_count;
$$;

-- 2. Wishes — core Intara table
create table if not exists wishes (
  id uuid primary key default gen_random_uuid(),
  owner uuid references auth.users(id) on delete set null,
  prompt text not null,
  prd jsonb not null default '{}'::jsonb,
  artifacts jsonb not null default '{}'::jsonb,
  status text not null default 'ready' check (status in ('weaving','ready','failed')),
  created_at timestamptz not null default now()
);

-- Index for constellation ordering
create index if not exists wishes_created_at_idx on wishes (created_at desc);
create index if not exists wishes_owner_idx on wishes (owner);

-- 3. RLS for wishes
alter table wishes enable row level security;

drop policy if exists "owners full" on wishes;
create policy "owners full"
  on wishes for all
  using (auth.uid() = owner or owner is null)
  with check (auth.uid() = owner or owner is null);

drop policy if exists "public read demo" on wishes;
create policy "public read demo"
  on wishes for select
  using (true);

-- Keep original schemas table RLS as is (allow all for demo)
-- For wishes, tighten later: drop public read, keep only owners.

-- 4. Wish logs for rate limiting (optional, not RLS needed for anon)
create table if not exists wish_logs (
  id uuid primary key default gen_random_uuid(),
  ip text not null,
  created_at timestamptz not null default now()
);
create index if not exists wish_logs_ip_created_idx on wish_logs (ip, created_at);
alter table wish_logs enable row level security;
drop policy if exists "allow all logs" on wish_logs;
create policy "allow all logs" on wish_logs for all using (true) with check (true);

-- 5. Backfill note: existing schemas rows remain, wishes starts empty.
-- To reseed docs with correct dim, run: python -c "from rag import seed_docs; seed_docs()"
