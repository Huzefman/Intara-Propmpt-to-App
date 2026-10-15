-- Migration 007 — Data plane (Phase 8, P8.1; guide Appendix E + ADR-2 option A).
-- ADDITIVE ONLY: new tables, no alterations to existing objects.
-- One shared `records` table (JSONB data): schema changes are metadata edits,
-- no DDL per app, trivially multi-tenant, free-tier friendly. RLS enabled
-- with NO permissive policies: service-key access from the API only
-- (same posture as 006 control-plane tables).
create table if not exists apps (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references projects(id) on delete cascade,
  pinned_version_id uuid references project_versions(id),
  published boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists apps_project_idx on apps (project_id) where project_id is not null;

create table if not exists records (
  id uuid primary key default gen_random_uuid(),
  app_id uuid not null references apps(id) on delete cascade,
  entity text not null,
  data jsonb not null,
  version int not null default 1,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);
create index if not exists records_app_entity_idx on records (app_id, entity) where deleted_at is null;
create index if not exists records_data_idx on records using gin (data jsonb_path_ops);

alter table apps enable row level security;
alter table records enable row level security;
