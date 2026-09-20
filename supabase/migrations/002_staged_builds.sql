-- Migration 002 — Staged sequential builds: normalized steps, full prompt history, progressing context in Supabase
-- Apply after 001. Fail-fast: no silent MEM fallback — Supabase is source of truth.

-- 1. Ensure wishes exists (may not have been applied — PGRST205 seen in logs)
create table if not exists wishes (
  id uuid primary key default gen_random_uuid(),
  owner uuid references auth.users(id) on delete set null,
  prompt text not null,
  prd jsonb not null default '{}'::jsonb,
  artifacts jsonb not null default '{}'::jsonb,
  status text not null default 'ready' check (status in ('weaving','ready','failed')),
  created_at timestamptz not null default now()
);
create index if not exists wishes_created_at_idx on wishes (created_at desc);
create index if not exists wishes_owner_idx on wishes (owner);
alter table wishes enable row level security;
drop policy if exists "owners full" on wishes;
create policy "owners full" on wishes for all using (auth.uid() = owner or owner is null) with check (auth.uid() = owner or owner is null);
drop policy if exists "public read demo" on wishes;
create policy "public read demo" on wishes for select using (true);

-- 2. Widen wishes for staged pipeline
alter table wishes add column if not exists current_step_id text;
alter table wishes add column if not exists build_graph jsonb default '[]'::jsonb;
alter table wishes add column if not exists updated_at timestamptz not null default now();

-- expand status check to staged states (drop old, recreate)
alter table wishes drop constraint if exists wishes_status_check;
alter table wishes add constraint wishes_status_check check (status in (
  'planning','awaiting_approval','approved','building','weaving','ready','failed'
));

-- trigger to keep updated_at
create or replace function set_wishes_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end;
$$ language plpgsql;
drop trigger if exists wishes_updated_at on wishes;
create trigger wishes_updated_at before update on wishes for each row execute function set_wishes_updated_at();

-- 3. Normalized steps — one row per DAG node, full prompt history
create table if not exists wish_steps (
  id uuid primary key default gen_random_uuid(),
  wish_id uuid not null references wishes(id) on delete cascade,
  step_id text not null,
  kind text not null, -- schema | backend_table | frontend_page | wiring | validate | oneshot
  ref text,
  status text not null default 'pending' check (status in ('pending','running','done','failed')),
  attempt int not null default 1,
  prompt text, -- full rendered prompt for this step
  raw_response text, -- full LLM raw text
  output jsonb, -- files/openapi fragment etc
  error text,
  depends_on jsonb default '[]'::jsonb,
  started_at timestamptz,
  ended_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(wish_id, step_id)
);
create index if not exists wish_steps_wish_id_idx on wish_steps (wish_id);
create index if not exists wish_steps_wish_status_idx on wish_steps (wish_id, status);
create index if not exists wish_steps_step_id_idx on wish_steps (wish_id, step_id);

alter table wish_steps enable row level security;
drop policy if exists "steps owners full" on wish_steps;
create policy "steps owners full" on wish_steps for all
  using (exists (select 1 from wishes w where w.id = wish_id and (w.owner is null or w.owner = auth.uid())))
  with check (exists (select 1 from wishes w where w.id = wish_id and (w.owner is null or w.owner = auth.uid())));
drop policy if exists "steps public read" on wish_steps;
create policy "steps public read" on wish_steps for select using (true);

drop trigger if exists wish_steps_updated_at on wish_steps;
create trigger wish_steps_updated_at before update on wish_steps for each row execute function set_wishes_updated_at();

-- 4. Backfill: existing wishes rows get empty build_graph if null
update wishes set build_graph = '[]'::jsonb where build_graph is null;
update wishes set current_step_id = null where current_step_id is null;

-- 5. Fix docs dim if still 1536 (from 001) — keep 3072 as target
create extension if not exists vector;
-- try alter, ignore if already 3072 or column missing embedding
do $$ begin
  perform 1 from information_schema.columns where table_name='docs' and column_name='embedding';
  if found then
    begin
      execute 'alter table docs alter column embedding type vector(3072) using embedding::text::vector(3072)';
    exception when others then
      -- already 3072 or type mismatch, ignore
      null;
    end;
  end if;
end $$;
create or replace function match_docs(query_embedding vector(3072), match_count int)
returns table(id uuid, content text, similarity float)
language sql stable as $$
  select id, content, 1 - (embedding <=> query_embedding) as similarity
  from docs
  order by embedding <=> query_embedding
  limit match_count;
$$;
