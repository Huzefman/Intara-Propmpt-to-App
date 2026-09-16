# Plan: Intara — Planet of Wishes — Prompt → Artifacts

> **Approved scope:** Defaults — full runnable artifacts (schema/prisma/sql + FE Vite React+TS+Tailwind + BE FastAPI+OpenAPI+README), stack locked React+FastAPI, one-shot+regenerate, dark nebula glass, free-tier $0, benchmark suite.

---

## 0. Context & Current Baseline

**Repo:** `prompt-to-app` — 56 files, 508 lines. Prototype `App.tsx:10` debounced 350ms → `POST /generate` `main.py:53` → `call_gemini` `main.py:47` → `parse_json` guard `main.py:37` → Supabase `schemas` `supabase/schema.sql:5` → list. RAG `rag.py:42` chunk 400/50 → `gemini-embedding-001` 3072d → `match_docs` `<=>` → synthesize + cites.

**Gaps:** Single `{tables}` json only, no FE/BE code, RLS `allow all`, `vector(1536)` bug vs 3072, demo fallback zero-vector, no auth, no history, inline white styles `App.tsx:54`, no routing.

**Target:** Intara themed web app — `wish → PRD → 4 artifact vault` — see `docs/INTARA_SCOPE.md` for full scope. v1 artifact-only (no sandbox/preview/deploy), runnable zip + share link.

---

## 1. Architecture Overview

```
Wish (prompt) 
  → POST /api/wish {prompt, owner}
  → Planner (Gemini 3.6-flash, INTARA_PLANNER_PROMPT) → PRD {appName, tables, pages, apis, auth}
  → Parallel Generators (3× call_gemini + parse_json repair):
       SchemaGen  → {tables, prisma, sql} (deterministic SQL template)
       FrontendGen→ {files: [{path,content}]} (Vite React template + App.tsx patterns)
       BackendGen → {files, requirements.txt, openapi.json} (FastAPI template + main.py patterns)
  → Assembler → artifacts jsonb {schema, frontend, backend, spec:{readme,openapi,cites}} → wishes table
  → FE Vault (4 tabs + jszip + copy) + Constellation (history)
  → RAG (rag.py) for cites in Scroll tab + Archives page
```

**DB:** `wishes` table + fix `docs.vector(3072)` + RLS `auth.uid()=owner`.

**Free-tier guardrails:** Debounce 350ms, 10 wishes/IP/day (in-memory), tenacity retry 429, WebContainers deferred.

---

## 2. Phases — Ordered, Dependency-Aware

### Phase 0 — Foundation & Rebrand (3 days) — *Unlocks all*

**Goal:** Production-safe baseline + Intara shell.

**BE:**
*   Fix uncommitted diffs: confirm `vite.config.ts:5` proxy rewrite, `supabase.ts` `(import.meta as any)`, embeddings truncation `rag.py:37`, `requirements.txt` bumps.
*   Env validation: `pydantic-settings`, fail fast if `GEMINI_API_KEY` missing (no demo fallback).
*   DB migration: `supabase/migrations/001_intara_wishes.sql` — create `wishes`, alter `docs.embedding vector(3072)`, RLS policies. Backfill: `update docs set embedding = ...` or reseed `seed_docs()`.
*   Extract routers: `server/routers/wishes.py` from `main.py:53`, keep `main.py` as thin `FastAPI` + `CORSMiddleware` `main.py:24`.

**FE:**
*   Install: `react-router-dom`, `jszip`, `prismjs` (or `shiki`), `mermaid`.
*   Theme: `src/theme/intara.css` (palette `#0a0a12` bg, `#8B5CF6` nebula, glass), `src/theme/tokens.ts`, replace `App.tsx:54` inline styles with classes.
*   Layout: `src/components/PlanetOrb.tsx` (img from `assets/planet-intara.png`, pulse on loading), `src/components/WishInput.tsx` (reuse debounce `App.tsx:26`), `src/components/Layout.tsx` (starfield `assets/starfield.jpg` bg).
*   Routing: `src/main.tsx` → `BrowserRouter`, `src/App.tsx` → shell with `<Routes>` — `/` Landing, `/wish/:id`, `/constellation`, `/archives` (placeholders).
*   Keep `api.ts:5` but add `VITE_API_URL` fallback.

**Infra:** `vercel.json` (SPA fallback), CI `npm run build` check, `.env.example` updated.

**Deliverable:** `npm run dev` shows Intara landing (orb + wish input), no artifacts yet, `GET /health` ok, DB migrated.

**Verify:** `vite build` passes, `supabase/schema.sql` runs without error, manual wish input shows debounce, no console warnings.

