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
| Tests | `tests/` (93 green baseline) | + `scripts/eval.py` (5/5) + `scripts/seed_components.py` |
| Guide + spec | `INTARA_ARCHITECTURE_GUIDE.md`, `PROJECT_SPEC_FOR_PLANNING_AGENT.md` | Read both before planning |
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

### Phase 4 — Spec v1 + control-plane DB [ ] *(code done 2026-10-12, live apply pending)*
*Goal: the App Spec as data with a linter. (Guide M1.2–M1.5, M1.7)*
- [x] P4.1 `packages/spec/app-spec.schema.json` + `scripts/gen_spec_types.py` → `packages/spec/app-spec.ts` + `server/engine/spec_models.py` (pydantic v2); `--check` drift green, both outputs compile/import. Generator lessons: `from`→alias, `field`→SpecField (pydantic import shadow), scalar `$defs` need alias emission.
- [x] P4.2 `server/gates/g1_lint.py` (36 rules R01–R36 + W01) + `g0_validate.py`; fixtures as patches (`packages/spec/fixtures/base.json` + `fail-patches.json`, 37 cases incl. warning-only); 2 golds pass G0/G1 clean. Reachability readings recorded in module docstring (row_link counts, empty roles = public, BFS from initial).
- [x] P4.3 Formula language (`grammar.md`): `server/engine/formula.py` + `packages/spec/formula/formula.ts` (erasable syntax, node ≥22) + 118 shared cases; node --test 120/120, pytest parity green, 500-input fuzz (only FormulaSyntaxError/FormulaError escape), no-eval grep enforced. Parity traps fixed: float/int strictness, non-finite rejection.
- [x] P4.4 `server/engine/patch.py` (RFC 6902 + simulation-based invert: `-` resolution, overwrite→replace-old) + `server/engine/versions.py` (create/patch/get/history/undo); 1175 randomized round-trips green.
- [x] P4.5 `supabase/migrations/006_v2_control_plane.sql` (projects, versions, runs, steps, events, exemplars, feedback + 006a run_id FK; RLS on, service-key only per sketch). Deviations: `artifacts` table omitted (006b covers it), `apps`/`records` deferred (data-plane migration), no monorepo move — paths adapted (`server/gates`, `server/engine`).
- **Accept:** golds pass G0/G1 ✅ (2 now; remaining 3 + PRD adapter = Phase 5 P5.1); patch round-trip ✅; migration applies cleanly — **PENDING dashboard apply**
- **Deviations from AGENT.md scope:** 2 gold specs now (guide: 1 per ~2 days; rest in Phase 5); Python formula port done now (guide said "later"); no M1.1 monorepo move (deferred to Phase 5/6 start).

### Phase 5 — Gold specs + retrieval seed [ ] *(parallelisable with Phase 4)*
*Goal: hand-authored truth to retrieve and eval against. (Guide M1.6, M7-start)*
- [ ] P5.1 Five gold specs (inventory, booking, CRM, repair tracker, leave/HR) + PRD→Spec adapter for legacy fixtures
- [ ] P5.2 Embed catalog + exemplars (768-d, sequential scan, tag filters)
- [ ] P5.3 Hold out 5 Appendix-D domains for `heldout` eval; never retrieve from them
- **Accept:** gold specs pass G0/G1; retrieval hit-rate test on held-out domains recorded

### Phase 6 — Runtime v1 [ ]
*Goal: apps run as data, no LLM involved. (Guide M2)*
- [ ] P6.1 Engine: validation, defaults, computed, refs/onDelete, lifecycle, permissions (vitest, ≥90% line coverage)
- [ ] P6.2 Adapters `memory` + `dexie` + shared contract suite (same tests, both green)
- [ ] P6.3 Shell: routes/nav/theme tokens, dev role switcher
- [ ] P6.4 ★ blocks (~14) with fixtures + empty/loading/error states (Playwright per block)
- [ ] P6.5 Spec-driven test generator (G3) + render smoke (G4); run on all gold specs
- [ ] P6.6 Studio `<RuntimePreview>` replaces Sandpack for Track A (Sandpack stays for legacy/trial)
- **Accept:** all gold specs operate (CRUD, filter, kanban drag-transition, stats, role restrictions) with zero LLM calls; runtime ≤ ~400 KB gzipped budget tracked

### Phase 7 — Agents + run engine + Studio slice [ ]
*Goal: the v2 pipeline builds specs end to end. (Guide M3 + M5-lite)*
- [ ] P7.1 Run engine: state machine, budgets, resume, SSE v2 from `run_events`, replay
- [ ] P7.2 Agents S0–S6 with versioned prompts + cassette unit tests; S3∥S4 capped at 2
- [ ] P7.3 Retrieval wired (catalog slice + 1–2 exemplars, logged); Critic + `trace[]` + ≤2 repairs
- [ ] P7.4 Blueprint view (Data/Screens/Rules/Assumptions cards) + approve + chat-patch + live preview
- [ ] P7.5 Live `core20` eval; record §6; diversity check (≥5 distinct archetype/nav/theme combos per 10 outputs)
- **Accept (MVP demo):** core20 ≥85% G0–G4 within ≤2 repairs; median ≤14 calls, ≤3 min; coverage ≥80%; type-a-wish → live distinct working app demoable

