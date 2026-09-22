-- Migration 003 — Wish-scoped custom chat (Q&A + action hints), persisted history
-- Apply after 002 in Supabase SQL editor. Fail-open: backend works session-only if table missing.
create table if not exists wish_messages (
  id uuid primary key default gen_random_uuid(),
  wish_id uuid not null references wishes(id) on delete cascade,
  role text not null check (role in ('user','agent')),
  content text not null,
  created_at timestamptz not null default now()
);
create index if not exists wish_messages_wish_idx on wish_messages (wish_id, created_at);
alter table wish_messages enable row level security;
drop policy if exists "public read demo" on wish_messages;
create policy "public read demo" on wish_messages for select using (true);
drop policy if exists "allow all inserts" on wish_messages;
create policy "allow all inserts" on wish_messages for insert with check (true);