---

### Phase 1 — Wish → PRD Planner (1 week) — *Depends Phase 0*

**Goal:** Single prompt → rich PRD, editable before artifact gen.

**BE:**
*   `server/prompts/intara.py` — `INTARA_PLANNER_PROMPT`:
    ```
    You are Intara, planet of wishes. Given wish, return ONLY JSON:
    {"appName": "...", "tagline": "...", "tables": [{"name": "...", "fields": [{"name":"...", "type":"text|integer|timestamp|boolean"}]}],
     "pages": [{"name":"Dashboard", "route":"/", "components":["TaskList","TaskCard"]}],
     "apis": [{"method":"GET", "path":"/api/tasks", "desc":"list tasks"}],
     "auth": true|false}
    Rules: 1-3 tables, 2-5 fields each, 1-4 pages, 2-6 apis. Types only text/integer/timestamp/boolean. No markdown.
    Wish: {prompt}
    ```
*   `server/services/planner.py` — `plan_wish(prompt) -> PRD` calls `call_gemini`, `parse_json` `main.py:37`, repair prompt `f"Fix to valid JSON: {raw}"` `main.py:63`, validate with `pydantic PRDModel`, retry 429.
*   `server/routers/wishes.py` — `POST /api/wish {prompt}` → `plan_wish` → `supabase.table("wishes").insert({prompt, prd, artifacts:{}, status:"weaving"})` → return `Wish`. `GET /api/wish/:id`, `POST /api/wish/:id/regenerate`. Rate limit: in-memory `dict[ip] -> count` 10/day.
*   Tests: `tests/test_planner.py` mocked Gemini, golden PRD fixtures.

**FE:**
*   `src/api/client.ts` (extend `api.ts`) — `createWish(prompt)`, `getWish(id)`, `regenerateWish(id)`.
*   `src/pages/Landing.tsx` — wish input → `createWish` → navigate `/wish/:id` with loading "Intara is listening... weaving stardust..." (reuse `loading` `App.tsx:62` pattern themed).
*   `src/pages/WishVault.tsx` — shows PRD preview (editable tables/fields, pages list) with "Weave Artifacts" button → triggers Phase 2 (or auto-triggers). Store `Wish` in state, fetch on mount.
*   `src/hooks/useWish.ts` — fetch + poll if status weaving.

**Deliverable:** Wish "task tracker..." → PRD with 2-3 tables, 3 pages, 4 apis visible, editable, persists to Supabase.

**Verify:** `pytest tests/test_planner.py` passes, manual 5 golden wishes produce valid PRD json (eval `json_valid` `docs/BENCHMARK.md`).

---

### Phase 2 — Artifact Generators (2 weeks, core) — *Depends Phase 1*

**Goal:** PRD → 4 artifacts, vault tabs, zip.

**BE:**
*   `server/services/generators/schema_gen.py` — `generate_schema(prd) -> {tables, prisma, sql}`. LLM prompt: PRD tables → `{"tables": ...}` + deterministic templates: `prisma` string builder, `sql` `create table` builder (not LLM hallucinated). Validate `tables` same as PRD.
*   `server/services/generators/frontend_gen.py` — `generate_frontend(prd) -> {files}`. Prompt per file:
    ```
    You are frontend weaver for Intara. Stack: Vite React18 + TS + Tailwind. Given PRD page {name,route,components}, return ONLY file content for src/pages/{Name}.tsx, no markdown, use Tailwind, import from '@/components', no extra deps.
    ```
    Generate 3-5 files: `src/pages/*.tsx`, `src/components/*.tsx`, `src/api.ts` analogue, `src/types.ts`. Concatenate? Or parallel per file (queue). Validate each with `tsc --noEmit` via `subprocess` (if fails, repair 1x with error msg).
*   `server/services/generators/backend_gen.py` — `generate_backend(prd) -> {files, requirements, openapi}`. Prompt per route file. Files: `server/main.py` snippet, `server/models.py`, `server/routers/*.py`, `requirements.txt` (fastapi, uvicorn, pydantic, supabase), `.env.example`, `openapi.json` (build from `apis`). Validate with `ast.parse` + `ruff check` (if fails, repair).
*   `server/services/assembler.py` — `assemble(wish_id, prd) -> Artifacts`. Orchestrates 3 gens parallel (`asyncio.gather`), builds `README.md` (how to run: `npm i && npm run dev`, `uvicorn main:app`), merges `cites` from `rag.answer(prd.tagline)` `rag.py:42`, writes `wishes.artifacts` + `status ready`.
*   Router: `POST /api/wish/:id/weave` → `assembler.assemble` (or auto-call after planner). Or merge into `POST /api/wish` to do planner+assembler in one for simpler FE.
*   Tests: mocked generators, fixture `tests/fixtures/wishes.json` 5 golden, `scripts/eval.py` checks `fe_build`, `be_parse`.

