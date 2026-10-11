# INTARA — Planet of Wishes — Full Project Specification for Planning Agent

> **Purpose of this file:** Give a downstream planning AI agent complete, self-contained context about the current codebase so it can produce a further build/roadmap plan — especially a **full re-architecture** of the product.
> **How to use:** Read this file top-to-bottom before proposing any plan. All paths are relative to repo root `/`. Do not assume anything not stated here — inspect code if unsure.
> **Freshness:** Rewritten from live codebase inspection (server ~4,700 lines Python across ~30 modules; 93 tests green; eval 5/5). Prior versions of this file are stale — trust this one, then trust code.

---

## 1. Project Identity

- **Name:** Intara — Planet of Wishes
- **Tagline:** "Make a software wish come true — describe any app, Intara weaves schemas, frontend, backend, and specs as stardust."
- **Theme:** Fictional planet Intara, 3.7 light years away — obsidian oceans, violet auroras. Dark nebula glass UI (bg `#07070B`, nebula `#8B5CF6` / light `#A78BFA` / `#7C3AED`, text `#F8FAFC`, muted `#CBD5E1`, faint `#94A3B8`, dim `#64748B`; glass `rgba(255,255,255,0.06)`). Fonts: Space Grotesk (display), Inter (body), JetBrains Mono (code). Motion easings `--ease-premium (0.16,1,0.3,1)`, `--ease-fluid (0.32,0.72,0,1)`. See `docs/INTARA_SCOPE.md`, `server/data/intara_lore.md`.
- **Positioning:** Miniature Rocket.new / Lovable / Bolt clone, but themed, opinionated, locked-stack, free-tier runnable. Built for portfolio + internship demos; benchmark gate is 5 golden wishes (see `docs/BENCHMARK.md`).
- **Current version:** v1.x — staged plan→build pipeline + runnable zip + browser trial + chat-to-refine + component composition foundation. **Not yet:** no deploy/hosting of generated apps, no GitHub push, no billing/teams, demo-grade auth/tenancy (see §12).

**Core promise today:**
```
Wish text --(Intara)--> clarify Q&A --> AppSpec/BuildPlan --> DAG build --> blocking gates --> Zip + Share + Browser Trial
                      └─ RAG (pgvector 3072d) → cites          └─ chat iterate (diff-first patches + revert)
                      └─ component composition (catalog → DAG) [new]
```

---

## 2. Monorepo Layout

