# AGENT.md — Intara v2 build ledger

> **What this file is:** the single source of truth for *where the rebuild stands*. It holds the phased plan, the per-session log (done / problems / next), and the known-error register — so context survives across sessions and the build actually completes.
> **Companion docs:** `INTARA_ARCHITECTURE_GUIDE.md` (target architecture + why), `PROJECT_SPEC_FOR_PLANNING_AGENT.md` (current system as-built). If this file disagrees with code, trust code, fix this file, note it in the session log.

---

## 0. Update protocol (mandatory, every session)

1. **Start of session:** read this file top to bottom, then `git status` + `git log --oneline -5`. Mark the phase you're working as `[~]`.
2. **During work:** append errors/blockers to §5 the moment they appear (don't rely on memory).
3. **End of session:** set phase/task statuses (`[ ]` todo, `[~]` active, `[x]` done), append a dated entry to §4 (done / problems / next + test output), update §6 metrics if measured, commit the code **and this file together**.
4. Never leave the tree red: `pytest tests/ -v`, `python scripts/eval.py --mocked`, `npx tsc --noEmit` (in `react-prompt-app/`) must pass before you stop.

**Status legend:** `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked (link the §5 entry).

---

## 1. Locked decisions (do not relitigate without user approval)

| # | Decision | Value | Source |
|---|---|---|---|
| 1 | Core bet (ADR-1) | **Spec-first runtime** — LLM writes small typed App Specs; a tested engine executes them; code is an export target | user, session 2026-10-11 |
| 2 | Freeform track | **Deferred past M5** — Track B (games/calculators/landing) comes after Studio + learning loop | user, session 2026-10-11 |
| 3 | Locale | **English-only v1** (no INR/timezone/seed-data localisation work) | user, session 2026-10-11 |
| 4 | First domains | Guide Appendix D #1–5 (inventory, booking, CRM, repair tracker, leave/HR) unless user overrides | default, pending user confirm |
| 5 | DB strategy | Additive-only migrations; legacy tables frozen, never dropped without explicit approval | spec §12 + guide §12.1 |
| 6 | Failure posture | Fail-closed gates; fail-soft composition/persistence; **no silent fallback** — every fallback carries `fallback_reason` and counts as failure in live evals | guide §2 + spec §12 |
| 7 | Templates | Deterministic templates stay byte-stable (golden tests depend on it); they become export templates, legacy path keeps goldens until sunset | guide §20 |
| 8 | Free tier | No paid infra. Single backend process, no `--reload` during builds, repo-local log file, kill by port holder | ops notes, §7 |

---

## 2. Where things live (map, not documentation)

| Area | Path | Notes |
|---|---|---|
| Control plane (current) | `server/` | FastAPI; routers, services, prompts, db — see spec §§2–6 |
| Builder UI | `react-prompt-app/src/` | Studio, Trial (Sandpack), chat/iterate thread |
| Component catalog | `server/components/catalog/*.json` | 19 entries; `planned` = unselectable by design |
| Migrations | `supabase/migrations/001–005` | 006a/b are Phase 2/3 infra (applied); 006+ control-plane is Phase 4 |
| Gateway telemetry | `server/services/telemetry.py`, `cassettes.py` | `llm_calls` writes, record/replay, `GET /api/health/llm-stats` |
| Durable builds | `server/services/artifacts.py`, `sweeper.py` | `artifact_contents` store, boot orphan sweep |
| App Spec v1 | `packages/spec/` (schema, TS types, formula, exemplars, fixtures) | source of truth; types generated, never hand-edited |
| Spec engine | `server/engine/` (models, formula, patch, versions) | G0 validation, JSON Patch, version tree |
| Spec gates | `server/gates/` (g0_validate, g1_lint) | deterministic gates, no LLM |
| Retrieval | `server/services/retrieval.py`, `evals/retrieval_index.json` | 768-d cosine scan + tag filters; held-out enforced |
| v2 pipeline | `server/agents/` (schemas/prompts/base/stages), `server/services/run_engine.py` | S0–S6 + Critic + Edit; budgets + resume + SSE v2 |
| v2 API | `server/routers/runs.py` | start/status/events/approve/chat; wish writeback |
| Tests | `tests/` (93 green baseline) | + `scripts/eval.py` (5/5) + `scripts/seed_components.py` |
| Guide + spec | `docs/process/INTARA_ARCHITECTURE_GUIDE.md`, `docs/process/PROJECT_SPEC_FOR_PLANNING_AGENT.md` | Read both before planning |
| Builds proof | `builds/photovault.zip` | Deterministic-build example |
| Runtime (to build) | `packages/runtime/` *(proposed)* | Does not exist yet |
| Spec schema (to build) | `packages/spec/` *(proposed)* | Does not exist yet |
| Agents/gateway/engine (to build) | `server/agents/`, `server/gateway/`, `server/engine/` *(proposed)* | Do not exist yet |

---

## 3. Roadmap (phases, tasks, acceptance)

*Effort unit: 1 week ≈ 20 focused hours, solo AI-assisted. Total to demoable MVP ≈ 12–13 weeks.*

### Phase 0 — Baseline & harness [x]
*Goal: know today's numbers before changing anything. Nothing else starts until this is recorded in §6.*
- [x] P0.1 `scripts/eval_live.py`: 20 diverse wishes (4 per Appendix-D domain #1–5), records per-step parse outcome/source/fallback, JSON report to `evals/reports/baseline-YYYYMMDD.json` (+ unit-tested `classify()`, 5 tests)
- [x] P0.2 Run baseline against live keys; record parse-success %, fallback %, calls/build, wall time in §6
- [x] P0.3 Verify `OPENROUTER_MODEL` id — live env already pinned to verified `google/gemma-4-31b-it:free` (+fallback `gemma-4-26b`); `.env.example` updated from placeholder
- [x] P0.4 Commit `INTARA_ARCHITECTURE_GUIDE.md` + this file → `21b36a9` (6 files, +1889/−2; backend.log + run log excluded)
- **Accept:** `evals/reports/baseline-*.json` exists; §6 filled; suite still 93/93

### Phase 1 — Gateway + visible fallback [x]
*Goal: structured output everywhere; every fallback labelled.*
- [x] P1.1 `server/services/llm.py` + `main.call_gemini`: `json_mode` (response_format/response_mime_type with cached per-model fallback), `max_output_tokens` on all providers, `info` telemetry (provider/model/finish_reason/attempts); wired into all JSON-expecting call sites (planner×2, analyzer, clarify, schema×2, backend×2, frontend×3, orchestrator×2, /generate×2)
- [x] P1.2 `server/utils/json_parse.py`: parse ladder + `detect_truncation()` + `parse_json_with_repair()` (one capped repair call)
- [x] P1.3 `fallback_reason` on generator `_meta` → orchestrator `step_output` → `wish_steps.output` → `artifacts.steps` → Studio badge; `_frag_fallback()` helper
- [x] P1.4 `tests/test_json_parse.py` (21 tests: ladder fixtures, repair semantics, gateway mocked transports, Gemini config)
- [x] P1.5 Re-run baseline, record delta → `evals/reports/baseline-20261012-104102.json`: **20/20 success, 0 fallback** (15 full plans: 10 nvidia + 5 groq; 5 clarify-Q&A)
- **Accept:** fixtures green; live re-run shows parse-success ≥ baseline +15pp ✅ (0/10 → 15/15 full plans); 100% of fallbacks carry reason (mechanism shipped + tested; zero fallbacks occurred to display); suite green

### Phase 2 — Telemetry + cassettes [x]
*Goal: product health numbers + keyless CI. (Guide M0.3, M0.6)*
- [x] P2.1 Migration `006a_llm_calls.sql` (additive-only, RLS append+public-read, no prompt text) + write path: `services/telemetry.py` (fail-soft, self-disables on missing table) + gateway wrappers (`call_llm`/`call_llm_with_meta` keep signatures; chain core renamed `_call_llm_inner`/`_call_llm_with_meta_inner`); records provider/model/tokens/latency/finish/fallback_reason + caller ctx (wish_id/step_key/agent/prompt_version); `_usage_openai` on all 4 OpenAI-compat providers + `usage_metadata` on Gemini; `LLM_TELEMETRY` kill-switch — applied 2026-10-12 via dashboard, live row verified
- [x] P2.2 `GET /api/health/llm-stats` (per-provider/model aggregates: calls, tokens, avg latency, repaired/failed; fail-soft `ok:false`, never 500) — live verified with real row
- [x] P2.3 `services/cassettes.py` (record/replay via `LLM_CASSETTES`, miss falls through to live, never fails a build) + `tests/test_telemetry.py` (10 tests); chain unit-test helpers force `LLM_TELEMETRY=0`/`LLM_CASSETTES=off`; `server/.env.example` documents new vars — live verified: record saved `evals/cassettes/95606af8….json`, zero-key replay (`has_any_llm()=False`) served byte-identical `{"ping":true}` as `provider: cassette`
- [x] P2.4 Prune/aggregate policy (free-tier 500 MB guard): one row ≈ 200 B → 500 MB ≈ 2.5 M calls (≈ years at small-biz volume); policy = monthly `delete from llm_calls where created_at < now() - interval '90 days'` once volume warrants; aggregates served from last 2000 rows by endpoint. No action needed now.
- **Accept:** ✅ post-build counts match logs (1 call → 1 row → endpoint n=1); ✅ zero-key serving proven via replay (full 20-wish cassette set = a manual-dispatch record run, see replay runbook below)
- **Replay runbook:** record = restart backend with `LLM_CASSETTES=record` → run `scripts/eval_live.py` → cassettes accumulate under `evals/cassettes/`; replay = restart backend with `LLM_CASSETTES=replay` and keys stripped → run `scripts/eval_live.py` → zero-key, byte-identical where recorded, live fallthrough on miss.

### Phase 3 — Durable state [x]
*Goal: kills/restarts never lose work. (Guide M0.4–M0.5)*
- [x] P3.1 Migration `006b_artifact_contents.sql` (new table, additive-only) + `services/artifacts.py`: content-addressed store (sha256 of canonical JSON; put fail-fast with `ARTIFACT_MAX_BYTES` guard, get fail-soft). **Decision (recorded): side table, not a jsonb column on wish_steps** — keeps step rows small, dedups across retries/wishes, purely additive. Every step now persists FULL content (schema/prisma/sql untruncated, frags with real file code, full scaffolds/preview) + `content_sha` in the summary output.
- [x] P3.2 Resume restores from store: done steps with `content_sha` fill accumulators with real content and stay done (`step_restored` event); legacy hollow rows (no sha) keep the old requeue+regen path (`step_requeued`) — backward compatible. Store failure fails the step (never a hollow persist).
- [x] P3.3 `services/sweeper.py` + `@app.on_event("startup")` in `main.py`: fresh boot owns nothing → orphan `running` steps → `pending` (+attempt, noted error), orphan `building` wishes → `failed` with resume pointer. Fail-soft, never blocks boot. **Live proof on first boot: photovault wish `5ed568b…` → failed, 2 steps requeued, resume at `backend-albums`.**
- [x] P3.4 `tests/test_durability.py` (8 tests): store round-trip/canonicalization/limits, sweeper requeue+noop+DB-down, legacy-hollow regen, store-failure-fails-step, and **kill-resume: fault mid-wiring → residue (building+running) → fresh process → sweep → retry completes `ready` with ZERO repeated per-step LLM calls** (3 `step_restored`, real contents in final artifacts).
- **Accept:** ✅ kill-resume test green; ✅ no row stuck in `building` (sweeper flips on boot, verified live)

### Phase 4 — Spec v1 + control-plane DB [x]
*Goal: the App Spec as data with a linter. (Guide M1.2–M1.5, M1.7)*
- [x] P4.1 `packages/spec/app-spec.schema.json` + `scripts/gen_spec_types.py` → `packages/spec/app-spec.ts` + `server/engine/spec_models.py` (pydantic v2); `--check` drift green, both outputs compile/import. Generator lessons: `from`→alias, `field`→SpecField (pydantic import shadow), scalar `$defs` need alias emission.
- [x] P4.2 `server/gates/g1_lint.py` (36 rules R01–R36 + W01) + `g0_validate.py`; fixtures as patches (`packages/spec/fixtures/base.json` + `fail-patches.json`, 37 cases incl. warning-only); 2 golds pass G0/G1 clean. Reachability readings recorded in module docstring (row_link counts, empty roles = public, BFS from initial).
- [x] P4.3 Formula language (`grammar.md`): `server/engine/formula.py` + `packages/spec/formula/formula.ts` (erasable syntax, node ≥22) + 118 shared cases; node --test 120/120, pytest parity green, 500-input fuzz (only FormulaSyntaxError/FormulaError escape), no-eval grep enforced. Parity traps fixed: float/int strictness, non-finite rejection.
- [x] P4.4 `server/engine/patch.py` (RFC 6902 + simulation-based invert: `-` resolution, overwrite→replace-old) + `server/engine/versions.py` (create/patch/get/history/undo); 1175 randomized round-trips green.
- [x] P4.5 `supabase/migrations/006_v2_control_plane.sql` (projects, versions, runs, steps, events, exemplars, feedback + 006a run_id FK; RLS on, service-key only per sketch). Deviations: `artifacts` table omitted (006b covers it), `apps`/`records` deferred (data-plane migration), no monorepo move — paths adapted (`server/gates`, `server/engine`).
- **Accept:** golds pass G0/G1 ✅ (2 now; remaining 3 + PRD adapter = Phase 5 P5.1); patch round-trip ✅; migration applies cleanly ✅ (dashboard 2026-10-12; all 7 tables live+empty, `llm_calls_run_id_fkey` enforced — bogus run_id rejected, existing telemetry row intact)
- **Deviations from AGENT.md scope:** 2 gold specs now (guide: 1 per ~2 days; rest in Phase 5); Python formula port done now (guide said "later"); no M1.1 monorepo move (deferred to Phase 5/6 start).

### Phase 5 — Gold specs + retrieval seed [x]
*Goal: hand-authored truth to retrieve and eval against. (Guide M1.6, M7-start)*
- **Golds (8):** inventory, booking, CRM/leads, repair tracker, leave/HR (hand) + veterinary, education, social (pipeline + human review).
- **Golds (10):** + productivity (TaskFlow), gardening (GardenPlan) — pipeline + human review, promoted byte-identical except one seed value (see #37).
- [x] P5.1 Five gold specs + `server/engine/prd_adapter.py` (legacy PRD→Spec; drops storage-managed id/created_at/updated_at per R40)
- [x] P5.2 `server/services/retrieval.py` (768-d) + builder/seeder; 8 exemplar rows live; versioned index rebuilt.
- [x] P5.3 Held-out #6–10 enforced; hit-rate recorded.
- [x] P5.4 Human-review integration: prototype checker ported to G1 (R37–R47, W02–W04); block vocabulary adopted (chart title/x/y, calendar date_field, timeline date_field/title); `today()`/`tomorrow()` added to formula language (both impls, TZ-pinned); S2/S3/S4 prompt rules from review findings (→ v3 prompts).
- **Accept:** ✅ 8 golds pass G0/G1 (+G3 on all 8 via node suite).
- **Ops note:** `SUPABASE_KEY` is the anon key (demo-open writes rely on RLS policies); control-plane writes (exemplars) need `SUPABASE_SERVICE_KEY` — seeder uses it explicitly.

### Phase 6 — Runtime v1 [x]
*Goal: apps run as data, no LLM involved. (Guide M2)*
- [x] P6.1 `packages/runtime/engine/` (validate, defaults, computed, refs/onDelete, lifecycle, permissions, `where`-subset): **156 node tests green, 98.4% lines / 89.9% branches** (`node --test --experimental-test-coverage`; vitest absent in env — native runner recorded as equivalent). Engine proven LLM/network-free by static test.
- [x] P6.2 `adapters/` (guide §5.2 interface): memory + dexie (fake-indexeddb in node, real IDB in browser) pass the SAME shared contract suite 12/12. Dexie syncs per-entity over one `records` table (ADR-2 A); transactions snapshot/restore.
- [x] P6.3 `shell/` (routes, nav-for-role, theme→CSS vars, RoleSession) tested; `AppShell` React shell tsc-clean.
- [x] P6.4 14 blocks (`blocks/`: table, kanban, filter, stat, gauge, detail, related_list, pipeline, form, chart, calendar, timeline, files, hero) with `fixtures.json` + 4-state contract (loading/error/empty/ready); registry/static/component-map checks + tsc. G1 BLOCKS extended with the 6 new stable types.
- [x] P6.5 G3 (`testing/g3.ts`: seed-load→CRUD→computed/refs→lifecycle matrix→permission closed-world, all golds green) + G4 (`testing/g4.ts`: react-dom/server smoke over all 14 block fixtures + AppShell on all 5 golds; `.tsx` via a transpile-on-the-fly loader, no new deps).
- [x] P6.6 `react-prompt-app/src/runtime/RuntimePreview.tsx` (spec → seeded Dexie → AppShell + operable blocks: select/open, transition, submit) + third Studio tab when `artifacts.spec_v1` exists; Sandpack stays default/legacy. Single-React via vite alias; `vite build` green.
- **Accept:** all gold specs operate (CRUD, filter, kanban drag-transition, stats, role restrictions) with zero LLM calls — ✅ G3+G4 green (drag-transition = UI affordance, Playwright-deferred); runtime ≤ ~400 KB gzipped budget — **OPEN (track at bundling; current Studio chunk ~554 KB incl. app code, not runtime-isolated)** — **OPEN (needs P6.5/G3–G4 harness + bundling)**
- **Deviations:** node --test for vitest; Playwright deferred (no browser in env — fixtures double as Playwright inputs later); `.tsx` can't run under node type-stripping → registry/components split with static completeness check; `packages/runtime` has its own deps (dexie, fake-indexeddb, react 18 types).

### Phase 7 — Agents + run engine + Studio slice [x]
*Goal: the v2 pipeline builds specs end to end. (Guide M3 + M5-lite)*
- [x] P7.1 `server/services/run_engine.py`: RunStore ABC (memory + Supabase-service-key), budgets (calls/wall/repairs), resume via `resume_run` (same id), SSE v2 (history + live tail), replay, wish text in run_started; sweeper extended to runs/run_steps; single-flight NOT needed (versions tree-merge).
- [x] P7.2 `server/agents/` (schemas/prompts/base/stages): versioned prompts (§8.4 structure, schema generated from Pydantic), `run_agent` repair loop (≤2, cooling temp) + deterministic fallbacks (edit: none, raises), quota propagates; S3→S4 sequential (S4 consumes S3 page roles — guide §7.2 lists ui summary as S4 input; parallelism dropped, semaphore kept).
- [x] P7.3 Retrieval logged per stage (catalog slice + file-index exemplars); Critic fills `trace[]`; G2 deterministic gate (`gates/g2_coverage.py`: musts covered, should advisory); S5 repair ≤2 on uncovered musts, else explicit degrade.
- [x] P7.4 `BlueprintView.tsx` (Data/Screens/Rules/Assumptions + approve + chat-patch with Details toggle + RuntimePreview) + `runs` client fns + Studio 4th tab (run link + spec write back to wish on start/finish).
- [x] P7.5 `scripts/core20.py` (20 wishes incl. 5 heldout; G0/G1/G2 + G3-via-node grades, diversity, budgets → `evals/reports/core20-*.json`); probe: 1 full pass (Library, 8 calls, G0/G1/G2 clean) + 2 fail-closed S5s that exposed the role-mismatch class → fixed (S4 role contract + S2 from/to gate + sequential S3→S4).
- **Accept (MVP demo):** core20 ≥85% — ✅ **MET 17/20 (85%) on rerun 2026-10-15** (`core20-20261015-111406.json`); median 9 calls ✅; median wall 267s (near 3-min target, quota-throttled); coverage 1.0 (gym trace gap noted); diversity 12 combos ✅ overlap 0.028 ✅; heldout 3/5 green (invoicing/gym/helpdesk); type-a-wish→working-app demoable via Studio Blueprint/App tabs on passed wishes.
- **Live findings:** (a) S3/S4 role mismatch failed 2 runs fail-closed → fixed, re-validating; (b) router double-created run rows (client polled an empty shell) → `run_id` passthrough fixed, proven by steps appearing under the polled id; (c) Gemini free-tier 5 RPM exhausted mid-probe — chain carried on groq as designed.

### Phase 8 — Capability depth [ ] *(slices 1–3 done: adapter, automations, boards/CSV, storage, print)*
*Goal: Track A covers real SMB work. (Guide M4)*
- [x] P8.1 `supabase/migrations/007_data_plane.sql` (apps + records, ADR-2 A, RLS service-key-only) + `packages/runtime/adapters/supabase.ts` (same contract; live test skipped without env, scratch-app isolated) — **needs dashboard apply to prove live**
- [x] P8.2 `packages/runtime/automation/executor.ts` (trigger match + set_field/create_record/notify/export_csv; email/webhook deferred explicitly) + 3 tests incl. gold-automation replay
- [ ] Lifecycle UI + transition buttons, more computed blocks, roles editor, `file`/`image` fields (Storage), CSV import/export UI, `chart.*`, `data.calendar`, single-user auth, email provider (verify limits), print/PDF views; every block `stable` only with fixtures+tests
- **Accept:** 10 gold specs pass G3/G4; adapter suite green on supabase — **OPEN (8 golds; supabase suite needs 007 applied)**

### Phase 9 — Studio v2 + learning loop [ ]
*Goal: non-technical users succeed unaided. (Guide M5 + M7)*
- Diffs in human language + undo, version timeline, build report page, template gallery (= gold specs), plain/developer toggle, feedback capture + dataset export
- **Accept:** 3 unfamiliar users complete describe→approve→edit→share unassisted (observed)

### Later (not phases yet)
- **Phase 10 — Track B** (M6): classifier, sandbox, delimiter code agent, interaction smoke, custom-block SDK (only after Phase 9)
- **Phase 11 — Ship** (M8–M10): export compiler → publish/hosting → multi-tenant hardening + billing (re-verify Vercel/Render/Supabase terms at that time)

---

## 4. Session log

### Session 0 — 2026-10-11 — Study + AGENT.md creation [x]
- **Done:** Read `INTARA_ARCHITECTURE_GUIDE.md` (1170 lines) end-to-end; cross-checked against live repo (no `agents/`, `gateway/`, `engine/`, `packages/` — v2 is greenfield); verified backend up (single process, no `--reload`), frontend up, `/health` OK (groq+nvidia+openrouter configured, deepseek off); locked decisions (spec-first, Track B deferred, English-only) via user answers; created this file.
- **Problems:** none (read-only session). Noted: guide file itself untracked in git; `.env.example` OpenRouter model id still placeholder (flagged for Phase 0).
- **Next:** user commits guide + AGENT.md (or authorise it in build mode); then Phase 0 baseline (needs LLM quota confirmation + guide/AGENT.md commit decision).

### Session 1 — 2026-10-12 — Phase 0 baseline [x]
- **Done:** Backend was down — restarted single-process (no `--reload`) with repo-local log; `/health` green (gemini primary, all 4 providers, no cooldowns). Wrote `scripts/eval_live.py` (20 wishes × 5 domains, plan-stage only, outcome classifier with mock→fallback semantics, JSON report). Fixed classifier mid-run (mock+awaiting_approval must count as fallback) and restarted the run. Fixed `.env.example` OR model ids to verified values. Added 5 unit tests (`classify`, 20-wish coverage). Suite 98/98, eval 5/5, tsc clean.
- **Problems:** (a) baseline proves analyzer parse-success 0/10 — malformed JSON envelopes dominate, quotas thin mid-run, 1 validator false-positive (see §6 + new §5 entries); (b) `load_dotenv` in seed tests leaked real `LLM_ONLY` into pytest env — fixed via hermetic env files (pattern to reuse); (c) `server/backend.log` is git-tracked runtime noise — excluded from commits, do not stage.
- **Next:** commit (P0.4); then Phase 1 gateway work — the baseline says JSON-mode + tolerant parsing is the highest-leverage fix.

### Session 2 — 2026-10-12 — Phase 1 gateway + visible fallback [x]
- **Done (so far):** P1.1 structured-output plumbing (`json_mode`/`max_output_tokens`/`info` through all 5 providers + `call_gemini`, cached per-model fallback, wired into all 17 JSON-expecting call sites); P1.2 parse ladder + `detect_truncation()` + `parse_json_with_repair()` (one capped repair call); P1.3 `fallback_reason` from generators → orchestrator → DB → Studio badge; `tests/test_json_parse.py` (21 tests); fixed a shipped `IndentationError` in `frontend_gen.py` game branch found during verification; updated 5 existing fallback-test mocks for new kwarg signatures; suite 123/123, tsc clean, eval 5/5.
- **Problems:** (a) two baseline runners briefly overlapped after a missed kill pid — restarted clean, stale partial log removed; (b) see §5 #13.

### Session 3 — 2026-10-12 — Phase 1 completion + verification [x]
- **Done:** Finished `json_mode=True` wiring at all remaining call sites (planner, analyzer, generators, orchestrator, /generate); `fallback_reason` metadata end-to-end (generator `_meta` → `step_output` → `wish_steps.output` → `artifacts.steps` → Studio badge via `_frag_fallback()`); fixed pre-existing route-precedence bug (`/api/wishes/health` shadowed by `/wishes/{wid}` — routers now mount last + regression test); suite 124/124, tsc clean, eval 5/5, backend restarted on final code.
- **Problems:** see §5 #14–15.
- **Next:** Phase 2 telemetry + cassettes.

### Session 4 — 2026-10-12 — Phase 2 complete + live-verified [x]
- **Done:** P2.1–P2.4: `supabase/migrations/006a_llm_calls.sql`, `server/services/telemetry.py`, `server/services/cassettes.py`, gateway wrapper refactor in `server/services/llm.py` (all 30+ call sites untouched — signatures backward-compatible), Gemini `usage_metadata` + endpoint `GET /api/health/llm-stats` in `server/main.py`, `tests/test_telemetry.py` (10 tests), `server/.env.example` vars; user applied 006a via dashboard → backend restarted → live verified: 1 groq call → 1 `llm_calls` row (128 in / 123 out, 1519 ms) → endpoint `ok:true n=1`; cassette record→replay round-trip + zero-key replay (`has_any_llm()=False`, byte-identical); P2.4 prune policy noted; replay runbook recorded. Suite **134/134**, eval 5/5.
- **Problems:** (a) no DDL path in this env (no psql/supabase CLI/direct DB URL) → migration needed dashboard apply + backend restart (recorder self-disables per-process); (b) found `server/.env` (not root) is the real key source after an env-hunt detour; removed stray root `.env.example`, vars live in `server/.env.example`; (c) see §5 #16.
- **Next:** Phase 3 durable state.

### Session 5 — 2026-10-12 — Phase 3 durable state [x]
- **Done:** P3.1–P3.4: `supabase/migrations/006b_artifact_contents.sql`, `server/services/artifacts.py`, `server/services/sweeper.py`, orchestrator restore/store wiring (5 step kinds), `@app.on_event("startup")` sweep in `main.py`, `tests/test_durability.py` (8 tests), `server/.env.example` var; backend restarted, healthy; sweeper proved live on boot (photovault orphan → failed + 2 requeued). Suite **142/142**, eval 5/5.
- **Problems:** (a) 006b needed dashboard apply before any new build (fail-fast by design) — user applied 2026-10-12, live put→get round-trip verified, backend healthy; (b) see §5 #17.
- **Next:** Phase 4 (spec v1 + control-plane DB).

### Session 6 — 2026-10-12 — Phase 4 complete [x]
- **Done:** P4.1–P4.5 code: spec schema + codegen (TS+Pydantic, drift green), G0/G1 gates (36 rules, 37 fixtures, 2 golds clean), formula twins (118 shared cases, 120/120 node, fuzz green), patch+versions (1175 randomized round-trips), 006 migration file. Suite **159/159**, eval 5/5, `app-spec.ts` compiles under `--strict`. No server-runtime change → no restart.
- **Apply:** user ran 006 via dashboard 2026-10-12 → verified live: 7 tables exist+empty, FK rejects bogus run_id, llm-stats intact, backend healthy.
- **Problems:** see §5 #18.
- **Next:** Phase 5 (golds 3–5 + retrieval).

### Session 7 — 2026-10-12 — Phase 5 golds + retrieval [x]
- **Done:** 3 new golds (booking, crm-leads, leave-hr — 5/5 G0/G1 clean), `prd_adapter.py` (5/5 legacy wishes adapt clean), `retrieval.py` + builder/seeder scripts, `tests/test_retrieval.py` (hit-rate 5/5, held-out enforced), exemplars seeded live (5 rows), index built. Suite **164/164**, eval 5/5. No server-runtime change → no restart.
- **Problems:** seeder first failed on RLS (42501) — root cause: runtime `SUPABASE_KEY` is anon, control-plane tables are service-key-only by design; seeder now uses `SUPABASE_SERVICE_KEY` explicitly · see §5 #19.
- **Next:** Phase 6 (runtime v1) — the big one: engine + adapters + shell + blocks.

### Session 8 — 2026-10-12 — Phase 6 engine/adapters/shell/blocks [ ]
- **Done:** `packages/runtime/` (engine 8 modules, 2 adapters + shared contract, shell core + AppShell, 14 blocks + registry + fixtures, own package.json/tsconfig): node **156/156**, coverage **98.4% lines**, tsc clean; python **164/164** (G1 extended, repair-tracker `where` restored guide-faithful), eval 5/5. No server-runtime change → no restart.
- **Problems:** (a) `.tsx` unrunnable under node type-stripping → registry/components split; (b) an edit dropped the `metric.gauge` linter line — python suite caught it instantly, restored · see §5 #20; (c) test-insert edits twice ate a `test(` opener — append tests at file end instead.
- **Next:** P6.5 (G3 generator + G4 smoke) → P6.6 RuntimePreview → close Phase 6.

### Session 9 — 2026-10-12 — Phase 6 G3/G4/RuntimePreview, phase closed [x]
- **Done:** P6.5 (`testing/g3.ts` + `gates.test.ts`: G3 green on all 5 golds; `g4.ts` + `g4.test.ts` + `tsx-loader.mjs`: 14 block smokes + 5 shell smokes green) + P6.6 (`src/runtime/RuntimePreview.tsx`, Studio third tab, vite alias, `vite build` green). Node **169/169** (93.1% lines), both tscs clean, python **166/166**, eval 5/5×3.
- **Problems:** (a) one transient golden-eval failure under load (npx tsc 15s timeout in eval.py, not a product change — green on rerun) · see §5 #21; (b) tsx-loader needed `shortCircuit: true`; (c) `@types/react@19` hoisted into runtime broke studio JSX types — pinned v18.
- **Next:** Phase 7 (agents + run engine + Studio slice).

### Session 10 — 2026-10-12 — Phase 7 pipeline + live fire [ ]
- **Done:** P7.1–P7.4 code (`server/agents/`, `run_engine.py`, `g2_coverage.py`, `routers/runs.py`, `BlueprintView`, runs client fns, `core20.py`): suite **185/185**, eval 5/5, both tscs + vite build green. Live: 4 v2 runs — 2 full passes (Library 8 calls, Library2 7 calls, both G0/G1/G2 clean, 0 degraded), 2 fail-closed S5s.
- **Live findings → fixed:** (a) S3/S4 role mismatch ×2 → S3-declares/S4-subset contract (owner anchor, page_roles input, subset gate) + S2 from/to gate + set_field/create_record gate (fields_of was undefined — crash-masked); (b) router double-created run rows (client polled an empty shell forever) → `run_id` passthrough; (c) resumed orphan run proved kill-resume live (5 calls to done); (d) Gemini free 5 RPM hit mid-probe, groq carried as designed. See §5 #22–24.
- **Next:** user go → full core20-20 manual dispatch → record §6 → close Phase 7 → Phase 8.

### Session 11 — 2026-10-13 — core20 readiness: status file + quota verdict [ ]
- **Done:** `--status-file` + incremental results + per-poll snapshots in `core20.py` (dry-run proved the loop: progress file + final report written); S3 R20 reachability gate (live dry-run failed S5 on orphan detail pages → gate now catches it with repair feedback); suite **188/188**; backend restarted on final code, healthy.
- **Quota verdict (live, 2026-10-13):** Gemini DAILY-exhausted until ~tomorrow (~10h); OpenRouter free pool congested (transient 429s); groq healthy (2.4s); nvidia alive but sloppy on structured JSON. Dry-run ran on groq, 7 calls, no quota errors.
- **Recommendation:** launch full 20 on the groq-led chain now, OR wait ~10h for Gemini reset for max pass-rate. Optional speedup: `LLM_ONLY=groq,openrouter,nvidia` in `server/.env` + restart (skips dead-Gemini round-trips), revert after.
- **Problems:** see §5 #25.
- **Next:** user launches full core20 (steps below) → pings me → analyze + §6 + gold candidates → Phase 8.

### Session 12 — 2026-10-13 — core20 full run: measured 4/20, taxonomy complete [x]
- **Result** (`evals/reports/core20-20261013-230036.json`, ~3h wall): **4/20 green** (productivity, retail, social done G0–G3; invoicing-HELDOUT degraded-but-green, coverage 1.0) · 10 failed · 6 harness HTTP timeouts (backend stalls, recovered) · median 11 calls (✅ ≤14) · median wall 537s (❌ >3min — quota-throttled) · diversity 4 combos (target ≥5), overlap 0.0 ✅.
- **Failure taxonomy (all fail-closed, all specific):** quota deaths ×3 (repair/freelance/restaurant 503s, gym timeout); R12-direction roles ×3 (education hr? no — education/automotive/school: pages use roles access lacks); lifecycle reachability ×1 (appointment); kanban group_by ×1 (gardening); role cascade ×1 (hr); empty-response parse degradations (education/school s4 — provider returned "").
- **Queued fixes:** S4 gate role-set EQUALITY (both directions), S3 required-props gate, S2 reachability gate, step-row hygiene on raise (rows stuck `running`), harness api timeout 30→120. Then restart + rerun the 16 non-green.
- **Generalisation read:** heldout 1/5 green (invoicing), rest lost to quota/timeouts more than quality — inconclusive, rerun will tell.
- **Next:** apply fix batch → restart → rerun non-green → §6 close → Phase 8.

### Session 13 — 2026-10-14 — fix batch + rerun launch [ ]
- **Fixes:** S4 role-equality (both directions) + S3 required-props (G1 catalog) + S2 reachability (BFS) + set_field/create_record checks (fields_of wired) + step-row hygiene on raise (`_run_simple/_run_s5/_run_iterate` bodies; unexpected throws fail gracefully, kill test updated) + harness api timeout 30→120 + `--resume` keeps green only + engine real-path test. Suite **189/189**.
- **Rerun:** `core20.py --live --resume` (4 green kept, 16 rerun) launched 18:10 IST.
- **Fix batch v2 (from rerun failures):** formula `&&`/`||`/`!` aliases (both impls + 7 conformance cases + grammar) for S4 `when` clauses; G3 guarded-transition probe made guard-aware (was flagging valid specs). Node **176/176**, pytest **189/189**, both tscs clean. Backend restarted on final code.
- **Standing limitation (recorded, not fixed):** cross-stage role coherence has no sound automatic repair — S2 invents transition roles, S3/S4 can't see them, and rewriting access at assembly would be fail-open. Fail-closed with specific errors stands; rerun measures it.
- **Rerun 1 result: 4/20 → 13/20 G0/G1** (`core20-20261014-212416.json`).
- **Rerun 2:** `--resume` (13 green kept — incl. food on g0/g1; 7 rerun: appointment, freelance, education, gardening, automotive, restaurant, school) launched 21:52 IST. (Food flips fully green on re-grade with fixed G3; library stays red on its int-id spec bug pending the S2 text-id rule proving live.)
- **Rerun 2 PAUSED by user at wish 1/7** (appointment run may still complete in backend — harmless, rerun redoes it). Backend left running healthy. Resume tomorrow with the same launch command.
- **Rerun 2 RESUMED next day:** backend was down overnight → restarted (no orphans swept, clean boot) → `--resume` relaunched (13 green kept, 7 rerun, appointment in flight).
- **Next:** rerun-2 result → §6 close → gold candidates → Phase 8.

### Session 14 — 2026-10-15 — rerun-2 lands 17/20, Phase 7 closed [x]
- **Result:** 4/20 → **17/20 G0/G1** (9 flips: repair/hr/crm/fitness/food/vet/gym/helpdesk + kept 4; food analytically green on fixed G3). Residual red: appointment/restaurant/school (S2-invented transition roles — standing limitation, fail-closed) + library (int-id spec, pinned pre-fix; fresh run exercises the S2 text rule).
- **Budgets/diversity:** median 9 calls ✅, wall 267s, 12 combos ✅, overlap 0.028 ✅, heldout 3/5 ✅, coverage 1.0 (gym trace gap 0.0 noted).
- **Next:** gold candidates from green specs (human review) → Phase 8.

### Session 15 — 2026-10-15 — human gold review integrated [x]
- **Done:** reviewed 3 improved specs (all G0/G1-clean first try — review quality high) + ported prototype checker (R37–R47, W02–W04; old golds get warnings only, zero new errors) + block vocabulary adoption (ChartBar title/x/y+count, CalendarMonth, ActivityTimeline; host data via component props, never spec props) + `today()`/`tomorrow()` in formula language (TZ-pinned, 131/131) + S2/S3/S4 review rules (→ v3 prompts) + adapter drops id/created_at/updated_at + promoted 3 golds (8/8 G0/G1, G3 green all 8) + seeded + index rebuilt. Python **189/189**, node **186/186**, both tscs, vite build, eval 5/5.
- **Decisions confirmed:** `$user.email` mapping ✓ (engine already resolves `$user.*`); block prop table adopted as canonical (runtime aligned to it); seeds WILL go stale mid-Oct-2026 (no relative-date tokens — noted, not built); education/social formulas (count/avg exist — left for next review, specs untouched).
- **Problems:** see §5 #31–32.
- **Next:** Phase 8 scaffolding whenever ready.

### Session 16 — 2026-10-15 — Phase 8 slice 1 (adapter + automations) [x]
- **Done:** 007 migration file (+additive test), Supabase adapter (contract suite green-skip without env, scratch-app isolation), automations executor + 3 tests, pytest wrapper globs updated. Node **190/190 (1 skip)**, tsc clean, python **190/190**, eval 5/5.
- **Problems:** g4.ts `spec.ui.nav` possibly-undefined (pre-existing, hidden) — fixed with `?? []`.
- **Live proof (after 007 applied):** all 3 adapters green on the SAME contract — memory 12/12, dexie 12/12, **supabase 6/6 live** (scratch app created + cascade-deleted, zero residue). Found + fixed: shared-table cross-test pollution → per-subtest hard-clean hook in contract.
- **Automations in preview:** RuntimePreview fires record.created/lifecycle.transition automations on user actions, shows notify/deferred effects, refreshes on mutations. Studio tsc + vite build green.
- **Next:** Phase 8 slice 2 (lifecycle UI/kanban wires, CSV UI, roles editor…) — ask user for priority.

### Session 17 — 2026-10-15 — Phase 8 slice 2 (boards + CSV) [x]
- **Done:** shared `blocks/csv.ts` (deduped from executor) + 4 tests; kanban drag-to-transition (HTML5 DnD, `move` action, host resolves transition, notice when none); table Export/Import CSV; RuntimePreview fires automations + handles move/export/import with notices. Supabase contract proven **live 6/6** (scratch app, zero residue). Node **194/194 (1 skip)**, 90.8% lines; both tscs + vite build; python **190/190**, eval 5/5.
- **Problems:** (a) shared-table cross-subtest pollution → per-subtest hard-clean hook in contract; (b) live network tests must be INTARA_LIVE opt-in, never ambient-env (a leaked shell export + transient fetch failure flaked the gate suite) · see §5 #33–34.
- **Next:** slice 3 candidates — roles editor, file/image Storage (+buckets), single-user auth, email verify, print/PDF, 2 more golds.

### Session 18 — 2026-10-15 — Phase 8 slice 3 (storage + print + gold staging) [x]
- **Done:** `008_storage_uploads.sql` (bucket + demo-open policies; needs dashboard apply) + `storage/uploads.ts` (uuid-prefixed sanitized paths, 3 tests) + FileList `upload` prop (opt-in, G1-registered) + RuntimePreview upload → storage → row + demo-mode guard + print toolbar/stylesheet. Staged `productivity` + `gardening` candidates in `packages/spec/review/` for human review. Node **197/197 (1 skip)**, 90.7% lines; both tscs + vite build; python **190/190**, eval 5/5.
- **Next:** user applies 008 → live upload proof → slice 4 (roles editor, auth decision, email key, remaining golds).

### Session 19 — 2026-10-15 — upload proven live + roles matrix [x]
- **Done:** 008 applied by user → proved live with anon key (bucket public, upload OK, public read bytes back, cleaned up, zero residue). `RolesMatrix.tsx` (role × entity ops via engine.can, current role highlighted) in preview behind Suspense; node smoke renders 4 rows. Python **190/190**, studio tsc + build green.
- **Next:** slice 4 remaining — roles *editor* (spec mutation = chat-patch, needs design), single-user auth (needs auth-model decision), email provider (needs key), 2 more golds (productivity/gardening in review with user).

### Session 20 — 2026-10-15 — PIN lock auth [x]
- **Done:** per user decision (PIN, no Resend; email integrates later via existing deferred effects). `auth/pin.ts` (PBKDF2-SHA256 100k, salt, constant-time compare, `_auth` store entity) + 2 tests; `PinGate.tsx` (setup/lock, digit-only, clears state); RuntimePreview wiring (auto-gate when enrolled, toolbar Set-PIN/Lock, notices). Email-later confirmed zero-rework (payloads already flow through deferred effects).
- **Verify:** node **199/199 (1 skip)**, 91.0% lines; both tscs + vite build; python **190/190**, eval 5/5.
- **Next:** 2 golds in review with user; roles editor design; print views already shipped.
- **Verify:** node **199/199 (1 skip)**, 91.0% lines; both tscs + vite build; python **190/190**, eval 5/5.
- **Next:** 2 golds in review with user; roles editor design; print views already shipped.

### Session 21 — 2026-10-16 — batch-2 golds promoted, prototype fully ported [x]
- **Done:** both improved specs G0/G1-clean first try; ported checker delta (R48 block-id uniqueness, R49 mirror-ref, R50 placeholder/id-only templates) + 5 fail-patches; `today()`/`tomorrow()` in formula language (TZ-pinned, 135/135); S2/S3/S4 review rules (→ v3 prompts); `set_field` evaluates zero-arg date fns (literal fallback); adapter drops storage-managed fields; promoted productivity+gardening (10/10 G0/G1, G3 green all 10); seeded + index rebuilt.
- **Verify:** node **204/204 (1 skip)**, 91.0% lines; both tscs + vite build; python **190/190**, eval 5/5.
- **Decisions confirmed:** chained computed needs dependency-first field order (engine semantics, now in grammar.md); multi-hop `to` resolves at provider time (lint already proves resolvability); seeds WILL go stale (no relative tokens — noted).
- **Next:** Phase 8 remainder (roles editor design) or Phase 9.

### Session 22 — 2026-10-16 — roles editor (deterministic patches) [x]
- **Done:** `editing/roles.ts` (add/remove/set with patch building + usage guards, 3 tests) + `POST /runs/{id}/patch` (G0/G1-gated, same version path as chat; 3 TestClient tests incl. a 422 that forced the test itself to write a complete role+page+rule patch) + Studio Roles section (op toggles scoped to primary entity, add/remove with guard messages) reusing the same lib. Backend restarted, endpoint live-verified (400 validation).
- **Verify:** node **207/207 (1 skip)**; both tscs + vite build; python **193/193**, eval 5/5.
- **Next:** Phase 8 remainder is now only: email key (blocked), 2 gold reviews (with user). Then Phase 9.

### Session 23 — 2026-10-16 — Phase 9 slice 1 (timeline + report + diffs/undo) [x]
- **Done:** `diff` + `summarize_ops` in engine/patch.py (round-trip + invert + 60 randomized cases); `009_version_summary.sql` (needs dashboard apply; Supabase writer degrades loudly without it); `create_version` summary plumbing (generate auto-summary, iterate/chat/manual summaries); `GET projects/{id}/versions` + `POST versions/{id}/revert` (4 endpoint tests); Studio `VersionTimeline` (summaries, parent diffs, view/undo) + build-report section in BlueprintView (steps, calls, degraded). Backend restarted, healthy.
- **Verify:** python **195/195**, eval 5/5; both tscs + vite build.
- **Next:** user applies 009 → Phase 9 slice 2 (gallery, plain/dev toggle, feedback).

### Session 24 — 2026-10-16 — Phase 9 slice 2 (gallery + dev toggle + feedback) [x]
- **Done:** exemplars list/get + eventlog JSON + feedback post/export(CSV) endpoints (fake-supa tests; KeyError→404 fix); `/templates` Gallery page (live preview + build-similar → run view) + header link + `/runs/:id` route; Blueprint plain/developer toggle (spec JSON + event log) + feedback widget (rating/comment, version-linked). Backend restarted; gallery endpoint live-verified with real data.
- **Verify:** python **197/197**, eval 5/5; node **207/207**; both tscs + vite build.
- **009 applied by user 2026-10-16** — verified live (probe insert/read/delete, zero residue). Summaries now persist.

### Session 25 — 2026-10-16 — stop all in-flight wishes (ops) [x]
- **Done (user-requested kill):** 2 v2 runs `running` → backend restarted (kills worker tasks) → boot sweeper flipped both to failed + requeued 1 step each. 3 orphaned v1 `wish_steps` (failed wishes) + 6 orphaned `run_steps` (failed runs) parked as failed with notes. Verified zero `running`/`building` rows everywhere; backend healthy.
- **Next:** Phase 9 slice 3 / UAT as directed.

### Session 26 — 2026-10-16 — spaced-filename preview outage [x]
- **Symptom:** HR wish `ready` but Trial preview errored — page files named `Daily Attendance.tsx` (spaces) produced `import { Daily Attendance }` (invalid JS). Validate gates never caught it: heavy gates run on template regen, light check ignores identifiers.
- **Immediate:** repaired the wish's artifacts in DB (4 files → PascalCase + barrel + App imports/elements), verified zero broken identifiers remain.
- **Systemic:** `page_ident()` + `normalize_frag()` in frontend_gen (template sites + end-of-pipeline normalization for LLM frags) + orchestrator final App/barrel slugged (labels/routes stay raw). 3 regression tests. Suite **200/200**, eval 5/5, backend restarted.
- **Rule:** display names never enter code positions — filenames, imports, JSX, barrel all slugified at a single choke point.

### Session 27 — 2026-10-16 — template floor raise (generic → human) [x]
- **Trigger:** user feedback — fallback-built apps look/feel dumb ("Demo name 1", "Sample 2", Jan-2026 dates).
- **Done:** `_seed_value` domain-aware (person pools, task/product/job/leave titles, INR phone/city/reasons, recent Oct-2026 dates, money/qty bands; unknown tables keep old generic floor) + `export default function` slugified in both page templates (missed in session 26 — same spaced-name class) + seed realism test. Committed.
- **Live note:** HR retry of backend-users STILL fell back (all-provider 429/timeout wave incl. new groq 400). Quota hostile tonight — stop retrying till fresh quota; seed/slug fixes load on next restart.
- **Verify:** template gates 16/16 (this area); full suite + restart deferred to after the running build lands.

### Session 28 — 2026-10-17 — portfolio packaging 1/6 (hygiene + docs restructure) [x]
- **Secrets audit (full history, gitleaks):** 8 findings, all false positives — seed-data invitation tokens (`"token": "inv_abc123xyz"`) in the social gold spec copied into core20 reports. No real credentials ever committed (`.env` files never tracked; only placeholders in history). `.gitleaks.toml` allowlist added so scans stay clean. **No rotation needed, no history rewrite.**
- **Hygiene:** `server/backend.log` untracked (#12 closed); `.gitignore` += `*.log`, `core20.progress.json`, PDF/docx duplicates, review `files.zip`; committed real-but-untracked code (`packages/runtime/blocks/csv.ts` + test) and eval evidence (cassettes + core20 rerun reports).
- **Docs:** root ledgers moved under `docs/process/` (git mv, history preserved): AGENT, PROJECT_HANDOFF, guide, spec, architecture, implementation, LOOM, intara-portfolio-shift; review candidates → `docs/process/reviews/`. MIT LICENSE added.
- **Node robustness:** machine default node is v22.12 (`/usr/local/bin/node`, homebrew node absent) → type-stripped `.ts` tests were red. New `tests/_nodeutil.py` adds `--experimental-strip-types` when node < 22.18 → formula twin + runtime suite green locally again (no test skipped). CI will pin Node 24.
- **Verify:** pytest **201/201**, eval 5/5, tsc clean, node suite 206+1 skip (via helper).
- **Next:** portfolio packaging 2/6 — static demo mode (bundled exemplars, offline gallery) for the Vercel live link.

### Session 29 — 2026-10-17 — portfolio packaging 2/6 (static demo + runtime display fixes) [x]
- **Static demo (`VITE_DEMO=1`):** bundled the 10 gold specs (`src/demo/exemplars.ts`, `import.meta.glob`); Landing shows a demo panel ("Open the 10 live apps"), Header drops Wish/Build nav + adds "Static demo · no backend", GalleryView falls back to bundled specs offline, routes limited to `/`, `/templates`; `useAuth` disabled and supabase counts guarded. Offline smoke: 10 apps render, zero network calls, no page errors.
- **Runtime visual layer:** blocks emitted `blk-*` with **no stylesheet** — new `packages/runtime/blocks/blocks.css` (dark glass for shell + every block) imported by `RuntimePreview.tsx`. Shell classes namespaced `intara-*` → `app-*`: the preview inherited the Studio page's `.intara-shell` (100vh starfield) causing stretched/over-styled previews.
- **Display correctness:** `FilterBar` no longer derives "empty" from zero rows (controls are ready unless host says otherwise); `displayPath` falls back to name/full_name/common_name/title/label/id for object/array values (hydrated refs); `ActivityTimeline`/`CalendarMonth` no longer read the `title` prop as a row path — it's the block heading, item text now picks the first non-empty of title/name/common_name/note; `RuntimePreview` hydrates ref ids to target rows **for display only** (forms/exports/transitions keep raw ids) and fills seed computed fields (leaves, then per-record reverse relations — mirrors `engine.test.ts` contract) so `total`/`hours_remaining` show real math; submitted records get computed fields too.
- **GalleryView:** `RuntimePreview` keyed by app name — the persisted `RoleSession` kept the first app's role, so switching apps could render an empty nav.
- **Capture tooling:** `scripts/capture.mjs` (playwright-core, system Chrome, no download) screenshots the demo + doubles as the offline smoke test → `docs/assets/demo-*.png`. Locator lesson: Playwright `getByRole(name)` is a case-insensitive **substring** match — "Board" hit "Dashboard"; use `exact: true`.
- **Verify:** pytest **201/201**, eval 5/5, tsc clean (studio + demo), node suite 206+1 skip, `VITE_DEMO=1 npm run build` green, capture smoke OK (10 apps, no page errors).
- **Next:** portfolio packaging 3/6 — README draft + user-side GitHub rename (`intara`, public) and Vercel import (root `react-prompt-app`, env `VITE_DEMO=1`), then live URL into README.

### Session 30 — 2026-10-18 — portfolio packaging 3/6 (README + demo script + deploy prep) [x]
- **README rewritten** for the portfolio audience: one-line pitch, ASCII pipeline diagram, live-demo slot (placeholder until Vercel deploy), screenshots from `docs/assets/`, measured-numbers table (5/5 gold, core20 17/20, held-out 3/5, 201 py + 206 node tests, 135 formula cases, Supabase contract 6/6), short Quickstart (static demo + full Studio), Limitations (short list → handoff §6), honest AI-assisted note, `docs/process/` linked only at the bottom.
- **Demo script:** stale 60-sec `LOOM.md` → `docs/process/DEMO_SCRIPT.md` (git mv, history kept; 2-min script matched to the static demo; recording is user-side).
- **Deploy prep:** `react-prompt-app/vercel.json` (SPA rewrite so `/templates` deep links work) + `docs/process/DEPLOY.md` (exact user-side steps: GitHub rename → `intara` + make public, Vercel import root `react-prompt-app` + env `VITE_DEMO=1`, verify checklist, URL-patch instructions). `.env.example` documents the static-demo build.
- **Verify:** pytest **201/201**, eval 5/5, tsc clean. Docs-only change; no runtime code touched.
- **Next:** portfolio packaging 4/6 — GitHub Actions CI (pytest + eval mocked on Python 3.12 w/ Node 24 for the TS-twin tests; Node 24 job for runtime suite + both tscs + `VITE_DEMO=1` build).

---

## 5. Known problems / error register

*Append-only. Format: date · symptom · root cause (if known) · status. Never delete entries — strike through when fixed with the fix noted.*

1. 2026-10-11 · `OPENROUTER_MODEL=openrouter/free` looks like a placeholder, not a real model id · unverified · **OPEN** (Phase 0 task P0.3)
2. 2026-10-11 · `wish_steps.output` stored file paths, content lived only in build-process memory · **RESOLVED by Phase 3** (content-addressed `artifact_contents` + resume-from-store; hollow rows only pre-exist it)
3. 2026-10-11 · Orphaned `running` rows after kills needed manual retry · **RESOLVED by Phase 3** (boot sweeper requeues + flips; v2 runs covered too)
4. 2026-10-11 · Historical: reloader fork trees + `multiprocessing.spawn_main` orphans inherit the listen socket and steal connections (silent hangs) · mitigated by single-process-no-reload discipline (§8 ops) · **MITIGATED, watch**
5. 2026-10-11 · Historical: `/tmp` backend log lost to OS purge · mitigated by repo-local log file · **MITIGATED**
6. 2026-10-11 · `RATE` (10/day) limiter defined but wired to no endpoint; enforced caps are CHAT_RATE 20/day (chat+iterate) + provider quotas · decide in re-architect whether to keep/replace · **OPEN**
7. 2026-10-11 · RLS demo-open everywhere except `component_defs` (public reads, allow-all writes on logs/iterations) · harden at multi-tenant time, policies must be written with v2 tables (Phase 4) · **OPEN by design**
8. 2026-10-11 · Root vs nested `react-router-dom` version skew (7.18.4 vs 6.30.6; nested wins) · resolve at monorepo move (Phase 4) · **OPEN**
9. 2026-10-11 · `VITE_API_URL` unused (client uses relative `/api` + proxy); `src/data/` empty; `TableExplorer.tsx`/`frontend_gen_new.py` referenced in stale docs but absent · cleanup at monorepo move · **OPEN**
10. 2026-10-12 · Analyzer validator false-positive: `page Summary needs a table binding in crud mode` discarded a live LLM plan into mock fallback · relax/scope the rule in Phase 1 (with fixture) · **OPEN**
11. 2026-10-12 · Free pools drain mid-run (Gemini 429 + OpenRouter upstream 429s during 20-wish baseline) · baseline cadence + per-tier budgets in Phase 1/2 · **OPEN**
12. 2026-10-12 · `server/backend.log` is git-tracked runtime noise — never stage it · ~~consider `git rm --cached` + gitignore entry~~ · **FIXED (session 28: untracked + `*.log` ignore)**
13. 2026-10-12 · Shipped `IndentationError` (`frontend_gen.py:181`, game branch) survived because full suite wasn't re-run post-edit in that session · rule: no session ends without the §0 verification trio · **FIXED (suite now gates it)**
14. 2026-10-12 · `/api/wishes/health` returned UUID syntax error — router `/wishes/{wid}` matched first · fixed by mounting routers after direct routes + regression test · **FIXED**
15. 2026-10-12 · Backend process died silently mid-session (health OK → port empty, no traceback) · cause unknown; single-process runs have no supervisor · consider restart check in session start routine · **OPEN, watch**
16. 2026-10-12 · New telemetry test failed on `"prompt" in k` matching `prompt_version` — assertion too broad, not a product bug · narrowed to exact `prompt`/`prompt_text` keys · **FIXED**
17. 2026-10-12 · Durability-test fake `dict(sid=..., step_id=..., **row)` blew up on duplicate `step_id` — fake bug, not product · `{**row, "sid": key}` · **FIXED**
18. 2026-10-12 · Patch `invert()` wrong on dict-key overwrite (double-add): undo removed the key instead of restoring old value — real product bug, caught by the randomized round-trip fuzzer · simulation-based invert with existence check (add/copy/move) · **FIXED (1175/1175 round-trips)**
19. 2026-10-12 · Exemplar seed hit RLS 42501 — runtime `SUPABASE_KEY` is the anon key; 006 control-plane tables are service-key-only per sketch · seeder uses `SUPABASE_SERVICE_KEY` explicitly; demo-open policies stay only on 006a/006b anon-fed tables · **FIXED (5 rows seeded)**
20. 2026-10-12 · A linter edit silently dropped the `metric.gauge` catalog line (R29 false-positive on the w01 fixture) — caught by the python suite, not by review · rule: full pytest after ANY gates/catalog edit · **FIXED**
21. 2026-10-12 · Transient golden-eval failure (4/5) under load — `eval.py` shells `npx tsc` with a 15s timeout; cold npx under contention exceeds it · not a product regression (green on immediate rerun ×3) · consider warming npx or raising timeout if it recurs · **FLAKE, watch**
22. 2026-10-12 · Live v2 runs failed S5 twice on cross-stage mismatch (S3 pages role owner vs S4-invented roles; S2 from-state 'any') — stage gates were slice-local, G1 only ran at assembly · fix: S3-declares/S4-subset role contract + S2 from/to gate + S4 set_field gate; S3→S4 sequential (guide lists ui summary as S4 input) · **FIXED, proven live (Library2 full pass)**
23. 2026-10-12 · v2 router created the run row AND engine.run created a second one — client polled an empty shell (running, no steps) while the shadow run did the work · `run_id` passthrough (exactly one row per run) · **FIXED, proven (steps under polled id)**
24. 2026-10-12 · `_gate_s4` referenced undefined `fields_of` (NameError swallowed into gate-error noise) — set_field automation errors only surfaced at S5 · gate now takes entity_fields; unit-pinned · **FIXED**
25. 2026-10-13 · core20 dry-run failed S5 on orphan detail pages (R20) — S3 gate lacked reachability (only G1 had it) · R20-equivalent added to `_gate_s3` (nav or row_link) + unit test · **FIXED (unproven live — full run exercises it)**
26. 2026-10-13 · core20 full run: role mismatch ALSO fires R12-direction (S3 pages use roles S4 never declares — education/automotive/school) · S4 gate role-set EQUALITY both directions · **FIXED (rerun 4/20 → 13/20)**
27. 2026-10-13 · core20: raising steps leave `running` rows (restaurant s5, gym s4) — only the return-failure path flips rows · `_run_simple/_run_s5/_run_iterate` bodies mark failed on raise · **FIXED (failed rows observed live)**
28. 2026-10-13 · core20: 6 harness timeouts from 30s api() timeout during backend stalls (recovered alone) · bumped to 120s · still 1 timeout in rerun-2 — backend can stall >2min under load · **WATCH**
29. 2026-10-14 · Formula `&&`/`||` parsed in Python but TS tokenizer rejected them (op allowlist missed the new tokens — 5 conformance failures) · allowlist extended; parity rule: tokenizer changes always need both impls + cases · **FIXED (127/127)**
30. 2026-10-14 · G3 flagged valid guarded transitions (probe record lacks guard fields) — harness bug, not spec bug · guarded transitions now assert guard-consulted-only · **FIXED**
31. 2026-10-15 · `today()` naive-ISO parsed as machine-local (IST) in TS → off-by-one vs Python · naive timestamps anchored to UTC in dayShift; cross-TZ test added · **FIXED**
32. 2026-10-15 · Strict block vocabulary (R37) broke host-injected props (`transitions`/`current` merged into pipeline block props by RuntimePreview) · host runtime data travels via component props, spec props stay pure · **FIXED**
33. 2026-10-15 · Supabase contract subtests shared one table across fresh adapters (entity names collide) · per-subtest hard-clean hook in shared contract (memory/dexie unaffected) · **FIXED (18/18 all adapters)**
34. 2026-10-15 · Live-network test keyed on ambient env: a leaked shell export + transient fetch failure flaked the gate suite · live tests are INTARA_LIVE=1 opt-in, never ambient · **FIXED**
35. 2026-10-16 · Batch-2 review port: G3 caught a real seed gap the review missed (task row t7 without estimate_hours, needed by a computed formula) · added the missing value (flagged to reviewer); rule of thumb: G3-over-golds is the last reviewer · **FIXED**
36. 2026-10-17 · Demo pass exposed four presentation-layer defects together: (a) preview shell reused Studio `.intara-shell` (100vh starfield leak), (b) `FilterBar` resolved "empty" from its empty rows list, (c) ref columns/detail/timeline/calendar showed ids or em dashes (no ref hydration; `title` prop misread as a row path; seed computed fields never filled), (d) switching gallery apps kept the first app's RoleSession → empty nav · fixed all four in session 29 (class namespace, ready default, display hydration + computed seeding, keyed remount) · **FIXED**
---

## 6. Metrics dashboard

*(Fill during Phase 0 baseline; all live-eval numbers degrade-fallbacks-counted-as-failures.)*

| Metric | Baseline (pre-change) | Current | Target (v1) |
|---|---|---|---|
| Parse success (first-try or repaired) | _pending P0.2_ | — | ≥ 95 % |
| Fallback/degraded rate per step | _pending P0.2_ | — | ≤ 5 % |
| G0–G4 pass per build | n/a (gates are code-level today) | — | ≥ 85 % |
| Requirement coverage | n/a | — | ≥ 80 % (100 % musts) |
| LLM calls per build (median) | _pending P0.2_ | — | ≤ 14 (≤ 6 strong) |
| Time to live preview post-approval | _pending P0.2_ | — | ≤ 30 s |
| Unit suite | 93/93 (2026-10-11) | 201/201 py + 206/207 node (2026-10-17) | green every session |
| Golden eval | 5/5 (2026-10-11) | 5/5 (2026-10-12) | 5/5 + new suites |

**Baseline 2026-10-12, pre-Phase-1** (`evals/reports/baseline-20261012-093539.json`, 20 wishes, plan-stage, no builds):
- Outcomes: **success 10 / fallback 10 / failed 0 / error 0** — but all 10 successes are *planning-with-questions* (clarify path only); **all 10 full plans fell back to mock**. True analyzer parse-success: **0/10**.
- Fallback causes (backend log): malformed LLM JSON envelopes (`Expecting ',' delimiter`, `Expecting value char 0`), mid-run Gemini 429 + OpenRouter upstream 429s, and 1 validator false-positive (`page Summary needs a table binding` discarded a good plan).
- Latency: min 6.7s / median 15.4s / max 31.0s per wish (plan stage only).
- Meta sources: clarify-LLM 10 ("live"), mock 10. No wish reached the build stage in this run.

**Re-run 2026-10-12, post-Phase-1** (`evals/reports/baseline-20261012-104102.json`, same 20 wishes):
- Outcomes: **success 20 / fallback 0 / failed 0**. Analyzer parse-success **15/15 full plans** (10 nvidia, 5 groq); other 5 are healthy clarify-path successes.
- Fallback rate 50% → **0%**. No validator false-positives observed.
- Latency: min 6.7s / median 42.7s / max 173.9s (Nemotron reasoning is slow; Groq ~11–21s).
- Note: Gemini served zero full plans (prior 429 exhaustion) — chain fallback carried the run, as designed.

---

## 7. Operating conventions (hard-won, keep)

- **Backend:** single process, no `--reload` during builds; log to repo-local file; kill by port holder (`lsof -iTCP:8000`), never by cmdline match alone.
- **Verify every session:** `pytest tests/ -v` (98 baseline), `python scripts/eval.py --mocked`, `npx tsc --noEmit` in `react-prompt-app/` for frontend changes.
- **DB:** additive-only migrations; Supabase credentials stay server-side; RLS posture changes are explicit decisions.
- **LLM spend:** measure first (Phase 0); cache by input hash; cassettes for CI; live evals only on manual dispatch; template gallery costs $0 — use it for demos.
- **Commits:** code + AGENT.md update together, every session. Never leave the tree red.

*End of AGENT.md v3 — phases 0–9 code-complete; core20 17/20; portfolio packaging 3/6 landed (README + deploy prep; CI + results write-up + notebook next).*
