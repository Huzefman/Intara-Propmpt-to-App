-- Migration 012 — Account isolation (multi-tenant public deploy)
-- One Supabase project, many accounts: every wish belongs to exactly one
-- auth user and is invisible to everyone else. The public surface stays
-- read-only (landing + templates); the Studio requires a session.
--
-- Apply after 001–011 in the Supabase SQL editor.
-- Owner decision (Session 36): legacy owner-null wishes are disposable.
--
-- What this migration changes:
--   1. profiles (1 row per auth user) + signup trigger
--   2. deletes legacy owner-null wishes (the old public demo data)
--   3. drops every public-read / open-write policy on wish content
--   4. adds per-user build metering (3 builds/day enforced by the API)
--   5. attributes llm_calls + feedback to users
--   6. storage writes now require a session (public reads stay for previews)

-- ---------------------------------------------------------------------------
-- 1. Profiles — created automatically for every new auth user.
-- ---------------------------------------------------------------------------
create table if not exists profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  display_name text,
  created_at timestamptz not null default now()
);

alter table profiles enable row level security;
drop policy if exists "own profile read" on profiles;
create policy "own profile read" on profiles for select
  using (auth.uid() = id);
drop policy if exists "own profile update" on profiles;
create policy "own profile update" on profiles for update
  using (auth.uid() = id) with check (auth.uid() = id);
drop policy if exists "own profile insert" on profiles;
create policy "own profile insert" on profiles for insert
  with check (auth.uid() = id);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Backfill profiles for accounts that already exist.
insert into profiles (id, email)
select id, email from auth.users
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- 2. Legacy public demo wishes are disposable (approved).
--    Deleting the parents cascades to steps / messages / iterations.
-- ---------------------------------------------------------------------------
delete from wishes where owner is null;

-- ---------------------------------------------------------------------------
-- 3. Owner-only RLS. Public-read and world-writable policies are removed.
--    The API uses the service key and scopes every query by owner as well;
--    these policies protect direct supabase-js reads from the browser.
-- ---------------------------------------------------------------------------
drop policy if exists "public read demo" on wishes;
drop policy if exists "owners full" on wishes;
create policy "owners full" on wishes for all
  using (auth.uid() = owner)
  with check (auth.uid() = owner);

-- Deleting an account deletes its wishes (children cascade), not orphan them.
alter table wishes drop constraint if exists wishes_owner_fkey;
alter table wishes add constraint wishes_owner_fkey
  foreign key (owner) references auth.users(id) on delete cascade;

drop policy if exists "steps public read" on wish_steps;
drop policy if exists "steps owners full" on wish_steps;
create policy "steps owners full" on wish_steps for all
  using (exists (
    select 1 from wishes w
    where w.id = wish_steps.wish_id and w.owner = auth.uid()
  ))
  with check (exists (
    select 1 from wishes w
    where w.id = wish_steps.wish_id and w.owner = auth.uid()
  ));

drop policy if exists "public read demo" on wish_messages;
drop policy if exists "allow all inserts" on wish_messages;
create policy "messages owners full" on wish_messages for all
  using (exists (
    select 1 from wishes w
    where w.id = wish_messages.wish_id and w.owner = auth.uid()
  ))
  with check (exists (
    select 1 from wishes w
    where w.id = wish_messages.wish_id and w.owner = auth.uid()
  ));

drop policy if exists "public read demo" on wish_iterations;
drop policy if exists "allow all writes" on wish_iterations;
create policy "iterations owners full" on wish_iterations for all
  using (exists (
    select 1 from wishes w
    where w.id = wish_iterations.wish_id and w.owner = auth.uid()
  ))
  with check (exists (
    select 1 from wishes w
    where w.id = wish_iterations.wish_id and w.owner = auth.uid()
  ));

drop policy if exists "wish components public read" on wish_components;
drop policy if exists "wish components owners full" on wish_components;
create policy "wish components owners full" on wish_components for all
  using (exists (
    select 1 from wishes w
    where w.id = wish_components.wish_id and w.owner = auth.uid()
  ))
  with check (exists (
    select 1 from wishes w
    where w.id = wish_components.wish_id and w.owner = auth.uid()
  ));

-- Build internals + telemetry: API-only from now on. `llm_calls` stores no
-- prompts, but anonymous append/read lets anyone poison the metrics; generated
-- artifact contents are writable code and must never be world-writable.
drop policy if exists "allow all logs" on wish_logs;
drop policy if exists "llm calls append" on llm_calls;
drop policy if exists "llm calls public read" on llm_calls;
drop policy if exists "llm calls attribute outcome" on llm_calls;
drop policy if exists "artifact contents public read" on artifact_contents;
drop policy if exists "artifact contents allow writes" on artifact_contents;

-- Legacy /generate prompts: API-only from now on (no anon read/write).
drop policy if exists "allow all for demo" on schemas;

-- ---------------------------------------------------------------------------
-- 4. Per-user build metering (3/day). Service-key only: no policies.
-- ---------------------------------------------------------------------------
create table if not exists build_events (
  id uuid primary key default gen_random_uuid(),
  owner uuid not null references auth.users(id) on delete cascade,
  wish_id uuid,
  kind text not null default 'build',
  created_at timestamptz not null default now()
);
create index if not exists build_events_owner_created_idx
  on build_events (owner, created_at desc);
alter table build_events enable row level security;

-- ---------------------------------------------------------------------------
-- 5. Attribution for telemetry + feedback.
-- ---------------------------------------------------------------------------
alter table llm_calls add column if not exists user_id uuid
  references auth.users(id) on delete set null;
create index if not exists llm_calls_user_idx
  on llm_calls (user_id, created_at desc);

alter table feedback add column if not exists user_id uuid
  references auth.users(id) on delete set null;
create index if not exists feedback_user_idx
  on feedback (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- 6. Storage: public reads stay (preview images), writes need a session.
-- ---------------------------------------------------------------------------
drop policy if exists "intara open insert" on storage.objects;
create policy "intara auth insert" on storage.objects for insert
  to authenticated
  with check (bucket_id = 'intara-uploads');

drop policy if exists "intara open delete" on storage.objects;
create policy "intara auth delete" on storage.objects for delete
  to authenticated
  using (bucket_id = 'intara-uploads');

-- ---------------------------------------------------------------------------
-- 7. New wishes can never be ownerless. (All legacy rows were deleted above.)
-- ---------------------------------------------------------------------------
alter table wishes drop constraint if exists wishes_owner_not_null;
alter table wishes add constraint wishes_owner_not_null check (owner is not null);