```
/
  README.md                        # user-facing overview (PARTLY STALE — see §13)
  architecture.md                  # whiteboard sketch (STALE — pre-staged-pipeline, see §13)
  implementation.md                # old fix plan (historical)
  LOOM.md                          # 60-sec demo script (historical)
  PROJECT_SPEC_FOR_PLANNING_AGENT.md # this file
  package.json                     # root: jszip + react-router-dom ^7.18.4 (NOTE: skew vs nested ^6.30.6)
  node_modules/                    # root-level (legacy)
  builds/
    photovault.zip                 # checked-in example generated app (PhotoVault, 43 files, exercises file-upload)
  assets/                          # planet/starfield/orb art + ASSET_PROMPTS.md
  example-pages/*.png              # screenshots
  docs/
    INTARA_SCOPE.md                # theme bible + artifacts spec (PARTLY SUPERSEDED — see §13)
    BENCHMARK.md                   # 5 golden wishes, 6 checks
  react-prompt-app/                # Intara shell frontend (the builder UI itself)
    package.json                   # scripts dev/build(tsc && vite build)/preview; deps sandpack-react ^2.20.0, supabase-js ^2.45.0, dexie ^4.4.6, framer-motion ^13.4.0, jszip ^3.10.2, react ^18.3.1, react-dom ^18.3.1, react-router-dom ^6.30.6; dev typescript ^5.5.3, vite ^5.4.2, plugin-react ^4.3.1
    vite.config.ts                 # port 5173, alias @->./src, proxy /api -> http://localhost:8000 (rewrite strips /api)
    vercel.json                    # SPA rewrite /(.*)->/index.html, build/dist
    index.html                     # title, Inter+Space Grotesk+JetBrains Mono fonts, #root
    src/
      App.tsx                      # BrowserRouter + Layout + Suspense; / eager Landing; lazy WishVault, Constellation, Archives
      main.tsx, supabase.ts        # supabase client w/ demo fallback (demo.supabase.co) + isSupabaseDemo flag
      api.ts                       # LEGACY duplicate: generateSchema + askRag only
      api/client.ts                # full client (see §5 table): 150s AbortController on createPlan, PlanAbortedError, reconcileWish (<3min), EventSource stream
      pages/
        Landing.tsx                # hero + PlanetOrb + 8 example chips + wish count + staged/one-shot toggle + WishInput + Pillars/HowItWorks + lore + RAG box
        WishVault.tsx              # legacy weaving spinner / classic ArtifactVault / staged Studio (rail+thread+preview) + BuildingView (DAG pills, per-step rows, progress, live feed, retry)
        Constellation.tsx          # history: Supabase select (fallback /api/wishes), SVG star-map (hash→position) + filterable list
        Archives.tsx               # RAG ask UI over docs
      components/
        Layout.tsx                 # /wish/* edge-to-edge (no header/footer), else Header + 1080px main + footer
        Header.tsx, PlanetOrb.tsx (framer-motion tilt + glow), WishInput.tsx (NO debounce — immediate onChange, 500-char count),
        ArtifactVault.tsx          # 5 tabs Trial/Schemas/Frontend/Backend/Scroll + copy/zip/share, AnimatePresence transitions
        PreviewTrial.tsx           # SandpackProvider (react-ts, autorun, 600ms recompile) + 380px preview + IndexedDB table sidebar
        StudioRail.tsx, StudioPreview.tsx (Preview/Code modes, file explorer, build logs), RocketSections.tsx, ErrorBoundary.tsx
        AgentThread.tsx            # clarify cards, clarity score, PlanProgress stepper, plan summary+approve, WhatIDid, zip/regen, SuggestChips, ChatThread (Q&A + fix/fork/retry chips + diff preview + apply/revert + 20/day budget)
      lib/
        zip.ts                     # buildWishZip: {slug}/frontend + {slug}/backend + README + PRD.json + CITES.md
        sandpack.ts                # toSandpackFiles (leading /, hides package/mock/vite/tsconfig, ensures main.tsx)
        hash.ts                    # FNV-1a
      hooks/
        useWish.ts                 # initial fetch w/ 8s busy timer + 2s poll (90 attempts max), stops on ready|failed|awaiting_approval
        useAuth.ts, useReveal.ts (scroll reveal, threshold 0.12)
      theme/                       # tokens.ts + intara.css (~937 lines: glass/orb/inputs/tabs/studio-shell grid/chat/diff/codeview)
      public/assets/               # planet-intara.png, starfield, wish-orb, constellation, nebula-gradient, glyphs/*
      data/                        # EMPTY directory
      .env.example                 # VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY / VITE_API_URL (note: src uses relative /api + proxy; VITE_API_URL currently unused)
  server/                          # FastAPI Planet core (the builder backend)
    main.py (140 lines)            # CORS *, Gemini client (60s timeout), tenacity retry EXCEPT quota, /generate, /rag, /health, mounts routers/wishes at /api + /
    requirements.txt               # fastapi==0.110.1, uvicorn==0.29.0, python-dotenv==1.0.1, supabase==2.31.0, google-genai==1.57.0, openai>=1.40.0, tenacity==8.2.3, pydantic>=2.9.0, httpx==0.28.1
    .env.example                   # all LLM keys/models, Supabase, OPENROUTER_EMBED_MODEL= (empty), LLM_COOLDOWN_SECONDS, LLM_ONLY (see §9)
    backend.log                    # local dev log (untracked noise, safe to delete)
    prompts/
      intara.py                    # INTARA_PLANNER_PROMPT (legacy one-shot shape)
      build_plan.py                # BUILD_PLAN_PROMPT (legacy v2 path)
      analyzer.py                  # ANALYZER_SYSTEM_PROMPT: 10-type taxonomy incl. game|tool|showcase, appKind/gameType keys, entity rules (0-5 crud / 0-2 interactive), UI catalog (+board-grid, game features), strict JSON schema, 2 few-shots (task tracker + tic-tac-toe)
      frontend_page.py / frontend_page_v2.py  # legacy + rich page prompt (+build_frontend_game_prompt: 2-file page+logic.ts contract)
      backend_table.py / backend_table_v2.py  # legacy + rich table prompt (+build_backend_scores_prompt: declared-routes-only)
      schema_v2.py                 # FK/RLS/index prompt (+build_schema_game_prompt: minimal, no FK/RLS demands)
    services/
      llm.py (572 lines)           # chain Gemini → OpenRouter → Groq → Nvidia → DeepSeek; cooldowns; LLM_ONLY; timeouts; status (see §6.5)
      planner.py                   # legacy one-shot plan_wish(): mock_prd fixtures + LLM guarded + repair; quota → mock+warning (never raises)
      planner_v2.py                # plan_build(): analyzer-first, legacy BUILD_PLAN_PROMPT fallback, mock_build_plan/game enrichment; GAME_WORDS routing; crud table-binding guards
      analyzer.py (221 lines)      # analyze_prompt(): single LLM → AppSpec; _app_kind/_validate_app_spec/_derive_build_graph; _compose_or_legacy_dag; mock fallbacks; quota → mock+retry-hint
      prompt_enhance.py            # score_prompt() deterministic 5..98 + clarify_prompt() LLM-first Q&A (max 3×3) + redraft_prompt(); READY_THRESHOLD=70; never raises 429
      suggest.py                   # suggest_next(): deterministic domain rules + generic fillers (max 4, no LLM)
      orchestrator.py (694 lines)  # run_build_sequential(): threaded steps, 600s watchdog, resume+requeue, fail-closed, final assembly (see §6.3)
      assembler.py                 # legacy one-shot assemble(): generators + scaffolds + mock merge, dedupe, README/cites
      contract.py (384 lines)      # contract IR + 9 check functions incl. check_csv_export/check_file_upload (see §6.3)
      gates.py (432 lines)         # tsc/vite + TestClient CRUD matrix (declared-route enforcement) + game rule proofs + repair (see §6.3)
      validator.py (58 lines)      # esbuild-FREE light checks: pages-scoped default export, brace balance, double-brace heuristic, ast.parse, import consistency
      iterate.py (435 lines)       # diff-first rewrites: resolve_step, 3-file cap, SEARCH/REPLACE patches, apply/revert snapshots, no-LLM apply path
      chat.py (124 lines)          # 1-call answers, compact context, action chips (retry/fix/fork), degraded stardust replies, never 429s
      rag.py                       # chunk 400/50, embed via llm.embed_texts → Gemini fallback, match_docs RPC + dim fallbacks, synthesize + cites[:120], seed_docs (7 texts)
      generators/
        schema_gen.py              # LLM-first (game prompt branch) + _schema_conforms (shape+FK checks) + deterministic to_prisma/to_sql + coerce/sanitize (1-5 tables, 2-6 fields)
        frontend_gen.py            # per-page LLM (+game 2-file branch) + template list/detail/dashboard + game templates (Board/logic.ts minimax/Scoreboard) + api.ts (full or minimal per contract) + types + App.tsx + barrel + csv.ts/upload.ts conditional emission
        backend_gen.py             # per-table LLM (scores branch) + _template_backend (full CRUD or minimal per contract routes) + openapi from contract
        scaffold_gen.py            # frontend_scaffold (package/vite/tsconfig/index/main/css/env/tailwind/postcss) + backend_scaffold (server/db.py + env + __init__ + README_BACKEND + storage.sql bucket file)
      preview/mock_gen.py          # Dexie db/seed/server/index from contract routes (string UUID ids, FK-aware seeds)
    components/                    # COMPOSABLE ARCHITECTURE foundation (new — see §11)
      registry.py                  # catalog loader/validator (fail-closed aggregate errors)
      composer.py                  # selection → topo order → to_dag() (existing step kinds)
      select.py                    # AppSpec → selections (entity/page/api mapping + export/upload keyword triggers)
      store.py                     # fail-soft wish_components persistence
      catalog/                     # 19 component JSONs + categories.json (10 packs)
    routers/
      wishes.py (735 lines)        # every /wish* endpoint (see §5); MEM cache; RATE (10/day, UNUSED); CHAT_RATE (20/day shared chat+iterate); SSE; single-flight 409
    db/
      wishes.py (160 lines)        # fail-fast Supabase layer: create/get/update/list/promote (see §8)
    utils/json_parse.py            # parse_json (fences, outer braces, trailing commas, truncation repair) + is_quota_error (429/quota/exhausted + tenacity unwrapping)
    data/intara_lore.md
    deps/ (presence unverified — treat as absent)
  supabase/
    schema.sql                     # legacy: schemas + docs vector(1536) + allow-all RLS + match_docs(1536)
    migrations/
      001_intara_wishes.sql        # docs → vector(3072), wishes table + RLS, wish_logs
      002_staged_builds.sql        # current_step_id/build_graph/updated_at, widened statuses, wish_steps + RLS, triggers
      003_wish_messages.sql        # chat turns (insert+read only)
      004_wish_iterations.sql      # diff previews + revert snapshots
      005_component_registry.sql   # component_defs + wish_components (ADDITIVE ONLY)
  tests/ (93 total: 37 components + 6 contract + 4 golden + 29 interactive + 9 llm-fallback + 8 template-gates)
    fixtures/wishes.json           # 5 ideal wishes (tracker/blog/ecommerce/booking/forum)
  scripts/
    eval.py                        # 6 checks (json/schema/tsc-optional/ast+ruff-optional/openapi/cites); --mocked/--live/--wish/--check/--verbose
    seed_components.py             # catalog → component_defs upsert (prefers SUPABASE_SERVICE_KEY, 42501 guidance, --dry-run)
```

