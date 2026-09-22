-- Migration 004 — Chat-driven rewrites (diff-first, one-click revert)
-- Apply after 003 in Supabase SQL editor. Fail-open: backend keeps pending
-- previews in memory and applies without snapshots if this table is missing.
create table if not exists wish_iterations (
  id uuid primary key default gen_random_uuid(),
  wish_id uuid not null references wishes(id) on delete cascade,
  step_id text not null,
  instruction text not null,
  files_changed jsonb not null default '[]'::jsonb,
  prev_artifacts jsonb,
  status text not null default 'preview' check (status in ('preview','applied','reverted','discarded')),
  created_at timestamptz not null default now()
);
create index if not exists wish_iterations_wish_idx on wish_iterations (wish_id, created_at);
alter table wish_iterations enable row level security;
drop policy if exists "public read demo" on wish_iterations;
create policy "public read demo" on wish_iterations for select using (true);
drop policy if exists "allow all writes" on wish_iterations;
create policy "allow all writes" on wish_iterations for all using (true) with check (true);