**FE:**
*   `src/components/ArtifactVault.tsx` — 4 tabs (state `activeTab`):
     *   Schemas: `SchemaTab` — Mermaid ER (`mermaid.render` from `tables`), code blocks for `schema.json`, `prisma`, `sql` with copy.
     *   Frontend: `FrontendTab` — file tree (left) + Monaco-like code view (right, readOnly, prism highlight), copy per file.
     *   Backend: `BackendTab` — similar, plus `requirements.txt` highlight.
     *   Scroll: `SpecTab` — `README.md` rendered markdown, `openapi.json` table, cites `Cites: ...` `App.tsx:47` pattern rethemed "Intara consulted archives".
*   `src/lib/zip.ts` — `buildZip(artifacts) -> blob` via `jszip` (frontend-only, no BE zip).
*   `src/pages/WishVault.tsx` — fetches `Wish`, shows vault if `status ready`, else weaving loader + poll.
*   Actions: `Copy All`, `Download Zip`, `Share` (copy link), `Regenerate` (disabled weave button), `Make another wish`.

**Deliverable:** Wish → 4 tabs populated, zip downloads, `tsc` on extracted FE passes, all copyable.

**Verify:** `scripts/eval.py --golden` — 5 wishes `fe_build` + `be_parse` pass 100%, manual zip `unzip && npm i && npm run build` succeeds for "task tracker".

---

### Phase 3 — Persistence & Constellation (4 days) — *Depends Phase 2*

**Goal:** Auth + history, Intara lore.

**BE:**
*   Supabase Auth: `supabase.auth` already via `supabase-js` `supabase.ts:12`. Add helper `server/deps/auth.py` to verify `Authorization` header, extract `owner`.
*   Migration: `wishes.owner` FK `auth.users`, backfill anon wishes `owner=null`, RLS as in scope.
*   Seed: `server/data/intara_lore.md` (create) + existing `sample_docs.md:3` → `rag.seed_docs` `rag.py:59` extended to include Intara lore docs (for cites).
*   RAG: `rag.py` unchanged except vector fix, but `answer` called with `wish.prompt + prd.tagline` for richer context.

**FE:**
*   `src/hooks/useAuth.ts` — `supabase.auth.getSession`, `signIn`, `signOut`.
*   `src/pages/Constellation.tsx` — fetch `supabase.from('wishes').select('*').order('created_at')` (if authed, filter `owner`), render star map: `svg` with `assets/constellation.svg` bg, each wish star at `(hash(prompt) % width, hash(prompt+id) % height)`, size by `tables.length`, tooltip prompt snippet, click → `/wish/:id`. Fallback grid list for mobile.
*   `src/pages/Archives.tsx` — reuse `askRag` `api.ts:15` → `POST /api/rag` `main.py:76` → show `answer + cites`, themed "Consult Intara archives".
*   `src/components/Header.tsx` — Intara wordmark, nav: Wish / Constellation / Archives, auth avatar.
*   Anonymous: allow wish creation, but prompt "Sign in to save your wish to constellation" banner.

**Deliverable:** Authed users see persistent wishes, shareable links, archives RAG works with lore cites.

**Verify:** RLS test (anon can read, only owner can delete), star map renders 5 golden wishes, `askRag("What is Intara?")` returns lore cite.

---

### Phase 4 — Polish, Export & Hardening (1 week) — *Depends Phase 3*

**Goal:** Portfolio-ready, free-tier guardrails,.eval.

**BE:**
*   Export: `POST /api/wish/:id/github` (stub, returns "v2" message) — or implement Octokit if time (free). But spec says disabled button v1, so just stub.
*   Rate limit hardened: from in-memory to `supabase` log table `wish_logs(ip, created_at)` counted, or `slowapi`.
*   Logging: `console.log` → structured `print(f"wish {id} {prompt} prd_ok")` for eval.
*   CI: `pytest`, `ruff`, `tsc` in GitHub Action (if repo has actions).