---

## 3. Tech Stack

### 3.1 Intara itself (builder)
- **Frontend:** Vite 5 + React 18.3 + TS 5.5 + React Router (6.30.6 nested; root ^7.18.4 skew — nested wins at runtime) + Tailwind + framer-motion + jszip + Sandpack + Dexie + supabase-js 2.45.
- **Backend:** FastAPI 0.110 + google-genai 1.57 + openai SDK (all OpenAI-compatible providers) + Tenacity (retries everything EXCEPT quota) + python-dotenv + httpx. NoCelery/RQ — `BackgroundTasks` + in-memory asyncio queues only.
- **DB:** Supabase Postgres + pgvector `vector(3072)` + RLS (demo-open, see §8) + `match_docs` RPC. Preview uses Dexie IndexedDB. Legacy `schemas` + `vector(1536)` SQL retained for compat.
- **AI:** `generate_content` + `embed_content(gemini-embedding-001)` + cosine RPC. Chain: **Gemini → OpenRouter → Groq → Nvidia → DeepSeek → mock** (see §6.5). Embeddings: OpenRouter only if `OPENROUTER_EMBED_MODEL` set, else Gemini, normalized to 3072d.
- **Hosting (today):** localhost (`:5173` + `:8000`) or Vercel Hobby (FE config present). No hosting for *generated* apps.
- **Quality gates:** tolerant JSON parse + per-call repair, fail-closed blocking gates (tsc + vite + TestClient + contract + game proofs), 93-test suite, golden eval.

### 3.2 Generated apps (output)
- **Frontend:** Vite React 18 + TS + Tailwind + Router + `src/api.ts` (contract-route client fns; full 6-fn or minimal) + `src/mock/*` (Dexie + seeded rows + fetch interceptor) + `src/types.ts` + `src/pages/*` + `src/components/*Card.tsx` + `src/game/logic.ts` (games only: pure rules, zero imports) + `src/lib/csv.ts` / `upload.ts` (only when selected). `npm install && npm run dev` works.
- **Backend:** FastAPI + Pydantic + SQLite default (`server/db.py`, real DDL) + Supabase swap + inline routes in `server/main.py` (no routers/) + `requirements.txt` + `openapi.json` + `storage.sql` bucket file. `pip install -r requirements.txt && uvicorn server.main:app` works with no Supabase.
- **Schema:** `schema.json` + `schema.prisma` + `supabase.sql`. Scroll: `README.md` + `PRD.json` + `openapi.json` + cites.
- **Zip:** `{slug}/frontend/` + `{slug}/backend/` + `README.md` + `PRD.json` + `CITES.md` (see `builds/photovault.zip`: 43 files, PhotoVault example exercising file-upload).

---

## 4. Data Models

