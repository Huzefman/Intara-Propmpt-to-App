-- Migration 005 — Component registry: composable building blocks for generated apps.
-- ADDITIVE ONLY: no existing table is altered, no data is touched. Safe to apply
-- on a live database. Run in Supabase SQL editor, then: python scripts/seed_components.py

-- 1. Canonical component definitions (mirrors server/components/catalog/*.json).
-- Seeded by scripts/seed_components.py (upsert); the repo JSON files stay the source of truth.
create table if not exists component_defs (
  id text primary key,
  version text not null default '0.1.0',
  kind text not null check (kind in ('entity','page','api','widget','workflow','integration')),
  title text not null default '',
  spec jsonb not null default '{}'::jsonb,
  status text not null default 'planned' check (status in ('stable','experimental','planned')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 2. Per-wish composition record: which components (and configs) a wish was built from.
create table if not exists wish_components (
  id uuid primary key default gen_random_uuid(),
  wish_id uuid not null references wishes(id) on delete cascade,
  component_id text not null references component_defs(id) on delete restrict,
  version text not null default '0.0.0',
  config jsonb not null default '{}'::jsonb,
  status text not null default 'pending' check (status in ('pending','building','done','failed','skipped')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists wish_components_wish_id_idx on wish_components (wish_id);
create index if not exists wish_components_component_id_idx on wish_components (component_id);

-- 3. updated_at triggers (reuses set_wishes_updated_at() from 002 if present)
do $$ begin
  if exists (select 1 from pg_proc where proname = 'set_wishes_updated_at') then
    drop trigger if exists component_defs_updated_at on component_defs;
    create trigger component_defs_updated_at before update on component_defs
      for each row execute function set_wishes_updated_at();
    drop trigger if exists wish_components_updated_at on wish_components;
    create trigger wish_components_updated_at before update on wish_components
      for each row execute function set_wishes_updated_at();
  end if;
end $$;

-- 4. RLS mirrors the wishes posture (owner-scoped, demo-open reads).
alter table component_defs enable row level security;
drop policy if exists "components public read" on component_defs;
create policy "components public read" on component_defs for select using (true);
drop policy if exists "components service write" on component_defs;
create policy "components service write" on component_defs for all
  using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

alter table wish_components enable row level security;
drop policy if exists "wish components owners full" on wish_components;
create policy "wish components owners full" on wish_components for all
  using (exists (select 1 from wishes w where w.id = wish_id and (w.owner is null or w.owner = auth.uid())))
  with check (exists (select 1 from wishes w where w.id = wish_id and (w.owner is null or w.owner = auth.uid())));
drop policy if exists "wish components public read" on wish_components;
create policy "wish components public read" on wish_components for select using (true);