### Phase 8 — Capability depth [ ]
*Goal: Track A covers real SMB work. (Guide M4)*
- Lifecycle UI + transition buttons, client-side automations executor, more computed blocks, roles editor, `file`/`image` fields (Storage), CSV import/export UI, `chart.*`, `data.calendar`, Supabase adapter + single-user auth, email provider (verify limits), print/PDF views; every block `stable` only with fixtures+tests
- **Accept:** 10 gold specs pass G3/G4; adapter suite green on supabase

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

### Session 6 — 2026-10-12 — Phase 4 code complete [ ]
- **Done:** P4.1–P4.5 code: spec schema + codegen (TS+Pydantic, drift green), G0/G1 gates (36 rules, 37 fixtures, 2 golds clean), formula twins (118 shared cases, 120/120 node, fuzz green), patch+versions (1175 randomized round-trips), 006 migration file. Suite **159/159**, eval 5/5, `app-spec.ts` compiles under `--strict`. No server-runtime change → no restart.
- **Problems:** (a) 006 NOT yet applied — needs dashboard SQL editor (no DDL path in env); nothing reads the new tables yet, so no fail-fast risk meanwhile; (b) see §5 #18.
- **Next:** user applies 006 → verify tables → close Phase 4 → Phase 5 (golds 3–5 + retrieval).

---

## 5. Known problems / error register

*Append-only. Format: date · symptom · root cause (if known) · status. Never delete entries — strike through when fixed with the fix noted.*

1. 2026-10-11 · `OPENROUTER_MODEL=openrouter/free` looks like a placeholder, not a real model id · unverified · **OPEN** (Phase 0 task P0.3)
2. 2026-10-11 · `wish_steps.output` stores file paths, content lives only in build-process memory; restarts force regeneration · by design, fix = Phase 3 (P3.1 durable artifacts) · **OPEN**
3. 2026-10-11 · Orphaned `running` rows after kills need manual retry; no startup sweeper · fix = Phase 3 (P3.3) · **OPEN**
4. 2026-10-11 · Historical: reloader fork trees + `multiprocessing.spawn_main` orphans inherit the listen socket and steal connections (silent hangs) · mitigated by single-process-no-reload discipline (§8 ops) · **MITIGATED, watch**
5. 2026-10-11 · Historical: `/tmp` backend log lost to OS purge · mitigated by repo-local log file · **MITIGATED**
6. 2026-10-11 · `RATE` (10/day) limiter defined but wired to no endpoint; enforced caps are CHAT_RATE 20/day (chat+iterate) + provider quotas · decide in re-architect whether to keep/replace · **OPEN**
7. 2026-10-11 · RLS demo-open everywhere except `component_defs` (public reads, allow-all writes on logs/iterations) · harden at multi-tenant time, policies must be written with v2 tables (Phase 4) · **OPEN by design**
8. 2026-10-11 · Root vs nested `react-router-dom` version skew (7.18.4 vs 6.30.6; nested wins) · resolve at monorepo move (Phase 4) · **OPEN**
9. 2026-10-11 · `VITE_API_URL` unused (client uses relative `/api` + proxy); `src/data/` empty; `TableExplorer.tsx`/`frontend_gen_new.py` referenced in stale docs but absent · cleanup at monorepo move · **OPEN**
10. 2026-10-12 · Analyzer validator false-positive: `page Summary needs a table binding in crud mode` discarded a live LLM plan into mock fallback · relax/scope the rule in Phase 1 (with fixture) · **OPEN**
11. 2026-10-12 · Free pools drain mid-run (Gemini 429 + OpenRouter upstream 429s during 20-wish baseline) · baseline cadence + per-tier budgets in Phase 1/2 · **OPEN**
12. 2026-10-12 · `server/backend.log` is git-tracked runtime noise — never stage it · consider `git rm --cached` + gitignore entry · **OPEN**
13. 2026-10-12 · Shipped `IndentationError` (`frontend_gen.py:181`, game branch) survived because full suite wasn't re-run post-edit in that session · rule: no session ends without the §0 verification trio · **FIXED (suite now gates it)**
14. 2026-10-12 · `/api/wishes/health` returned UUID syntax error — router `/wishes/{wid}` matched first · fixed by mounting routers after direct routes + regression test · **FIXED**
15. 2026-10-12 · Backend process died silently mid-session (health OK → port empty, no traceback) · cause unknown; single-process runs have no supervisor · consider restart check in session start routine · **OPEN, watch**
16. 2026-10-12 · New telemetry test failed on `"prompt" in k` matching `prompt_version` — assertion too broad, not a product bug · narrowed to exact `prompt`/`prompt_text` keys · **FIXED**
17. 2026-10-12 · Durability-test fake `dict(sid=..., step_id=..., **row)` blew up on duplicate `step_id` — fake bug, not product · `{**row, "sid": key}` · **FIXED**
18. 2026-10-12 · Patch `invert()` wrong on dict-key overwrite (double-add): undo removed the key instead of restoring old value — real product bug, caught by the randomized round-trip fuzzer · simulation-based invert with existence check (add/copy/move) · **FIXED (1175/1175 round-trips)**

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
| Unit suite | 93/93 (2026-10-11) | 159/159 (2026-10-12) | green every session |
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

*End of AGENT.md v3 — Sessions 0–2 done, Session 3 closed Phase 1. Next: Phase 2 telemetry + cassettes.*