### 4.1 PRD (one-shot, `prompts/intara.py` + `services/planner.py`)
```json
{
  "appName": "TaskOrb", "tagline": "...",
  "tables": [{"name": "users", "fields": [{"name": "email", "type": "text"}]}],
  "pages": [{"name": "Dashboard", "route": "/", "components": ["TaskList"]}],
  "apis": [{"method": "GET", "path": "/api/tasks", "desc": "list tasks"}],
  "auth": true,
  "appType": "dashboard", "appKind": "crud", "gameType": null,
  "_meta": {"source": "mock|gemini|openrouter|groq|nvidia|deepseek", "model": "...", "repaired": true}
}
```
Constraints: 1–3 tables requested (sanitized to 1–5 in schema_gen), 2–5 fields, types `text|integer|timestamp|boolean` (+`uuid` in v2 paths), 1–4 pages, 2–6 APIs. `mock_prd()` keyword fixtures (task/blog/ecommerce/booking/forum/recipe/library/hr) else generic keyword-derived fallback. Quota → mock+warning (never raises).

### 4.2 AppSpec / BuildPlan (staged)
Superset of PRD:
- `appType`: catalog|dashboard|marketplace|social|booking|form-wizard|content-management|**game|tool|showcase**
- `appKind`: `crud` (default) | `interactive` (explicit wins, else derived from appType); `gameType`: tictactoe|memory|arcade|custom|null (validated only for games)
- `entities[{name, fields[], relationships[{target,type,fk}], businessRules[]}]` (0–5 crud, 0–2 interactive; board state never DDL)
- `uiPatterns{layout (+board-grid/single-tool/showcase), primaryEntity, listStyle/detailStyle (+none), features[] (+game/tool features)}`
- `requirements{functional[], nonFunctional[], auth, roles[]}`, `ia{entities[], relations[], nav[]}`
- `tables[]` (derived, stripped), `pages[]` (crud pages MUST bind `table`; interactive pages are feature-bound, no table key)
- `buildGraph[{id, kind, ref, dependsOn[], status, promptHint}]`, kinds: schema|backend_table|frontend_page|wiring|validate (+oneshot legacy). Pure-frontend specs skip `schema-foundation`.
- `_components{order, units[{component, config}], warnings, catalog_version}` + `_meta{source, model, analyzer, clarify?, components_warning?}`
- `mock_game_plan()` deterministic TicTacToe shape (scores table, Game+Scores pages, GET+POST scores, 6-node DAG) for game prompts under no-key/quota.

### 4.3 Artifacts (orchestrator final)
```json
{
  "schema": {"tables": [], "prisma": "...", "sql": "..."},
  "frontend": {"files": [{"path": "src/pages/Dashboard.tsx", "content": "..."}]},
  "backend": {"files": [{"path": "server/main.py", "content": "..."}], "requirements": "...", "openapi": {}},
  "preview": {"src/mock/db.ts": "...", "src/mock/seed.ts": "...", "src/mock/server.ts": "...", "src/mock/index.ts": "..."},
  "spec": {"readme": "...", "openapi": {}, "cites": ["..."], "prd": {}},
  "steps": {"schema-foundation": {"status": "done|running|pending|failed"}},
  "buildGraph": []
}
```
NOTE: `wish_steps.output` stores file **paths only** — file contents live in the build process memory. After any restart, resume re-queues content-hollow steps for fresh regeneration (deliberate; see §6.3).

### 4.4 Supabase tables
- `schemas(id, prompt, tables, created_at)` — legacy one-shot compat, RLS allow-all demo.
- `docs(id, content, embedding vector(3072))` + `match_docs(vector(3072), int)` RPC cosine.
- `wishes(id, owner→auth.users SET NULL, prompt, prd, artifacts, status, build_graph, current_step_id, created_at, updated_at)` — status in `planning|awaiting_approval|approved|building|weaving|ready|failed`.
- `wish_steps(id, wish_id CASCADE, step_id, kind, ref, status pending|running|done|failed, attempt, prompt [:20000], raw_response [:20000], output jsonb, error [:2000], depends_on, started_at, ended_at, created_at, updated_at)` — UNIQUE(wish_id, step_id).
- `wish_logs(id, ip, created_at)` — present but the IP rate limiter is NOT wired to any endpoint (see §12.5).
- `wish_messages(id, wish_id CASCADE, role user|agent, content, created_at)` — insert+select only.
- `wish_iterations(id, wish_id CASCADE, step_id, instruction, files_changed[{path,before,after,area}], prev_artifacts, status preview|applied|reverted|discarded, created_at)`.
- `component_defs(id text PK, version, kind entity|page|api|widget|workflow|integration, title, spec jsonb, status stable|experimental|planned, created_at, updated_at)` — seeded mirror of repo catalog JSON.
- `wish_components(id, wish_id CASCADE, component_id →defs RESTRICT, version, config jsonb, status pending|building|done|failed|skipped, created_at, updated_at)`.
- RLS today is **demo-open everywhere**: owners-full (`auth.uid()=owner OR owner IS NULL`) + public-read on all tables; allow-all writes on logs/iterations/messages-insert; `component_defs` is the sole exception (public read, service_role write). Must harden for production (see §12).

---

## 5. API Contracts (FastAPI)

Base: `server/main.py` mounts `routers/wishes.py` at both `/api` and `` (so `/wish` and `/api/wish` both work). CORS `*` today.

