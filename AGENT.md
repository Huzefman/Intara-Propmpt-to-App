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
| Migrations | `supabase/migrations/001–005` | 006+ are v2 (Phase 4) |
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

### Phase 1 — Gateway + visible fallback [ ]
*Goal: structured output everywhere; every fallback labelled. (Guide M0.1–M0.2)*
- [ ] P1.1 `server/services/llm.py`: per-provider capability probe (cached) → `json_schema`/`json_object`/`prompt_only`; `response_format` / `response_mime_type` wired per provider with auto-fallback; `max_output_tokens` per call; keep cooldown chain + `LLM_ONLY`
- [ ] P1.2 `server/utils/json_parse.py`: parse ladder (`json.loads` → fence/prose strip → control-char/escape normalisation → truncation repair → **one** LLM repair with exact error) + `finish_reason` truncation detection (split, never blind-repair)
- [ ] P1.3 `fallback_reason` on every generator return path → stored in `wish_steps.output` → Studio badge (thread + BuildingView)
- [ ] P1.4 `tests/test_json_parse.py`: fixtures for unescaped newlines, tabs, trailing commas, fenced+prose, truncated, BOM, smart quotes, empty/prose-only
- [ ] P1.5 Re-run baseline script; record delta in §6
- **Accept:** fixtures green; live re-run shows parse-success ≥ baseline +15pp; 100% of fallbacks carry reason; suite green

### Phase 2 — Telemetry + cassettes [ ]
*Goal: product health numbers + keyless CI. (Guide M0.3, M0.6)*
- [ ] P2.1 Migration `006a_llm_calls.sql` + write path in gateway: provider, model, tokens in/out, latency, finish_reason, parse_outcome, repair_used, fallback_reason
- [ ] P2.2 `GET /api/health/llm-stats` (counts by provider/outcome, last 24h)
- [ ] P2.3 Record/replay cassettes for LLM calls; `eval.py --replay` runs offline, byte-identical
- [ ] P2.4 Prune/aggregate policy note (free-tier 500 MB guard)
- **Accept:** post-build counts match logs; full eval passes with zero keys via replay

### Phase 3 — Durable state [ ]
*Goal: kills/restarts never lose work. (Guide M0.4–M0.5)*
- [ ] P3.1 Content-addressed artifact persistence (`006b_artifacts.sql` or jsonb column — decide in-session, record here): every step output stored by hash, not paths
- [ ] P3.2 Resume reads stored content (delete hollow-restore + regen path once proven)
- [ ] P3.3 Startup sweeper: orphaned `running` steps/wishes → `failed`/requeue on boot
- [ ] P3.4 Kill-resume test: start build → `kill -9` mid-step → restart → retry resumes with **zero** repeated LLM calls (assert call count)
- **Accept:** kill-resume test green; no row stuck in `building` after unclean shutdown

### Phase 4 — Spec v1 + control-plane DB [ ]
*Goal: the App Spec as data with a linter. (Guide M1.2–M1.5, M1.7)*
- [ ] P4.1 `packages/spec/`: JSON Schema v1 (spec §4 shape), generated Pydantic + TS types, CI drift check (`scripts/gen_spec_types.py --check`)
- [ ] P4.2 Linter G1 (refs, ids, naming, field-type fit, lifecycle reachability, nav/page/role coverage, formula parse) + ≥25 failing fixtures; gold specs pass
- [ ] P4.3 Formula language: grammar + TS parser/evaluator + shared conformance JSON (≥100 cases, fuzz, no `eval`)
- [ ] P4.4 JSON Patch apply/invert + version service (round-trip property test)
- [ ] P4.5 Migration `006_v2_control_plane.sql`: projects, versions, runs, steps, events, artifacts, exemplars, feedback (+ RLS written now, service-key access until multi-tenant)
- **Accept:** gold-spec fixtures pass G0/G1; patch round-trip green; migration applies cleanly after 001–005

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
| Unit suite | 93/93 (2026-10-11) | 98/98 (2026-10-12) | green every session |
| Golden eval | 5/5 (2026-10-11) | 5/5 (2026-10-12) | 5/5 + new suites |

**Baseline 2026-10-12** (`evals/reports/baseline-20261012-093539.json`, 20 wishes, plan-stage, no builds):
- Outcomes: **success 10 / fallback 10 / failed 0 / error 0** — but all 10 successes are *planning-with-questions* (clarify path only); **all 10 full plans fell back to mock**. True analyzer parse-success: **0/10**.
- Fallback causes (backend log): malformed LLM JSON envelopes (`Expecting ',' delimiter`, `Expecting value char 0`), mid-run Gemini 429 + OpenRouter upstream 429s, and 1 validator false-positive (`page Summary needs a table binding` discarded a good plan).
- Latency: min 6.7s / median 15.4s / max 31.0s per wish (plan stage only).
- Meta sources: clarify-LLM 10 ("live"), mock 10. No wish reached the build stage in this run.

---

## 7. Operating conventions (hard-won, keep)

- **Backend:** single process, no `--reload` during builds; log to repo-local file; kill by port holder (`lsof -iTCP:8000`), never by cmdline match alone.
- **Verify every session:** `pytest tests/ -v` (98 baseline), `python scripts/eval.py --mocked`, `npx tsc --noEmit` in `react-prompt-app/` for frontend changes.
- **DB:** additive-only migrations; Supabase credentials stay server-side; RLS posture changes are explicit decisions.
- **LLM spend:** measure first (Phase 0); cache by input hash; cassettes for CI; live evals only on manual dispatch; template gallery costs $0 — use it for demos.
- **Commits:** code + AGENT.md update together, every session. Never leave the tree red.

*End of AGENT.md v1 — Session 1 done (Phase 0 complete). Next: Phase 1 gateway (P1.1–P1.5).*
