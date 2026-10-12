-- Migration 006a — LLM call telemetry (Phase 2, guide M0.3).
-- ADDITIVE ONLY: new table, no alterations to existing objects.
-- Per-call gateway telemetry: provider/model routing, token usage, latency,
-- structured-output outcome, repair and fallback attribution. Prompts are
-- NEVER stored (no PII in this table).
-- NOTE: run_id has no FK yet — it references runs(id) from the Phase 4
-- control-plane migration; the FK lands there, not here.

create table if not exists llm_calls (
  id bigserial primary key,
  run_id uuid,
  wish_id uuid references wishes(id) on delete cascade,
  step_key text,
  agent text,
  prompt_version text,
  provider text not null,
  model text not null,
  tokens_in int,
  tokens_out int,
  latency_ms int,
  finish_reason text,
  parse_outcome text check (parse_outcome in ('ok', 'repaired', 'llm_repaired', 'failed')),
  repair_used boolean not null default false,
  fallback_reason text,
  created_at timestamptz not null default now()
);
create index if not exists llm_calls_created_idx on llm_calls (created_at desc);
create index if not exists llm_calls_provider_idx on llm_calls (provider, created_at desc);
create index if not exists llm_calls_wish_idx on llm_calls (wish_id, created_at desc)
  where wish_id is not null;

alter table llm_calls enable row level security;
-- Append-only metrics: anyone may insert (no prompt text stored, aggregates only);
-- reads are public so the health endpoint works on any key.
drop policy if exists "llm calls append" on llm_calls;
create policy "llm calls append" on llm_calls for insert with check (true);
drop policy if exists "llm calls public read" on llm_calls;
create policy "llm calls public read" on llm_calls for select using (true);