**FE:**
*   Polish: orb pulse animation `intara.css`, glass card shadows, empty states ("No wishes yet — make your first"), error boundaries, mobile responsive (vault tabs → accordion), copy toast, zip progress.
*   `src/lib/eval.ts` — client-side checks before showing (e.g., `artifacts.schema.tables.length` badge).
*   `assets/*` wiring: import `planet-intara.png` in `PlanetOrb.tsx`, `starfield.jpg` as `body` bg, `glyphs` in tabs, fallback to CSS if asset missing (check `assets/.gitkeep`).
*   Accessibility: `aria-label` on tabs, `textarea` `App.tsx:60` retains `label`.

**Benchmark:** Run `docs/BENCHMARK.md` suite:
*   `pytest tests/test_golden_wishes.py` (mocked)
*   `python scripts/eval.py --live` (one live Gemini call for "task tracker", checks `fe_build` via `tsc` temp dir) — optional, costs 1 free call.
*   Manual Lighthouse: target >90.

**Deliverable:** `intara.vercel.app` deployed (Vercel Free), `README.md` updated with Intara story + `Quick Start` + `Benchmark` badge, demo ready.

**Verify:** Full flow wish → vault → zip → constellation, Lighthouse, eval script passes 5/5 golden, `assets` present or graceful fallback.

---

## 3. File Change Map

**New FE:**
*   `src/theme/intara.css`, `src/theme/tokens.ts`
*   `src/components/PlanetOrb.tsx`, `WishInput.tsx`, `Layout.tsx`, `Header.tsx`
*   `src/components/ArtifactVault.tsx`, `SchemaTab.tsx`, `FrontendTab.tsx`, `BackendTab.tsx`, `SpecTab.tsx`
*   `src/pages/Landing.tsx`, `WishVault.tsx`, `Constellation.tsx`, `Archives.tsx`
*   `src/api/client.ts` (extends `api.ts`), `src/hooks/useWish.ts`, `useAuth.ts`, `src/lib/zip.ts`, `src/lib/hash.ts`
*   `src/data/lore.ts` (optional)

**Modified FE:**
*   `src/App.tsx` → router shell (keep debounce logic moved to `WishInput.tsx`)
*   `src/main.tsx` → BrowserRouter
*   `src/supabase.ts` → auth session
*   `vite.config.ts:5` unchanged

**New BE:**
*   `server/prompts/intara.py`
*   `server/services/planner.py`
*   `server/services/generators/{schema_gen,frontend_gen,backend_gen}.py`
*   `server/services/assembler.py`
*   `server/routers/wishes.py`
*   `server/deps/auth.py` (optional)
*   `server/data/intara_lore.md`
*   `supabase/migrations/001_intara_wishes.sql`

**Modified BE:**
*   `server/main.py` → include routers, keep `parse_json`, `call_gemini`, `health` `main.py:88`, add `wishes` routes
*   `server/rag.py` → fix vector 3072, extend `seed_docs` lore
*   `supabase/schema.sql` → add wishes table doc

**Tests/Docs:**
*   `docs/INTARA_SCOPE.md` (done), `docs/BENCHMARK.md`, `assets/ASSET_PROMPTS.md`, `assets/README.md`
*   `tests/test_planner.py`, `tests/test_generators.py`, `tests/fixtures/wishes.json`, `scripts/eval.py`

**Infra:**
*   `vercel.json`, `.env.example` additions `VITE_API_URL`, `GEMINI_MODEL`

---

## 4. Risks & Mitigations

*   **LLM hallucinates broken code** (high) → Templates + `tsc`/`ruff` gate + 1 repair retry, not pure LLM. If still fails, show warning badge but still deliver.
*   **Gemini 429 free-tier** (medium) → Debounce 350ms, queue, 10/day limit, tenacity 3 retries `main.py:46`, show "Intara is crowded, retry in X" toast.
*   **Vector dim mismatch** (high) → Migration `vector(3072)` before any RAG call, else `match_docs` errors. Mitigate Phase 0 first.
*   **Asset missing** (low) → Fallback CSS orb (gradient circle) if `assets/planet-intara.png` absent, check `assets/.gitkeep` in `Layout.tsx`.
*   **Scope creep (multi-stack)** (medium) → Lock React+FastAPI, reject Next.js requests v1, document in scope.

---

## 5. Execution Plan for Agents

*   **Agent 1 (Frontend — Intara Theme):** Phase 0 FE + Phase 2 Vault tabs + Phase 3 Constellation.
*   **Agent 2 (Backend — Planner/Generators):** Phase 1 planner + Phase 2 generators/assembler + DB migration.
*   **Sequential:** Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4, with benchmark eval after Phase 2.

**Next step after plan approval:** Create docs + asset prompts (this plan + scope + benchmark already drafted), generate assets externally, then opencode agents build Phase 0.

---

*Plan approved — proceed to file creation.*
