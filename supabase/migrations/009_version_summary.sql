-- Migration 009 — version summaries (Phase 9, slice 1).
-- ADDITIVE ONLY: one nullable column. Human summaries make the version
-- timeline readable (chat/LLM summaries stored at creation; auto-summaries
-- for deterministic operations).
alter table project_versions add column if not exists summary text;
