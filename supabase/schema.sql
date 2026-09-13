-- Supabase schema — minimal, interview-ready (18 lines + comments)
-- Run in Supabase SQL editor

-- 1. Schemas generated from prompts
create table if not exists schemas (
  id uuid primary key default gen_random_uuid(),
  prompt text not null,
  tables jsonb not null, -- [{name: "users", fields: [{name:"email", type:"text"}]}]
  created_at timestamp with time zone default now()
);

-- 2. Docs for RAG (pgvector)
create extension if not exists vector;
create table if not exists docs (
  id uuid primary key default gen_random_uuid(),
  content text not null,
  embedding vector(1536)
);

-- 3. RLS: user can read own rows (demo: open for anon in interview, tighten later)
alter table schemas enable row level security;
create policy "allow all for demo"
  on schemas for all using (true) with check (true);

-- 4. Vector search RPC (cosine)
create or replace function match_docs(query_embedding vector(1536), match_count int)
returns table(id uuid, content text, similarity float)
language sql stable as $$
  select id, content, 1 - (embedding <=> query_embedding) as similarity
  from docs
  order by embedding <=> query_embedding
  limit match_count;
$$;

-- 5. Example seed (run once)
-- insert into docs(content) values ('DhiWise builds Rocket.new — prompt to app with DB/auth/API.');
