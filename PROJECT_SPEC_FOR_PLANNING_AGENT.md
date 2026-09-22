# INTARA — Planet of Wishes — Full Project Specification for Planning Agent

> **Purpose of this file:** Give a downstream planning AI agent complete, self-contained context about the current codebase so it can produce a further build/roadmap plan — especially to evolve this into a **production-grade, professional product for small non-tech businesses to build internal / custom software tools**.
> **How to use:** Read this file top-to-bottom before proposing any plan. All paths are relative to repo root `/`. Do not assume anything not stated here — inspect code if unsure.

---

## 1. Project Identity

- **Name:** Intara — Planet of Wishes
- **Tagline:** "Make a software wish come true — describe any app, Intara weaves schemas, frontend, backend, and specs as stardust."
- **Theme:** Fictional planet Intara, 3.7 light years away — obsidian oceans, violet auroras. Dark nebula glass UI (`#0a0a12`, `#8B5CF6`, glass `rgba(255,255,255,0.06)`). Fonts: Space Grotesk (display), Inter (body), JetBrains Mono (code). See `docs/INTARA_SCOPE.md`, `server/data/intara_lore.md`.
- **Positioning:** Miniature Rocket.new / Lovable / Bolt clone, but themed, opinionated, locked-stack, free-tier runnable. Built for portfolio + internship demos, 5 golden wishes 100% pass.
- **Current version:** v1.1 — runnable + trial, free-tier $0. **Not yet:** no deploy, no GitHub push, no chat-to-refine (see §12).

**Core promise today:**
```
Wish text --(Intara)--> PRD --> { Schemas, Frontend, Backend, Scroll } --> Zip + Share + Browser Trial
                      └─ RAG (pgvector 3072d) → cites + groundedness
```

---

## 2. Monorepo Layout

