-- Migration 014 — persist v2 run inputs for retry/resume.
-- ADDITIVE ONLY: one defaulted JSONB column on `runs`.
--
-- Without this, a restarted process can replay completed steps from the
-- content-addressed artifact store but cannot reconstruct the original wish,
-- app name, requirements, or wish_id. A retry would therefore run with empty
-- inputs. The router now writes `inputs` at run creation and the retry
-- endpoint resumes the same run id.
alter table runs
  add column if not exists inputs jsonb not null default '{}'::jsonb;

comment on column runs.inputs is
  'Original request inputs (wish, app_name, requirements, wish_id, budgets) used by retry/resume.';