| Method & Path | Body | Returns | Notes |
|---|---|---|---|
| `POST /generate`, `POST /api/generate` | `{prompt}` | `{tables[]}` | Legacy schema-only; `call_llm` then `call_gemini` fallback; repair pass; optional `schemas` insert |
| `POST /rag`, `POST /api/rag` | `{question}` | `{answer, cites[]}` | Via `rag.answer()` |
| `GET /health`, `GET /api/health` | — | `{ok, model, supabase, planet:"intara", llm:{...}}` | Per-provider configured/model/cooldown + OpenRouter quota + `primary/order/only` |
| `GET /api/wishes/health` | — | `{ok, wishes:true}` | Liveness (no dependencies) |
| `POST /wish`, `POST /wishes` | `{prompt: 4..500}` | full wish | Legacy one-shot `plan_wish + assemble`; MEM + Supabase (fallback `schemas`) |
| `POST /wish/plan` → **202** | `{prompt, answers?, skip_clarify?}` | shell wish (`planning`) | Sync shell insert only (no LLM); background `_run_plan_task`; fail-fast 500 without Supabase |
| `PATCH /wish/{wid}/plan` | `{prd}` | wish `awaiting_approval` | Validates appName+tables; backfills buildGraph/requirements/ia; resets steps |
| `POST /wish/{wid}/answer` | `{answers}` | wish `awaiting_approval` | Only from `planning`; redraft + `plan_build` + step reset; records composition |
| `GET /wish/{wid}/suggest` | — | `{suggestions[{label,detail,prompt_suffix}]}` | Deterministic, no LLM |
| `GET /wish/{wid}/chat` | — | `{messages[]}` | DB + MEM fallback |
| `POST /wish/{wid}/chat` | `{message: 1..1000}` | `{reply, actions[], degraded?}` | Shared 20/day IP cap; fail-open degraded replies; never 429s to UI |
| `POST /wish/{wid}/iterate` | `{instruction: 1..500, stepId?}` | `{iteration_id, step_id, files[{path,before,after}], summary}` | Shared 20/day cap; step resolution; persists nothing until apply |
| `POST /wish/{wid}/iterate/{iid}/apply` | — | fresh wish | No LLM; snapshot + patch + step bump; idempotent |
| `POST /wish/{wid}/iterate/{iid}/revert` | — | fresh wish | No LLM; snapshot restore |
| `POST /wish/{wid}/approve` | — | `{ok, status:"building"}` | Only from `awaiting_approval/approved/failed`; sets `building`, enqueues build task |
| `GET /wish/{wid}/stream` | SSE | snapshot + live events + heartbeat | Snapshot `{steps,status,plan_phase,current_step,updated_at}`; breaks on done/failed/plan events; 2s DB-poll fallback |
| `POST /wish/{wid}/retry` | `{stepId}` | `{ok, retrying}` | 404 unknown step; **409 if a build task is already running**; resets pending/attempt+1, resumes |
| `GET /wish/{wid}`, `GET /wishes/{wid}` | — | full wish | DB first, MEM fallback |
| `GET /wishes` | — | `[...]` max 50 desc | DB + MEM merge deduped; legacy `schemas` fallback if unmigrated |
| `POST /wish/{wid}/regenerate` | — | new wish | One-shot re-run of same prompt |

Frontend client mirrors all in `api/client.ts`. `createPlan()` 150s AbortController → `PlanAbortedError` (friendly) + `reconcileWish()` (same prompt, <3min, newest). `streamBuild()` EventSource + 2s `useWish` polling (90 attempts max, 8s busy indicator).

Rate limits: `RATE` 10/day exists but is **not wired to any endpoint**; the enforced caps are `CHAT_RATE` 20/day/IP shared by chat+iterate.

---

## 6. Generation Pipeline (detail for planner)

### 6.1 Clarify-first (`services/prompt_enhance.py`)
- `score_prompt()`: 45 base + detail + entity density (cap 20) + action/data/audience/constraint signals. Clamp 5..98 → `{score, aspects, missing}`.
- `clarify_prompt()`: 1 small LLM call (temp 0.3) for `{score, questions[{id,q,options[{label,desc}]}]}` (max 3×3, validated); fallback domain templates (audience + opponent/commerce/social/scope + data). Never raises 429.
- `redraft_prompt()`: folds answers as `"Q Answer: label."` sentences, cap 2000 chars.

### 6.2 Plan (`services/planner.py`, `planner_v2.py`, `services/analyzer.py`)
- `mock_prd()`: keyword fixtures (task/blog/ecommerce/booking/forum/recipe/library/hr) + generic keyword-derived fallback. Always valid.
- `plan_wish()` (legacy): `has_any_llm` else mock; LLM + repair; quota → mock+warning (never raises).
- `analyze_prompt()`: LLM AppSpec → tolerant parse → `_validate_app_spec` (appKind/gameType/snake_case/FK/page bindings; crud pages must bind) → derive tables/entities → bind crud pages only → `_compose_or_legacy_dag` → requirements/ia → `_meta`. No-key/quota/generic-failure → mock paths, all composition-attempted.
- `plan_build()`: analyzer-first; legacy `BUILD_PLAN_PROMPT` fallback (crud table-binding guards); mock fallback.
- `mock_build_plan()` + `mock_game_plan()`: deterministic enrichment (requirements/ia/entities/DAG).

