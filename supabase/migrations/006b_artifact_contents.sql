-- Migration 006b — Content-addressed artifact store (Phase 3, P3.1).
-- ADDITIVE ONLY: new table, no alterations to existing objects.
-- Step outputs keep small summaries + content_sha; FULL step contents
-- (file trees with real code, scaffolds, previews) live here by sha256 so a
-- resumed build restores accumulators instead of regenerating (no hollow rows).
create table if not exists artifact_contents (
  sha256 text primary key,
  content jsonb not null,
  byte_size int not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists artifact_contents_created_idx on artifact_contents (created_at desc);

alter table artifact_contents enable row level security;
-- Demo-open posture (cf. wish_iterations): service-key writes in practice;
-- harden with owner-scoped policies at multi-tenant time.
drop policy if exists "artifact contents public read" on artifact_contents;
create policy "artifact contents public read" on artifact_contents for select using (true);
drop policy if exists "artifact contents allow writes" on artifact_contents;
create policy "artifact contents allow writes" on artifact_contents for all using (true) with check (true);