```
/
  README.md                        # user-facing overview, quickstart, benchmark, loom script
  architecture.md                  # 10-min whiteboard: prompt->Gemini->FastAPI->Supabase->Vercel
  implementation.md                # fix plan: 8 issues, ~60 lines across 7 files
  LOOM.md                          # 60-sec demo script
  docs/
    INTARA_SCOPE.md                # theme bible + 4 artifacts spec + routes + data model + flow
    BENCHMARK.md                   # 5 golden wishes, 6 checks, HumanEval/MBPP adaptation
  react-prompt-app/                # Intara shell frontend (the builder UI itself)
    package.json                   # vite 5, react 18, react-router 6, sandpack-react, dexie, supabase-js, jszip
    vite.config.ts                 # port 5173, /api proxy -> localhost:8000 (rewrite strips /api)
    vercel.json
    src/
      App.tsx                      # router shell + lazy WishVault/Constellation/Archives
      main.tsx
      supabase.ts
      api.ts / api/client.ts       # createWish, createPlan, patchPlan, approvePlan, answerClarify, getSuggest, streamBuild (SSE), retryStep, getWish, listWishes, askRag
      pages/
        Landing.tsx                # hero + PlanetOrb + WishInput + staged/one-shot toggle + RAG ask + lore
        WishVault.tsx              # legacy vault (weaving/ready without buildGraph) + staged Studio (rail+thread+preview+BuildingView DAG)
        Constellation.tsx          # history star map (hash id -> position) + list/filter
        Archives.tsx               # RAG ask docs
      components/
        Layout.tsx, Header.tsx, PlanetOrb.tsx, WishInput.tsx
        ArtifactVault.tsx          # 5 tabs: Trial / Schemas / Frontend / Backend / Scroll + copy/zip/share
        PreviewTrial.tsx           # Sandpack instant iframe + IndexedDB explorer + create form
        TableExplorer.tsx (if present)
        AgentThread.tsx            # staged chat thread (clarify Q&A, plan approval, build events)
        StudioRail.tsx, StudioPreview.tsx, RocketSections.tsx
      lib/
        zip.ts                     # buildWishZip: {slug}/frontend + {slug}/backend + README + PRD.json + CITES.md
        sandpack.ts                # toSandpackFiles: frontend files -> Sandpack format
        hash.ts
      hooks/
        useWish.ts, useAuth.ts, useReveal.ts
      theme/intara.css
      public/assets/               # planet-intara.png, starfield, wish-orb, constellation, nebula-gradient, glyphs/*
  server/                          # FastAPI Planet core (the builder backend)
    main.py                        # 116 lines: CORS *, /generate, /rag, /health, mounts routers/wishes
    requirements.txt               # fastapi 0.110.1, uvicorn 0.29, supabase 2.31, google-genai 1.57, openai>=1.40, tenacity, pydantic, httpx
    .env.example                   # DEEPSEEK_*, GROQ_*, NVIDIA_*, GEMINI_*, SUPABASE_*, OPENROUTER_* (see §9)
    prompts/
      intara.py                    # INTARA_PLANNER_PROMPT: appName/tagline/tables/pages/apis/auth, 1-3 tables
      analyzer.py                  # ANALYZER_SYSTEM_PROMPT: AppSpec with appType taxonomy, entities+relationships, UI patterns, requirements, ia
      build_plan.py                # BUILD_PLAN_PROMPT (legacy v2 path)
      frontend_page.py / frontend_page_v2.py
      backend_table.py / backend_table_v2.py
      schema_v2.py
    services/
      planner.py                   # plan_wish(): mock_prd (task/blog/ecommerce/booking/forum/recipe/library/hr/generic) + LLM guarded + repair + quota detect
      planner_v2.py                # plan_build(): analyzer-first, fallback mock_build_plan() enriching to requirements/ia/buildGraph DAG
      analyzer.py                  # analyze_prompt(): single LLM -> AppSpec, validate snake_case/FK/page-table, derive tables/buildGraph, quota->mock with warning
      prompt_enhance.py            # score_prompt() deterministic 5..98 + clarify_prompt() LLM-first Q&A (max 3 Q, 3 options) + redraft_prompt(); READY_THRESHOLD=70
      suggest.py                   # suggest_next(): deterministic domain rules (game/shop/social/booking/task/recipe) + generic fillers, prompt_suffix for v2 fork
      llm.py                       # provider chain: DeepSeek -> Nvidia Kimi -> Groq -> OpenRouter -> Gemini; embed_texts() 3072d norm; get_llm_status()
      generators/
        schema_gen.py              # LLM-first if entities else deterministic to_prisma()/to_sql() with FK map; sanitize 1-5 tables, 2-6 fields
        frontend_gen.py            # generate_frontend(): api.ts + types.ts + per-page LLM (frontend_page_v2 + validate_tsx + repair) else template list/detail/dashboard + Card components + App.tsx + barrel
        frontend_gen_new.py        # (variant, check before using)
        backend_gen.py             # generate_backend(): per-table LLM (backend_table_v2 + validate_python + repair) else template models.py/main.py(SQLite+Supabase)/routers/requirements/openapi
        scaffold_gen.py            # frontend_scaffold(appName): package.json/vite.config/tsconfig/index.html/main.tsx/index.css/.env.example/tailwind; backend_scaffold(): db.py(SQLite+Supabase adapter)+server/db.py/README_BACKEND.md
      preview/mock_gen.py          # generate_mock(): src/mock/db.ts (Dexie stores) + seed.ts (3 rows/table FK-aware) + server.ts (fetch interceptor for /api/* CRUD) + index.ts
      assembler.py                 # assemble(prd,prompt): schema+frontend+backend+scaffold+mock -> README + cites (RAG or fallback) + dedupe + {schema,frontend,backend,preview,spec}
      orchestrator.py              # run_build_sequential(): schema -> per-table backend -> per-page frontend -> wiring -> validate; BUILD_STATE + SSE_QUEUES, emit(), resume from DB, persist_step(), final merge + App.tsx regen + README + cites
      validator.py                 # validate_tsx() (default-export check + brace balance + esbuild bundle), validate_python() (ast.parse), validate_imports_consistency() (fetch /api/* vs backend routes)
    routers/
      wishes.py                    # MEM={} + RATE={} (10/day/IP in-mem); make_wish() one-shot; make_plan() clarify-first; _run_staged_build(); POST /wish/plan, PATCH /wish/{wid}/plan, POST /wish/{wid}/answer, GET /wish/{wid}/suggest, POST /wish/{wid}/approve, GET /wish/{wid}/stream (SSE), POST /wish/{wid}/retry, POST /wish, GET /wish/{wid}, GET /wishes, POST /wish/{wid}/regenerate
    db/
      wishes.py                    # Supabase source of truth fail-fast: _client(), create_wish_tx(), get_wish_with_steps(), update_step(), set_wish_status(), list_wishes_with_steps(), get_steps()
    utils/json_parse.py            # parse_json() (strip ```json, regex braces, trailing-comma fix, truncation repair) + is_quota_error() (429/quota/exhausted incl. tenacity wrapping)
    rag.py                         # chunk(size 400, overlap 50), embed() via llm.embed_texts + Gemini fallback, answer(question, top_k=5) via match_docs RPC + synthesize, seed_docs()
    data/intara_lore.md
    db/ (generated backend adapter example, if present)
    deps/ (if present)
  supabase/
    schema.sql                     # legacy: schemas table + docs vector(1536) + allow-all RLS + match_docs(1536)
    migrations/
      001_intara_wishes.sql        # fix docs -> vector(3072), recreate match_docs(3072), wishes table (weaving/ready/failed) + RLS (owners full + public read demo) + wish_logs
      002_staged_builds.sql        # ensure wishes, add current_step_id/build_graph/updated_at, widen status (planning/awaiting_approval/approved/building/weaving/ready/failed), wish_steps table (step_id/kind/ref/status/attempt/prompt/raw_response/output/error/depends_on) + RLS + triggers + backfill + docs dim fix
  tests/
    test_golden_wishes.py          # 4 tests: all pass, each individually, types allowed, has pages
    fixtures/wishes.json           # 5 ideal wishes (task tracker, blog, ecommerce, booking, forum) with prd + artifacts
  scripts/eval.py                  # check_json_valid, check_schema (1-3 tables 2-5 fields), check_fe_build (tsc), check_be_parse (ast+ruff), check_openapi, check_cites; --mocked/--live/--wish/--check/--verbose
  assets/ASSET_PROMPTS.md + *.png
  example-pages/*.png (screenshots)
```

---

## 3. Tech Stack

### 3.1 Intara itself (builder)
- **Frontend:** Vite 5 + React 18 + TypeScript + React Router 6 + Tailwind (glass) + framer-motion + jszip + Sandpack (`@codesandbox/sandpack-react`) + Dexie + `@supabase/supabase-js`.
- **Backend:** FastAPI 0.110 + `google-genai` (Gemini 3.6-flash default) + `openai` SDK for OpenAI-compatible providers + Tenacity retry + SQLAlchemy (generated backends) + python-dotenv + httpx.
- **DB:** Supabase Postgres + `pgvector` `vector(3072)` + RLS + RPC `match_docs(query_embedding vector(3072), match_count int)`. Preview uses Dexie IndexedDB (no Supabase). Legacy `schemas` + `docs vector(1536)` kept for compat.
- **AI:** `generate_content` (PRD/AppSpec/pages/tables) + `embed_content` (`gemini-embedding-001`, 3072d) + Supabase `vector <=>`, cites 120 chars. Provider priority: `DEEPSEEK_API_KEY` -> `NVIDIA_API_KEY` -> `GROQ_API_KEY` -> `OPENROUTER_API_KEY` -> `GEMINI_API_KEY` -> mock. See `server/services/llm.py:135,205`, `server/.env.example`.
- **Hosting (today):** Vercel Hobby (FE) + Render Free or localhost (BE, `vite.config.ts:7` proxy). No hosting for *generated* apps.
- **Quality gates:** `parse_json` guard + repair prompt, 429 retry, `tsc --noEmit`, `ruff`/`ast.parse`, openapi validator, benchmark suite.

### 3.2 Generated apps (output)
- **Frontend:** Vite + React 18 + TS + Tailwind + Router + `src/api.ts` (mock vs supabase switch) + `src/mock/*` (Dexie trial) + `src/types.ts` + `src/pages/*.tsx` + `src/components/*Card.tsx`. `npm install && npm run dev` works.
- **Backend:** FastAPI + Pydantic + SQLite default via `db.py` (SQLAlchemy) + Supabase swap via `SUPABASE_URL/KEY` + `server/routers/*.py` + `requirements.txt` (+sqlalchemy) + `openapi.json`. `pip install -r requirements.txt && uvicorn main:app` works with no Supabase.
- **Schema:** `schema.json` + `schema.prisma` + `supabase.sql` + Mermaid ER (in UI).
- **Spec/Scroll:** `README.md` (how to run) + `PRD.json` + `openapi.json` + cites from archives.
- **Zip:** Split runnable `{slug}/frontend/` + `{slug}/backend/` + `README.md` + `PRD.json` + `CITES.md`. No config needed; swap to Supabase via `VITE_API_MODE=supabase` + `SUPABASE_URL` (no regen).

---

## 4. Data Models

### 4.1 PRD (one-shot, `prompts/intara.py`, `services/planner.py`)
```json
{
  "appName": "TaskOrb",
  "tagline": "...",
  "tables": [{"name": "users", "fields": [{"name": "email", "type": "text"}]}],
  "pages": [{"name": "Dashboard", "route": "/", "components": ["TaskList"]}],
  "apis": [{"method": "GET", "path": "/api/tasks", "desc": "list tasks"}],
  "auth": true,
  "_meta": {"source": "mock|deepseek|nvidia|groq|openrouter|gemini", "model": "...", "repaired": true}
}
```
Constraints: 1-3 tables (sanitized to 1-5 in schema_gen), 2-5 fields each, types `text|integer|timestamp|boolean` (+`uuid` in v2 paths), 1-4 pages, 2-6 APIs.

### 4.2 AppSpec / BuildPlan (staged, `prompts/analyzer.py`, `services/analyzer.py`, `services/planner_v2.py`)
Superset of PRD:
- `appType`: catalog|dashboard|marketplace|social|booking|form-wizard|content-management
- `entities[{name, fields[], relationships[{target,type:belongs_to|has_many,fk}], businessRules[]}]`
- `uiPatterns{layout, primaryEntity, listStyle, detailStyle, features[]}`
- `requirements{functional[5-10 "As a..."], nonFunctional[2-4], auth, roles[]}`
- `ia{entities[], relations[], nav[]}`
- `tables[]` (derived from entities, stripped for compat)
- `buildGraph[{id, kind:schema|backend_table|frontend_page|wiring|validate, ref, dependsOn[], status, promptHint}]`
  - Always: `schema-foundation` -> `backend-<table>` x N + `frontend-<Page>` x M -> `wiring` -> `validate`.

### 4.3 Artifacts (`services/assembler.py`, `services/orchestrator.py` final)
```json
{
  "schema": {"tables": [], "prisma": "...", "sql": "..."},
  "frontend": {"files": [{"path": "src/pages/Dashboard.tsx", "content": "..."}]},
  "backend": {"files": [{"path": "server/main.py", "content": "..."}], "requirements": "...", "openapi": {}},
  "preview": {"src/mock/db.ts": "...", "src/mock/seed.ts": "...", "src/mock/server.ts": "..."},
  "spec": {"readme": "...", "openapi": {}, "cites": ["..."], "prd": {}},
  "steps": {"schema-foundation": {"status": "done|running|pending|failed"}},
  "buildGraph": []
}
```

### 4.4 Supabase tables
- `schemas(id uuid, prompt text, tables jsonb, created_at)` — legacy one-shot compat, RLS allow-all demo.
- `docs(id uuid, content text, embedding vector(3072))` + `match_docs()` RPC cosine.
- `wishes(id uuid, owner uuid->auth.users, prompt text, prd jsonb, artifacts jsonb, status text, build_graph jsonb, current_step_id text, created_at, updated_at)` — status in `planning|awaiting_approval|approved|building|weaving|ready|failed`.
- `wish_steps(id uuid, wish_id->wishes, step_id text, kind text, ref text, status pending|running|done|failed, attempt int, prompt text (cap 20k), raw_response text (cap 20k), output jsonb, error text (cap 2k), depends_on jsonb, started_at, ended_at, created_at, updated_at)` — unique(wish_id, step_id).
- `wish_logs(id uuid, ip text, created_at)` — rate-limit log (optional, RLS allow-all).
- RLS today is **demo-open**: `owners full (auth.uid()=owner OR owner IS NULL)` + `public read demo (true)` + `steps public read (true)`. Must harden for production (see §12).

---

## 5. API Contracts (FastAPI)

Base: `server/main.py` mounts `routers/wishes.py` at both `/api` and `` (so `/wish` and `/api/wish` both work). CORS `*` today.

| Method & Path | Body | Returns | Notes |
|---|---|---|---|
| `POST /generate`, `POST /api/generate` | `{prompt}` | `{tables[]}` | Legacy schema-only, OpenRouter-first via `call_llm`, fallback Gemini, repair pass, optional Supabase `schemas` insert |
| `POST /rag`, `POST /api/rag` | `{question}` | `{answer, cites[]}` | Via `rag.answer()` |
| `GET /health`, `GET /api/health` | — | `{ok, model, supabase:bool, planet:"intara", llm:{...}}` | `get_llm_status()` |
| `GET /api/wishes/health` | — | `{ok, wishes:true}` | Liveness |
| `POST /wish`, `POST /wishes` | `{prompt: 4..500 chars}` | full wish `{id,prompt,prd,artifacts,status,created_at}` | One-shot `make_wish()` = `plan_wish()` + `assemble()`; MEM cache + Supabase persist (wishes→fallback schemas) |
| `POST /wish/plan` | `{prompt, answers?, skip_clarify?}` | wish with `status planning` (if clarify score<70) or `awaiting_approval` | Staged entry; clarify-first via `clarify_prompt()`; persists clarifying shell with empty buildGraph if not ready; else `plan_build()` + `create_wish_tx()`; fail-fast requires Supabase |
| `PATCH /wish/{wid}/plan` | `{prd}` | updated wish `awaiting_approval` | Validates appName+tables; fills buildGraph/requirements/ia from mock if missing; deletes+reinserts `wish_steps` pending |
| `POST /wish/{wid}/answer` | `{answers:{qid:label}}` | wish `awaiting_approval` | Only if `status==planning`; `redraft_prompt()` + `plan_build()` + reset steps |
| `GET /wish/{wid}/suggest` | — | `{suggestions[{label,detail,prompt_suffix}]}` | Deterministic, no LLM |
| `POST /wish/{wid}/approve` | — | `{ok,status:"building",wid}` | Only from `awaiting_approval|approved|failed`; sets DB `building` + enqueues `_run_staged_build()` BackgroundTask |
| `GET /wish/{wid}/stream` | SSE | `snapshot, step_started/done/failed, build_done/failed, heartbeat` | `SSE_QUEUES` pub/sub + 2s DB poll fallback; frontend `streamBuild()` + polling fallback |
| `POST /wish/{wid}/retry` | `{stepId}` | `{ok, retrying}` | Resets step to pending (attempt+1), sets building, re-runs `_run_staged_build()` (resumes) |
| `GET /wish/{wid}`, `GET /wishes/{wid}` | — | full wish | DB first, MEM fallback for legacy one-shot |
| `GET /wishes` | — | `[{id,prompt,prd,created_at,status,build_graph}]` max 50 desc | DB + MEM merge deduped |
| `POST /wish/{wid}/regenerate` | — | new wish (same prompt) | One-shot re-run |

Frontend client mirrors all in `react-prompt-app/src/api/client.ts`. `createPlan()` has 35s AbortController. `streamBuild()` uses EventSource.

Rate limit: in-memory `RATE` 10/IP/24h for one-shot (reset on restart). Staged relies on LLM quota surfacing (429 with hint).

---

## 6. Generation Pipeline (detail for planner)

### 6.1 Clarify-first (`services/prompt_enhance.py`)
- `score_prompt()`: 45 base + detail (len>=120 +10, >=40 +5) + entities (distinct len>4 words x4 capped 20) + actions/data/audience/constraints (+5 each). Clamp 5..98. Returns `{score, aspects, missing}`.
- `clarify_prompt()`: tries 1 small LLM call for `{score, questions[{id,q,options[{label,desc}]}]}` (max 3x3), validates shape; fallback `_fallback_questions()` templates by domain (game/commerce/social else scope + audience/data). Returns `{score, ready: score>=70, questions, redrafted, _meta}`. Never raises 429 (advisory).
- `redraft_prompt(prompt, answers, questions)`: appends `"Q Answer: label."` per answer, cap 2000.

### 6.2 Plan (`services/planner.py`, `planner_v2.py`, `analyzer.py`)
- `mock_prd()`: keyword match task/blog/ecommerce/booking/forum/recipe/library/hr else generic keyword-derived appName/tables/pages/apis. Always returns valid PRD.
- `plan_wish()`: if no `OPENROUTER|GEMINI` key → mock + `_meta{source:mock}`. Else `call_llm_with_meta(INTARA_PLANNER_PROMPT)` → `parse_json` → validate appName+tables → repair call on fail → mock fallback. Quota → raise 429.
- `analyze_prompt()`: if no key → `mock_build_plan()` + analyzer defaults. Else `call_llm_with_meta(ANALYZER_SYSTEM_PROMPT)` → `_parse_json`/`main_parse` → `_validate_app_spec()` (snake_case, FK targets valid, page.table valid) → derive tables/entities/pages.table/buildGraph/requirements if missing → `_meta{analyzer:true}`. Quota → mock with `warning` + retry hint parsed from message.
- `mock_build_plan()` / `plan_build()`: enrich base PRD with requirements/ia/buildGraph DAG (see §4.2). `plan_build()` tries analyzer first, then LLM `BUILD_PLAN_PROMPT`, then mock. Ensures pages have `table` binding.

### 6.3 Generators
- **Schema (`generators/schema_gen.py`):** LLM-first if `prd.entities` via `schema_v2.build_schema_prompt()` → must return tables+sql+prisma else fallback. Deterministic `to_prisma()` (uuid id, camelCase fields, FK `@relation`, `@@index`) + `to_sql()` (uuid PK, FK `references`, indexes). Sanitize lower snake, allowed types, 1-5 tables, 2-6 fields, pad to 2 fields.
- **Frontend (`generators/frontend_gen.py`):** `api.ts` (baseFetch mock vs real + per-API fns) + `types.ts` + per-page: try `generate_frontend_page_llm()` (`frontend_page_v2` prompt, temp 0.3, `validate_tsx`, repair once) else template: detail (`:id` → fetch/edit/delete) vs list/dashboard (search/filter/stats/create/cards). Components `*Card.tsx` per table (first 3). `App.tsx` nav + `pages/index.ts` barrel.
- **Backend (`generators/backend_gen.py`):** If `prd.entities`, try per-table LLM (`backend_table_v2`, temp 0.3, `validate_python`, repair) → merge + scaffold + openapi fill. Else template: `models.py` (Pydantic), `main.py` (per-table GET list + POST create, Supabase→SQLite→[] fallback, CORS *, health), `routers/<table>.py`, `requirements.txt`, openapi from `apis`.
- **Scaffold (`generators/scaffold_gen.py`):** As in §3.2. `db.py` SQLite `sqlite:///./app.db` + Supabase swap.
- **Mock (`preview/mock_gen.py`):** Dexie `PreviewDB` with `++id,fields` stores incl. FKs, `seedPreview()` 3 rows/table, `installMockServer()` fetch interceptor for GET/POST/PATCH/DELETE incl. generic CRUD per table + detail `/:id`.
- **Assembler (`assembler.py`):** One-shot merge scaffold+mock into fe/be files, dedupe by path (last wins), README (stack/run/tables/pages/apis), cites via `rag.answer()` or 3 fallbacks, openapi passthrough.
- **Orchestrator (`orchestrator.py:76 run_build_sequential`):** Staged strict sequential. Loads canonical plan from DB, `init_build_state()`, resume done steps (restore schema/backend/frontend accumulators from `wish_steps.output`), `emit(build_started)`, per-node: set running → `persist_step(running)` → generate (schema/backend_table/frontend_page/wiring/validate with real `validator.py` + `validation_warnings` event) → `persist_step(done, prompt, raw, output)` → `step_done` + `update_wish_partial()` + `sleep 0.2`. Final: merge scaffold+mock+pages (dedupe api/types, regen final `App.tsx` with all routes/nav + barrel), regen final backend via `generate_backend(full plan)`, README staged, cites, `final_artifacts` → MEM+Supabase `ready` + `build_done`. Failures → `step_failed` + `build_failed`, return False. `validate` node checks all `.tsx` via `validate_tsx`, all `.py` via `validate_python`, cross-check via `validate_imports_consistency`.

### 6.4 Validator (`services/validator.py`)
- `validate_tsx`: missing default export, brace balance, `npx esbuild --bundle` (timeout 10s, skip if missing).
- `validate_python`: `ast.parse`.
- `validate_imports_consistency`: frontend `fetch(/api/X)` must have backend `@app.*(/api/X)` substring match.

### 6.5 LLM provider (`services/llm.py`)
Order: DeepSeek (`DEEPSEEK_API_KEY`, `deepseek-chat`) → Nvidia (`NVIDIA_API_KEY`, `deepseek-ai/deepseek-v4-flash-0731`, reasoning high for analyzer, vision helper `call_nvidia_vision` Kimi K3) → Groq (`GROQ_API_KEY`, `openai/gpt-oss-20b`) → OpenRouter (`OPENROUTER_MODEL/FALLBACK`, default `openrouter/free`) → Gemini (`call_gemini` in `main.py`, temp 0.2, tenacity 3x exp). `call_llm_with_meta()` returns `(text, {source,model})`. `embed_texts()` OpenRouter if `OPENROUTER_EMBED_MODEL` set else Gemini `gemini-embedding-001`, normalize to 3072d (pad/truncate). `get_llm_status()` for `/health` incl. OpenRouter quota check via `httpx`.

### 6.6 RAG (`server/rag.py`)
`chunk(400/50)` → `embed()` → `supabase.rpc(match_docs, {query_embedding, match_count:5})` (retry 1536 truncation, fallback direct `docs` fetch) → `Context+Q+Cite` synthesize via `call_llm(temp 0.2)` → `{answer, cites[120 chars]}`. Demo mode if no Supabase/LLM. `seed_docs()` 7 texts (DhiWise, pgvector, Gemini, Intara lore x4) tries 3072 →1536 →no-embedding.

### 6.7 JSON/quota utils (`utils/json_parse.py`, `server/main.py:45 parse_json`, `call_gemini:55`)
Strip ```json, regex `{.*}`, trailing-comma fix, truncation repair (last `}` + brace balance). `is_quota_error` checks 429/quota/exhausted incl. tenacity `RetryError` unwrapping. `call_gemini` tenacity `wait_exp(1,8)` x3.

---

## 7. Frontend (builder UI) Detail

- **Routes (`App.tsx`):** `/` Landing, `/wish/:id` WishVault (lazy), `/constellation` history, `/archives` RAG. `Layout` wrapper, `Suspense` fallback spinner.
- **Landing (`pages/Landing.tsx`):** Hero grid (copy + `PlanetOrb interactive 240`), 8 example chips (first 4 shown), wish count via `supabase.from(wishes).select(head)`, Build mode toggle `staged (plan→pages)` default vs `one-shot quick`, `WishInput` (debounced 350ms in component), `onWeave()` → `createPlan|createWish` → `nav(/wish/:id)`, `Pillars/HowItWorks`, lore strip, Archives RAG box (`askRag`).
- **WishVault (`pages/WishVault.tsx`):** `useWish(id)` + `refresh()`. If `weaving` → spinner. If `ready` without `buildGraph` → legacy `ArtifactVault`. Else staged Studio: `StudioRail` + `AgentThread` (clarify Q&A, plan approval, build events) + `StudioPreview` + `BuildingView` (DAG flowchart pills + per-step rows + progress bar + SSE `streamBuild()` + 2s polling fallback + Retry button per failed step, reload on done/failed).
- **ArtifactVault:** 5 tabs Trial (Sandpack+Dexie) / Schemas / Frontend / Backend / Scroll + Copy + Download zip + Share (`/wish/:id`).
- **PreviewTrial:** `toSandpackFiles()` → `SandpackProvider template react-ts autorun recompileDelay 600` + `SandpackPreview 380px` + sidebar table buttons + how-trial + Connect Supabase hint. Banner: "Preview DB is local — Connect Supabase to persist".
- **Constellation:** Each wish star hashed id→position, appName→size, filter, click→vault.
- **Lib:** `zip.ts buildWishZip()` + `downloadBlob()`, `sandpack.ts toSandpackFiles()` (leading `/`, hide package/mock/vite/tsconfig), `hash.ts`.
- **API client:** See §5 table. Types `Wish`, `WishStatus`, `Suggestion`.
- **Theme:** `theme/intara.css` dark nebula glass variables `--intara-nebula`, `--intara-faint`, etc. Motion: orb pulse 2s, tab fade 150ms, no Three.js (bundle <200KB target, Lighthouse >90 target).

---

## 8. DB & Migrations Detail

- Apply order in Supabase SQL editor: `supabase/schema.sql` then `migrations/001_intara_wishes.sql` then `migrations/002_staged_builds.sql`. Seed: `python -c "from rag import seed_docs; seed_docs()"`.
- `schema.sql`: `schemas` + `docs vector(1536)` + `match_docs(1536)` + allow-all RLS. Legacy only.
- `001`: `alter docs -> vector(3072)`, recreate `match_docs(3072)`, `wishes` + indexes + RLS, `wish_logs` + RLS.
- `002`: ensure `wishes`, add `current_step_id/build_graph/updated_at`, widen status check, `set_wishes_updated_at()` trigger, `wish_steps` + indexes + RLS + trigger, backfill, docs dim fix (DO block), recreate `match_docs(3072)`.
- `db/wishes.py` caps: prompt 20k, raw 20k, error 2k. All writes raise on no-data (fail-fast, no silent MEM).

---

## 9. Env & Run

**Backend `server/.env.example`:**
`DEEPSEEK_API_KEY/MODEL`, `GROQ_API_KEY/MODEL`, `NVIDIA_API_KEY/MODEL`, `GEMINI_API_KEY/MODEL=gemini-3.6-flash`, `SUPABASE_URL/KEY`, `OPENROUTER_API_KEY/MODEL/FALLBACK` (default `openrouter/free`), `OPENROUTER_EMBED_MODEL=` (empty = skip OpenRouter embed). Without keys: deterministic mock + MEM store + fallback cites, still passes benchmark. 10 wishes/IP/day in-mem.

**Frontend `react-prompt-app/.env.example`:** `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL=http://localhost:8000`. Empty = demo MEM mode.

**Quickstart (free, no keys):**
```bash
cd react-prompt-app && npm install && cp .env.example .env && npm run dev  # :5173, proxy /api->:8000
cd ../server && pip install -r requirements.txt && cp .env.example .env && uvicorn main:app --reload --port 8000  # :8000/docs
# Supabase once: run schema.sql then 001 then 002; seed: python -c "from rag import seed_docs; seed_docs()"
# Demo: backend MEM store, mock PRDs, deterministic assembler, fallback cites.
```

**Benchmark:**
```bash
python scripts/eval.py --mocked --verbose  # 5 wishes x 6 checks, exit 0/1 for CI
pytest tests/test_golden_wishes.py -v       # 4/4
curl -X POST http://localhost:8000/api/wish -H 'Content-Type: application/json' -d '{"prompt":"A task tracker..."}' | python -m json.tool  # live 1 call
```
Golden wishes: task tracker, blog, ecommerce wishlist, booking salon, forum (cover 80% CRUD). 6 checks: json_valid, schema (1-3 tables 2-5 fields), fe_build (tsc), be_parse (ast+ruff), openapi (paths), cites (cites>0 or README has Intara). Suite pass = 5/5.

---

## 10. Current Constraints / Assumptions (do not violate silently)

- Locked generated stack: Vite React 18 + TS + Tailwind + FastAPI + Supabase + Prisma. No Next.js/Vue/Firebase.
- Free-tier: Gemini 60 RPM / 1500 RPD / 1M tokens/day, Supabase Free 500MB/50k MAU, Vercel Hobby, Render Free (sleeps). Debounce 350ms, 10 wishes/IP/day, tenacity retry, 429 surfacing with retry hint.
- Prompt 4..500 chars. Tables 1-5 (eval expects 1-3), fields 2-6 (eval 2-5). Types text/integer/timestamp/boolean (+uuid in v2 paths only).
- No server cost for preview (Sandpack browser + Dexie, not Docker). No sandbox `npm build` server-side.
- RAG chunk 400/50, embed 3072d, top_k 5, cites 120 chars.
- SSE + polling dual path required (EventSource unreliable). DB is source of truth for staged; MEM is cache + legacy one-shot fallback only.
- Bundle <200KB, Lighthouse >90, mobile works (targets, not yet enforced).

---

## 11. What Works Today (strengths to preserve)

- Prompt → PRD/AppSpec → runnable FE+BE+Trial+Zip E2E in browser before Supabase.
- Staged DAG with per-step prompt/output persistence, resume, retry, SSE live + poll fallback.
- Clarify Q&A improves vague prompts without blocking on quota.
- Deterministic fallbacks everywhere (mock PRD, template pages/backends, mock Dexie, fallback cites) → benchmark passes with $0.
- Modular generators + validator + eval suite → safe to extend per-table/per-page.

---

## 12. Gaps to Production-Grade for Small Non-Tech Businesses (planning agent: address these)

**Context:** Target user is a non-technical SMB owner/staff who needs internal tools (inventory, bookings, CRM, leave tracker, billing, catalog) without hiring devs. They cannot run `npm install` / `uvicorn`. They need hosted, shareable, secure tools with iteration.

1. **No hosted generated apps:** Only zip + local trial. Need one-click Preview (already Sandpack) → Deploy (Vercel for FE + Render/Fly/Docker for BE + per-customer Supabase project/branch) → live URL + custom domain + env management.
2. **Auth/tenancy demo-grade:** CORS `*`, RLS public-read demo, MEM/RATE in-memory, no orgs/workspaces/roles, no `auth.uid()` enforcement. Need workspaces, roles (admin/member/viewer), per-app RLS, audit logs, Redis/DB rate limits, secret vault.
3. **No iteration:** No chat-to-refine ("add status column", "add auth"), no versioning/diff/rollback, only manual `patchPlan`. Need `POST /wish/:id/iterate {instruction}` re-running single DAG node + history + diff UI. `wish_steps.prompt/raw/output` already stored — expose it.
4. **Expressiveness narrow:** Only CRUD + 4 types. SMB needs auth pages, file/image upload (Supabase Storage), search/filter/pagination/sorting, dashboards/charts, calendar/kanban, forms/wizards, workflows/reminders, integrations (Sheets, WhatsApp, email, UPI/invoice), roles/permissions, CSV import/export.
5. **Reliability/ops:** In-process `BackgroundTasks` + `asyncio.Queue`, no durable queue (Inngest/BullMQ/Temporal), no observability (logs/metrics/traces), no backups, no SLA, no billing metering.
6. **UX for non-tech:** Builder UI is dev-flavored (tabs with code, zip). Need plain-language mode, templates gallery (Inventory, CRM, etc.), guided setup, hosted app dashboard, user management, help/support.
7. **Security/compliance:** No input sanitization beyond length, no prompt-injection guard, no PII handling, no SOC2/GDPR story, no pen-test. Harden before SMB data.
8. **Commercial:** No teams, billing (per-wish + per-hosted-app), support, uptime, data residency.

**Non-goals for next plan (unless user asks):** multi-stack (keep locked stack), realtime collab, heavy 3D/WebGL, full HumanEval 164, Docker sandbox preview (prefer WebContainers).

---

## 13. Instructions to Planning Agent

1. **Read** `docs/INTARA_SCOPE.md`, `docs/BENCHMARK.md`, `architecture.md`, `README.md`, then this file.
2. **Propose** a phased roadmap P0 (harden) → P1 (hosted + non-tech usable) → P2 (iterate/version) → P3 (SMB SaaS wrapper) with concrete file-level changes, DB migrations, API additions, UI additions, and eval updates. Keep locked stack unless justified.
3. **Preserve** what works (§11) and constraints (§10). Call out breaking changes explicitly (e.g., RLS tightening, MEM removal, status widening).
4. **Include** effort estimates (weeks), free-tier cost impact, risks, and acceptance criteria per phase reusing `scripts/eval.py` + `tests/test_golden_wishes.py` patterns (extend to new checks: deploy success, RLS deny, iterate diff, Lighthouse).
5. **Ask** for clarification only on true tradeoffs (e.g., Vercel vs Cloudflare, Supabase branching vs per-tenant schema, queue choice). Default to cheapest free-tier option.
6. **Output** a build plan with ordered tasks, each with files to touch, SQL to run, env to add, and how to verify (commands + expected output).

---

*End of spec — generated from live codebase inspection. If code and this file disagree, trust code and update this file.*
