-- Migration 006 — v2 control plane (Phase 4, P4.5; guide Appendix E).
-- ADDITIVE ONLY: new tables + one new FK on 006a's llm_calls.run_id (which
-- was left unconstrained pending this migration). No alterations to existing
-- tables/rows. Data-plane `apps`/`records` are NOT included (later migration).
--
-- Deviations from the Appendix E sketch (recorded in AGENT.md):
-- - `artifacts` table omitted: content-addressing already ships as
--   006b artifact_contents (step contents); generic build blobs land with export.
-- - `llm_calls` omitted (ships as 006a); only its run_id FK is added here.
-- - `exemplars` + `feedback` added (Phase 5 retrieval seed / Phase 9 loop).
-- - RLS enabled with NO permissive policies: service-key access from the API
--   only, per sketch. (006a/006b carry demo-open policies for the anon-fed
--   health endpoints; control-plane rows stay API-only until multi-tenant.)

create table if not exists projects (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references auth.users(id) on delete set null,
  workspace_id uuid,
  name text not null,
  track text not null check (track in ('business', 'freeform')),
  created_at timestamptz not null default now()
);

create table if not exists project_versions (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  parent_id uuid references project_versions(id),
  spec jsonb not null,
  spec_hash text not null,
  source text not null check (source in ('generate', 'iterate', 'manual', 'import')),
  created_at timestamptz not null default now()
);
create index if not exists project_versions_project_idx on project_versions (project_id, created_at desc);

create table if not exists runs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  base_version_id uuid references project_versions(id),
  kind text not null check (kind in ('build', 'iterate', 'eval')),
  status text not null check (status in ('queued', 'running', 'done', 'degraded', 'failed', 'cancelled')),
  budget jsonb not null default '{}'::jsonb,
  started_at timestamptz, ended_at timestamptz, error text
);

create table if not exists run_steps (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references runs(id) on delete cascade,
  step_key text not null,
  agent text not null,
  attempt int not null default 1,
  status text not null check (status in ('pending', 'running', 'done', 'degraded', 'failed', 'skipped')),
  input_hash text, output_hash text,
  fallback_reason text,
  started_at timestamptz, ended_at timestamptz,
  unique (run_id, step_key, attempt)
);

create table if not exists run_events (
  id bigserial primary key,
  run_id uuid not null references runs(id) on delete cascade,
  ts timestamptz not null default now(),
  type text not null,
  payload jsonb not null default '{}'::jsonb
);
create index if not exists run_events_run_idx on run_events (run_id, id);

create table if not exists exemplars (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  domain text not null,
  spec jsonb not null,
  spec_hash text not null,
  source text not null default 'hand-authored' check (source in ('hand-authored', 'promoted', 'imported')),
  created_at timestamptz not null default now(),
  unique (name)
);
create index if not exists exemplars_domain_idx on exemplars (domain);

create table if not exists feedback (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references projects(id) on delete cascade,
  version_id uuid references project_versions(id) on delete set null,
  kind text not null check (kind in ('rating', 'comment', 'correction')),
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists feedback_project_idx on feedback (project_id, created_at desc);

-- Fulfill the 006a NOTE: run_id now references runs(id).
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'llm_calls_run_id_fkey') then
    alter table llm_calls add constraint llm_calls_run_id_fkey
      foreign key (run_id) references runs(id) on delete set null;
  end if;
end $$;

alter table projects enable row level security;
alter table project_versions enable row level security;
alter table runs enable row level security;
alter table run_steps enable row level security;
alter table run_events enable row level security;
alter table exemplars enable row level security;
alter table feedback enable row level security;