### 6.3 Generators + orchestrator
- **Schema:** LLM-first (game prompt branch for interactive) + `_schema_conforms` (table coverage + `{name,type}` shape + FK-in-sql/prisma) else deterministic `to_prisma/to_sql` + coerce/sanitize (1–5 tables, ≤6 fields, pad to 2, string fields inferred). Malformed LLM field shapes are *rejected*, not coerced, at this layer.
- **Frontend:** per-page LLM (crud 1-file / game 2-file page+logic.ts; import-free logic enforced, multi-file dedupe) + repair-on-TSX-error once; template fallback (list/detail/dashboard + game Board/Scoreboard/logic.ts-minimax). `api.ts` full-6-fn or minimal per contract routes; `src/lib/csv.ts` + `upload.ts` emitted iff selected (guaranteed even on all-LLM page sets); `App.tsx` + barrel always deterministic-regenerated.
- **Backend:** per-table LLM (scores branch for interactive) + contract-conformance filter; `_template_backend` full CRUD or minimal per declared routes; openapi derived from contract.
- **Scaffold:** static FE shell + BE `server/db.py` (real DDL exec) + `storage.sql` bucket file + README_BACKEND (incl. `__INTARA_ENV__` upload wiring docs).
- **Mock:** Dexie stores/seeds/fetch-interceptor **driven off contract routes** (not hardcoded CRUD); string UUID ids; FK-aware seeds.
- **Orchestrator `run_build_sequential()`:** canonical plan from DB; BUILD_STATE + SSE emit + `BUILD_RUNNING` single-flight set; **resume re-queues content-hollow steps** (DB stores paths, not contents); per-step thread + **600s watchdog** (`STEP_TIMEOUT_SECONDS`); persist running→work→done/failed (fail-fast on DB errors); validate node = light checks + template-only regen + contract checks + tsc/vite + TestClient matrix + one LLM repair + re-gate; **fail-closed** (`_mark_build_failed` flips DB+MEM+SSE — wishes never stick on `building`); final assembly refuses empty content, persists `ready` unconditionally via DB layer.
- **Assembler** (legacy one-shot path only): same generators + merge/dedupe + README/cites.

### 6.4 Validator (`services/validator.py`)
- `validate_tsx`: default export **only for `/pages/*.tsx`** (components/barrel exempt), brace balance, double-brace heuristic (`={{!` / `={{bare-ident}}`). **Deliberately esbuild-free**: per-file bundling cannot resolve bare imports outside a project dir, so it red-flagged every valid file (verified) — real typechecking lives in gates.
- `validate_python`: `ast.parse`. `validate_imports_consistency`: frontend `fetch(/api/X)` ⇒ backend route must exist (one-way).

### 6.5 LLM provider (`services/llm.py`)
Order: **Gemini → OpenRouter → Groq → Nvidia → DeepSeek → mock**. `call_llm()` / `call_llm_with_meta()` (returns `(text, {source,model})`) fall through until all exhausted; quota hits get 60s cooldowns (`LLM_COOLDOWN_SECONDS`) then auto-retry; 429 raised only when all exhausted; unconfigured error when no keys at all. `LLM_ONLY` (e.g. `gemini`, comma lists) constrains the chain; unknown names match nothing. `has_any_llm()` respects it. Timeouts: OpenRouter/Groq/DeepSeek 30s, Gemini 60s (`http_options`, plain fallback), Nvidia 120s (`NVIDIA_TIMEOUT_SECONDS`; Nemotron thinking config + reasoning passthrough + streaming support + `call_nvidia_vision` Kimi helper). `embed_texts()` OpenRouter-only-if-model-set else Gemini, 3072d normalized. `get_llm_status()` per-provider configured/model/cooldown + OpenRouter quota via httpx + `primary/order/only`.
- **Known gap (deferred, approved): JSON-mode overhaul** — generation uses plain chat completions (no `response_format`/`responseMimeType`), the parser lacks escape/control-char tolerance, and parse failures get no repair call. Measured consequence: a full Gemini build showed 21 failed LLM attempts / 0 parse successes (all template fallbacks). Plan approved: native JSON mode everywhere + tolerant parsing + 1 parse-error repair.

### 6.6 RAG (`server/rag.py`)
`chunk(400/50)` → `embed_texts` → `match_docs` RPC top-5 (3072→1536→table fallbacks) → `call_llm` synthesize + `cites[:120]`. Demo mode without Supabase/LLM. `seed_docs()` 7 texts.

### 6.7 JSON/quota utils
`parse_json` (fences, outer braces, trailing commas, truncation repair); `is_quota_error` (429/quota/exhausted + tenacity unwrapping). `call_gemini` tenacity 3× exponential, skipping quota errors.

---

## 7. Frontend (builder UI) Detail

