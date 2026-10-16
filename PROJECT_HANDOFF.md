# Intara — Planning Handoff (2026-10-16)

> **For:** a smart planning agent deciding where to steer this project.
> **Companions (read in this order):** this file (decisions + state) →
> `AGENT.md` (phased build ledger, sessions 0–26, error register §5) →
> `INTARA_ARCHITECTURE_GUIDE.md` (target architecture + why, 1170 lines) →
> `PROJECT_SPEC_FOR_PLANNING_AGENT.md` (system as-built).
> **Rule if anything disagrees:** trust code, then fix the doc.

## 1. What this is

Intara ("Planet of Wishes"): a non-technical small business owner describes an
app in plain words and gets a **working app in the browser** — data, screens,
roles, automations — plus downloadable code. Core bet (ADR-1, locked):
**spec-first runtime** — LLMs write small typed App Specs (JSON data); a
tested engine executes them; code is an export target, not the product.

## 2. Objective (unchanged)

Production-grade prompt-to-app for small non-tech businesses on **$0 free
tiers**, English-only v1, Track B (freeform custom code) deferred until Track
A is user-validated.

## 3. Where things stand (measured, not claimed)

- **Phases 0–9 code-complete.** Test suites (2026-10-16 runs): **pytest
  201/201**, **node 206 pass + 1 env-skip** (~91% lines), **eval 5/5**,
  both `tsc` clean, `vite build` green.
- **core20 live eval: 17/20 (85% = the accept bar).** Median 9 LLM calls
  (budget ≤14 ✅), median wall ~4.5 min (target ≤3 min, quota-throttled),
  requirement coverage 1.0 on green, diversity 12 combos with 0.028 entity
  overlap, held-out domains 3/5 green (invoicing, gym, helpdesk).
- **10 gold specs**, all G0/G1-clean, G3 green: inventory, booking,
  crm-leads, repair-tracker, leave-hr (hand) + veterinary, education,
  social, productivity, gardening (pipeline + human-reviewed).
- **Backend + Studio run locally right now** (`:8000` + `:5173`; restart
  procedure in §8).

## 4. Architecture as-built (two builders, one Studio)

- **v1 builder (Track B legacy):** wish → clarify → plan → approve →
  sequential codegen → Sandpack trial + zip download. Deterministic
  templates + LLM per-page/per-table with template fallback. *Still the only
  path that produces downloadable code.*
- **v2 pipeline (spec-first):** S0 Intake → S1 Clarifier → S2 Modeler →
  S3 Designer → S4 Logic → S5 Assembler + Critic → S6 Seed. Versioned
  prompts (§8.4 structure), repair loops (≤2, cooling temps), deterministic
  fallbacks marked degraded, quota propagates (never burns repairs on 429).
  S3→S4 sequential (S4 consumes S3 page roles). State machine in
  `server/services/run_engine.py` (budgets, resume same-id, SSE v2,
  content-addressed artifacts, kill-resume proven live).
- **Runtime (`packages/runtime`, TS):** engine (validate/defaults/computed/
  refs+lifecycle/permissions/`where`-subset) + memory/Dexie/Supabase
  adapters (one shared contract suite, all green incl. 6/6 live Supabase) +
  shell (routes/nav/theme/roles/PIN gate) + 14 blocks + automations executor
  + CSV + storage uploads + print. No LLM at runtime (statically tested).
- **Gates (fail-closed):** G0 schema (generated Pydantic/TS from one JSON
  Schema + drift check) · G1 semantic lint (**R01–R50** + warnings; ported
  from two human review rounds) · G2 requirement coverage · G3 generated
  engine tests · G4 render smoke. Formula language (own parser, no `eval`,
  135 shared Py/TS conformance cases) + RFC 6902 patch/invert/version tree.
- **Studio (`react-prompt-app`):** Landing, WishVault, Blueprint (cards,
  approve, chat-patch, deterministic roles editor, timeline, build report,
  dev toggle, feedback widget, live RuntimePreview), Templates gallery,
  Archives, Constellation, PIN lock, roles matrix, print/PDF.

## 5. Complete inventory

- **Backend endpoints** (`server/routers/`): wishes CRUD + plan/answer/
  suggest/chat/iterate/apply/revert/retry/regenerate/stream; runs
  start/status/events/eventlog/approve/chat/patch; versions list/revert;
  exemplars list/get; feedback post/export(CSV); health + llm-stats.
- **DB (`supabase/migrations/001–009`, additive-only):** wishes,
  wish_steps, wish_messages, wish_iterations, component catalog, v2 control
  plane (projects, versions, runs, steps, events, exemplars, feedback),
  llm_calls, artifact_contents, apps + records (data plane), storage bucket
  + policies, version summaries. RLS: demo-open on legacy tables **by
  design**; service-key-only on 006/007 tables.
- **Scripts:** `eval.py --mocked`, `eval_live.py`, `core20.py`
  (`--probe/--live/--limit/--resume/--status-file`), `gen_spec_types.py
  --check`, `seed_components.py`, `seed_exemplars.py`,
  `build_retrieval_index.py`.
