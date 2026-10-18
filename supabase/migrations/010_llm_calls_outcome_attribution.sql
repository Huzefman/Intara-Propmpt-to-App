-- Migration 010 — parse-outcome attribution on llm_calls (additive, Phase 2 follow-up).
--
-- The recorder inserts append-only rows the moment a provider call returns;
-- the parse outcome is only known AFTER JSON parsing, so the agent stamps it
-- with a follow-up UPDATE keyed by row id (services/telemetry.set_parse_outcome).
--
-- Narrow on purpose:
--   * column grants restrict anon/authenticated to exactly the two attribution
--     columns — provider/model/tokens/latency/fallback_reason stay write-once;
--   * the policy only allows UPDATE (insert + select policies from 006a remain).
--
-- ADDITIVE ONLY: no existing policy, grant or row is dropped or altered.

revoke update on llm_calls from anon, authenticated;
grant update (parse_outcome, repair_used) on llm_calls to anon, authenticated;

drop policy if exists "llm calls attribute outcome" on llm_calls;
create policy "llm calls attribute outcome" on llm_calls
  for update using (true) with check (true);