- **Routes:** `/` Landing, `/wish/:id` WishVault, `/constellation`, `/archives`. Layout wrapper; lazy routes with spinner fallback; ErrorBoundary per pane.
- **Landing:** hero (mock-aware clarity copy), PlanetOrb, 8 example chips (4 shown), live wish count (Supabase w/ silent fallback), staged/one-shot toggle, WishInput (NOT debounced — immediate), weave → nav with abort-reconcile, Pillars/HowItWorks, lore, RAG box.
- **WishVault:** `useWish` + refresh; weaving spinner; legacy classic vault when ready without buildGraph; else Studio shell (drag-resizable chat column 280–720px, collapsible rail/chat). `BuildingView`: DAG pills, per-step rows (dot, kind·ref·duration, status, working Retry with error display), progress + elapsed, **live activity feed** (last 8 events, all event types labeled), live/polling badge, no full-page reloads on finish.
- **AgentThread:** clarity score card, clarify Q&A cards, 3-phase PlanProgress stepper (clarifying/drafting_tables/drafting_pages), plan summary + approve, WhatIDid, zip/regenerate, suggestion chips (fork), failed-state retry, plus always-on ChatThread (history, optimistic send, 1000-char cap, retry/fork/**fix** chips, diff preview with before/after panes, apply/revert, day budget display).
- **ArtifactVault:** 5 tabs + copy/zip/share. **PreviewTrial:** Sandpack instant + IndexedDB sidebar + local-persist banner. **StudioPreview:** Preview/Code modes, file explorer w/ search, build logs. **Constellation:** hash-positioned star SVG + filterable list (Supabase w/ API fallback). **Theme:** CSS variables + studio grid + diff/codeview styles.

---

## 8. DB & Migrations Detail

- Apply order in Supabase SQL editor: `schema.sql` → `001` → `002` → `003` → `004` → `005`. Seed: `python -c "from rag import seed_docs; seed_docs()"` + `python scripts/seed_components.py` (needs `SUPABASE_SERVICE_KEY`; `--dry-run` safe).
- `schema.sql`: legacy only (stale 1536 dim, allow-all RLS).
- `001`: 3072 dim + `wishes` + `wish_logs` + RLS (owners-full + demo reads).
- `002`: staged columns/statuses, `wish_steps` + RLS + triggers + backfill.
- `003`: `wish_messages` (insert+select only).
- `004`: `wish_iterations` (preview/applied/reverted/discarded).
- `005`: `component_defs` + `wish_components` — **ADDITIVE ONLY** (no ALTER/DROP/DELETE of existing objects; verified by test).
- `db/wishes.py` caps: prompt/raw 20k, error 2k. All writes raise on no-data (fail-fast, no silent MEM).

---

## 9. Env & Run

**Backend `server/.env.example`:** `DEEPSEEK_API_KEY/MODEL`, `GROQ_API_KEY/MODEL`, `NVIDIA_API_KEY/MODEL` (+vision note), `GEMINI_API_KEY/MODEL=gemini-3.6-flash`, `SUPABASE_URL/KEY (service-role)`, `OPENROUTER_API_KEY/MODEL/FALLBACK (=openrouter/free placeholder — VERIFY a real free model id before relying on it)`, `OPENROUTER_EMBED_MODEL=` (empty), `LLM_COOLDOWN_SECONDS`, `LLM_ONLY`. Without keys: deterministic mock + MEM + fallback cites; benchmark still passes. Runtime note: live `server/.env` may pin `LLM_ONLY` — check before assuming full-chain behavior.

**Frontend `.env.example`:** `VITE_SUPABASE_URL/ANON_KEY` (+ demo fallback), `VITE_API_URL` (currently unused — client uses relative `/api` + proxy).

**Quickstart:**
```bash
cd react-prompt-app && npm install && cp .env.example .env && npm run dev  # :5173
cd ../server && pip install -r requirements.txt && cp .env.example .env && uvicorn main:app --port 8000  # :8000/docs
# Supabase once: schema.sql → 001..005; seed docs + components (scripts/seed_components.py needs service key)
```

**Benchmark:**
```bash
python scripts/eval.py --mocked --verbose   # 5 wishes × 6 checks (tsc/ruff soft-skip if missing)
pytest tests/ -v                            # 93 tests across 6 files (see §10)
```

**Ops notes (earned the hard way):**
- Run the backend as a **single process, no `--reload`** in dev-loop-with-builds: reloader fork trees + orphaned `multiprocessing.spawn_main` children inherit the listen socket and steal connections (requests hang with no error). Kill by port holder (`lsof -iTCP:8000`), not just by `uvicorn` cmdline match.
- Backend log to a repo-local file (e.g. `server/backend.log`, untracked noise) — `/tmp` gets purged and takes diagnostics with it.
- Killing a build mid-step orphans its `running` row; resume via retry (hollow steps regenerate) or mark `failed`.

---

## 10. Tests (93 total)

| File | Count | Covers |
|---|---|---|
| `test_components.py` | 37 | Catalog validity, packs vs analyzer taxonomy, stable-generator metadata, composer (order/conflicts/cycles/determinism/DAG shape), select mapping + keyword triggers, store rows, seed credentials/errors, csv-export + file-upload emission/scoping/gates |
| `test_contract.py` | 6 | Path canon, FK schema, backend/frontend template conformance, scaffold closure, mock string IDs |
| `test_golden_wishes.py` | 4 | All-5/individual/type-allowlist/has-pages over fixtures |
| `test_interactive.py` | 29 | Minimal contracts, backendless exemption, game gates green/red/skip/import-reject, analyzer game validation, mock game shape, graph variants, prompt directives, game templates, mock/BE-matrix enforcement |
| `test_llm_fallback.py` | 9 | Order/fallback/cooldown/reuse/expiry, with_meta source, has_any_llm, status shape, planner mock-warning, LLM_ONLY pin + unknown-disable (env-isolated) |
| `test_template_gates.py` | 8 | Single-brace checkbox, double-wrap detection + valid-pattern negatives, template brace-clean, backend compiles, contract pass, no-node validation |

Plus `scripts/eval.py` (6 checks × 5 fixtures) and `scripts/seed_components.py --dry-run` (catalog/DB shape check).

---

## 11. Component Architecture (new foundation)

Rationale (from user): stop depending on fully-arbitrary generation; compose vetted building blocks per category, extendable over time. Status: foundation shipped (registry + composer + selection + persistence + 19 seeded defs); Analyzer emits selections and DAGs from them; generators consume composition for csv-export/file-upload; Studio does not yet visualize composition (phase 4).

- **Catalog** (`server/components/catalog/*.json`, 19 entries + `categories.json` v1.0.0):
  - Entities (stable): `crud-entity`, `auth-users`, `scores-table`, `booking-slot`
  - Pages (stable): `list-page`, `detail-page`, `dashboard-page`, `game-board`, `scores-list`; (experimental): `auth-pages`
  - APIs (stable): `crud-api`, `scores-api`; (experimental): `search-api`
  - Widgets (stable): `stat-cards`; (experimental): `kanban-board`; (planned): `charts`
  - Workflows (stable): `csv-export`; (planned): none left (csv done)
  - Integrations (stable): `file-upload`; (experimental): `supabase-auth`; (planned): none left — add storage/billing here next
  - Packs cover all 10 analyzer appTypes; `game` = scores-table + game-board + scores-list + scores-api; `tool` = game-board; `showcase` = [] (pure static, no build units beyond wiring/validate)
- **Lifecycle:** `planned` = unselectable (loud error, never silent); `experimental` = selectable with warning; `stable` = generators + gates exist. Promotion path: JSON + generator + gates + tests.
- **Registry** (`registry.py`): fail-closed load/validate (semver, kinds, dangling refs, param schemas with defaults); `pack_for_category`, `check_params`, `get_component`.
- **Composer** (`composer.py`): repeated-component instances (one unit per table/page), transitive requires (must be satisfiable, else error), symmetric conflicts, cycle detection, first-selection-order deterministic emission (matches legacy DAG shape — guarded by test), unique DAG ids (DB constraint), api/widget/workflow/integration fold into host nodes (`via`, dedicated kinds = phase 4).
- **Select** (`select.py`, pure): table→entity (+auth-users/scores-table), bound page→list/detail (+stat-cards for dashboard `/`), feature page→game-board/scores-list (unknown → warning, never forced), entity→api, keyword triggers (`export/csv/…` → csv-export per table; `upload/attach/image/…` word-boundaried → file-upload per table).
- **Store** (`store.py`): `rows_for_wish` (pure) + `record_wish_composition` (delete+insert, fail-soft, works on publishable key for ownerless wishes); called after plan-promote and after clarify-answers (not on manual plan-patch — user edits own the PRD there).
- **Live proof:** PhotoVault wish composes 19 units incl. 4× file-upload; `builds/photovault.zip` is a checked-in deterministic build exercising it.

---

## 12. Gaps & Constraints (planning agent: start here)

1. **JSON-mode overhaul (approved, deferred):** generation uses plain chat completions; no `response_format`/`responseMimeType`; parser lacks escape/control tolerance; parse failures get no repair. Measured: 21 failed LLM attempts / 0 parse successes on a full Gemini build. Plan: native JSON mode per provider (auto-fallback) + tolerant parsing + 1 parse-error repair + max_tokens on big calls + `fallback_reason` in step output.
2. **No hosted generated apps:** zip + Sandpack trial only. Need Preview → Deploy (Vercel FE + Render/Fly BE + per-customer Supabase) → URLs/domains/env.
3. **Auth/tenancy demo-grade:** CORS `*`, public-read RLS everywhere, unenforced `RATE` limiter, no orgs/roles/audit, generated backends without auth middleware, DDL without owner columns/policies.
4. **Reliability/ops:** in-process `BackgroundTasks` + asyncio queues (single-flight only); tombstoned `running` rows after kills need retry/requeue (exists) — consider a startup sweeper; no metrics/traces/billing; log to file (do not rely on `/tmp`).
5. **Expressiveness (shrinking via components):** knon gaps now tracked as `planned` catalog entries, but still missing: roles/permissions, email/SMS/WhatsApp, Stripe billing, calendar view, full-text search backend, charts (dep surgery needed: conditional recharts), multi-table wizards, realtime/cron/storage-adapters beyond the uploads bucket file.
6. **UX for non-tech:** Studio is dev-flavored (code tabs, DAG pills); needs plain-language mode, template gallery, guided setup, hosted-app dashboard. `showcase` pack is empty — landing/portfolio generation unimplemented.
7. **Security/compliance:** length-only validation, no prompt-injection guard, no PII handling, no SOC2/GDPR story.
8. **Commercial:** no teams/billing/support/SLA/data-residency.
9. **Known debt register:** root `package.json` vs nested react-router skew (6.30.6 wins); `VITE_API_URL` unused; `src/data/` empty; `TableExplorer.tsx` referenced in old docs but absent; `frontend_gen_new.py` referenced in the oldest spec but does not exist and is unreferenced anywhere; `server/deps/` exists but is empty; legacy `/generate` + one-shot `/wish` paths retained for compat; `server/deps/` status unverified; game track covers tic-tac-toe rules only (`custom`/`memory`/`arcade` skip gates); `mock_game_plan`/`GAME_WORDS` keyword routing is brittle by design.

**Non-goals (unless user asks):** multi-stack generation (locked stack), realtime collab, heavy 3D/WebGL, full HumanEval, Docker sandbox preview (prefer WebContainers/browser), `facebook/…` providers.

---

## 13. Instructions to Planning Agent + doc hygiene

1. **Read** this file, then `server/components/catalog/` (ground truth for extensibility), then code for anything load-bearing.
2. **Propose** phased roadmaps with concrete file-level changes, migrations, tests, and verification commands. Preserve §11 component statuses (never silently use `planned`).
3. **Constraints to respect:** fail-closed gates, fail-soft composition/persistence, deterministic templates byte-stable (golden tests depend on it), DB additive-only unless user explicitly authorizes clears, RLS posture changes called out explicitly.
4. **Verify** with `pytest tests/ -v` (93 green baseline), `scripts/eval.py --mocked`, and `tsc --noEmit` in `react-prompt-app/` for frontend changes.
5. **Stale-doc policy:** `README.md`, `architecture.md`, `docs/INTARA_SCOPE.md`, and `docs/BENCHMARK.md` contain pre-staged-pipeline claims (enumerated in the audit of record: deploy promises, 4-tab vault, 350ms debounce, 35s abort, TableExplorer, pytest 4/4). Treat them as historical unless re-verified; this file supersedes them on conflicts.

---

*End of spec — rewritten from live codebase inspection (93 tests, eval 5/5). If code and this file disagree, trust code and update this file.*
