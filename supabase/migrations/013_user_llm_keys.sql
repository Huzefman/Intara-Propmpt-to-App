-- Migration 013 — Bring-your-own LLM keys.
--
-- One row per (account, provider). The API key is encrypted by the server
-- (Fernet, `KEY_ENCRYPTION_SECRET`) before it reaches Postgres and is never
-- returned to the browser after saving. Service-key only: RLS is enabled with
-- no policies, so only the FastAPI backend can read or write these rows.
--
-- Apply after 012. Safe to re-run.

create table if not exists user_llm_keys (
  id uuid primary key default gen_random_uuid(),
  owner uuid not null references auth.users(id) on delete cascade,
  provider text not null check (provider in (
    'gemini', 'openrouter', 'groq', 'nvidia', 'deepseek',
    'openai', 'anthropic', 'custom'
  )),
  api_key_enc text not null,
  model text,
  base_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (owner, provider)
);

create index if not exists user_llm_keys_owner_idx
  on user_llm_keys (owner, updated_at desc);

alter table user_llm_keys enable row level security;
-- Deliberately no policies: the service-role key used by the API bypasses RLS,
-- while anon/authenticated clients cannot read encrypted keys or write rows.