- **Keys needed (names only, values in `server/.env`, never committed):**
  `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`,
  `NVIDIA_API_KEY`, (`DEEPSEEK_API_KEY` unconfigured — slot reserved),
  `SUPABASE_URL`, `SUPABASE_KEY` (anon), `SUPABASE_SERVICE_KEY`;
  Studio optionally `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`.

## 6. Limitations — the full list, no softening

1. **Quota dominates everything on free tiers.** Gemini daily-caps (~20/day);
    OpenRouter pool congests; Groq is the workhorse; Nvidia is slow/sloppy.
    ~Half of all observed failures are quota-shaped. Paid keys remove this
    class overnight (~cents per build); nothing else does.
2. **Role coherence has no automatic repair (standing limitation).**
    S2 invents transition roles nothing declares → fail-closed at S5 with
    specific errors. Rewriting access at assembly would be fail-open, so
    this stands until a real design (e.g. single role source) lands.
3. **Single-worker fragility.** One uvicorn worker + sync Supabase calls in
    async paths: a grinding build can wedge `/health` for 20s+; backend has
    died silently before (no supervisor). Acceptable for demo, not for users.
4. **Demo-grade security.** Demo-open RLS, anon keys, device-grade PIN,
    no logins, no multi-tenant isolation. Fine for demos; disqualifying for
    strangers' data.
5. **No hosting/publish path.** Runs on the operator's machine. No export
    compiler yet — preview (spec) and download (Track B code) are siblings,
    not the same artifact.
6. **Email is intent-only.** Automations record `send_email` as deferred
    effects; no provider key exists (user has none, none soon).
7. **Template floor.** Fallback output is generic-correct, recently
    humanized (seeds, slugified identifiers) but never tailored.
8. **Track B is narrow by decision.** Freeform/custom-code wishes fail
    closed; custom-block SDK, sandbox, interaction smoke don't exist.
9. **No user validation yet.** All quality numbers are lab numbers; the
    3-human UAT (describe→approve→edit→share, observed) hasn't happened.
10. **Watch items (transient, logged):** `npx tsc` 15s flake in evals;
    backend stalls >2min under load; free-model ids rotate; seeds go stale
    (dated Oct-2026 rows); machine clock has jumped ~3h (don't trust
    timestamp arithmetic for stuck-detection — watch the log tail).
11. **Ledger debt:** AGENT.md §5 items #2/#3 still read OPEN but were
    resolved by Phase 3 (durable artifacts + sweeper) — the register wasn't
    updated; treat as closed.

## 7. Locked constraints (do not relitigate without the user)

Spec-first runtime · Track B deferred past user validation · English-only ·
additive-only migrations · fail-closed gates, no silent fallback (every
fallback labelled + counted as failure) · deterministic templates stay
byte-stable · no paid infra (user revisits explicitly for LLM keys) ·
LangChain rejected as framework (custom engine is the differentiator; SDK
clients only) · no `eval`/arbitrary code · prompts versioned, [1]–[3]
byte-stable for prefix caching.

## 8. Operator runbook

```bash
# backend (keys in server/.env; single process, no --reload)
lsof -iTCP:8000 -sTCP:LISTEN -t | head -1 | xargs kill; sleep 3
cd server && nohup python -u /opt/anaconda3/bin/uvicorn main:app --port 8000 > .run.log 2>&1 &
curl -s -m 10 http://localhost:8000/health            # expect {"ok":true,...}
# frontend — cd react-prompt-app && npm run dev  → :5173 (proxies /api)
# verify trio — pytest tests/ · python scripts/eval.py --mocked · tsc --noEmit
# migrations — paste supabase/migrations/*.sql in dashboard SQL editor in order
# stuck detection — log tail moving, not timestamps (clock jumps observed)
```

## 9. Suggested steering (ranked, with costs)

1. **Paid LLM key (user purchase, ~cents/build).** Removes failure class
    #1, unblocks honest re-measurement, makes retries land. Highest ROI.
2. **3-human UAT (user recruits).** Only real validation gate left; decides
    whether Track B is even needed. Everything else is lab work until this.
3. **UI polish slice (planned, dark-only default).** Theme stylesheets per
    archetype + 14-block visual pass + screenshot review. Zero quota cost.
4. **Export compiler (Phase 11 slice).** Closes the preview/download gap;
    proven by G7 (tsc + vite build + TestClient matrix in CI).
5. **Roles-editor depth + multi-role coherence design.** Addresses
    limitation #2 properly (single role source); needs a design decision.
6. **Phase 10 Track B — only if UAT says Track A is too narrow.**
7. **Phase 11 Ship — hosting, multi-tenant auth/RLS, billing** — after UAT.

Latest ledger state: suite 201/201 py + 206+1 node, eval 5/5, core20
17/20, 10 golds, backend healthy. Tree must stay green: verify trio
before stopping, code + AGENT.md committed together.
