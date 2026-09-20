# Intara — Planet of Wishes ✨

> **Make a software wish come true — describe any app, Intara weaves schemas, frontend, backend, and specs as stardust.**

![Intara](https://img.shields.io/badge/Intara-Planet%20of%20Wishes-8B5CF6) ![React](https://img.shields.io/badge/React-18-149eca) ![FastAPI](https://img.shields.io/badge/FastAPI-Python-009688) ![Gemini](https://img.shields.io/badge/Gemini-3.6-8B5CF6) ![Supabase](https://img.shields.io/badge/Supabase-pgvector-3fcf8e)

```
Wish --(Intara)--> PRD --> { Schemas, Frontend, Backend, Scroll } --> Zip + Share
                └─ RAG (pgvector 3072d) → cites + groundedness
```

**Theme:** Fictional planet **Intara** 3.7 light years away — obsidian oceans, violet auroras, every wish drifts to Intara and returns as four artifacts. Dark nebula glass, orb pulse, constellation map.

### What it does (v1.1 — runnable + trial, free-tier $0)

*   **Schemas** — `schema.json` + `schema.prisma` + `supabase.sql` + Mermaid ER
*   **Frontend** — **Runnable** Vite React 18 + TS + Tailwind — `package.json`, `vite.config.ts`, `index.html`, `src/main.tsx`, `src/pages/*.tsx`, `src/components/*Card.tsx`, `src/api.ts` (mock vs supabase switch), `src/mock/*` (Dexie trial), `src/types.ts` — `npm install && npm run dev` works
*   **Backend** — **Runnable** FastAPI + Pydantic + **SQLite default, Supabase swap** — `server/main.py` (real CRUD via `db.py` sqlite→supabase), `server/models.py`, `server/routers/*.py`, `db.py` (SQLAlchemy + Supabase adapter), `requirements.txt` (+sqlalchemy), `openapi.json` — `pip install -r requirements.txt && uvicorn main:app` works with **no Supabase**
*   **Scroll** — `README.md` (how to run) + `PRD.json` + cites from archives
*   **Trial** — Vault Tab 1 **Trial** — Sandpack instant iframe (no server) + IndexedDB relational (Dexie) + seed 3 rows/table + table explorer + Create form — full E2E CRUD in browser before Supabase. Banner: "Preview DB is local — Connect Supabase to persist"

**Zip** is split runnable: `{slug}/frontend/` (Vite) + `{slug}/backend/` (FastAPI+SQLite) + `README.md` + `PRD.json` + `CITES.md`. No config needed; swap to Supabase via `VITE_API_MODE=supabase` + `SUPABASE_URL` (no regen).

**Not yet:** No deploy — you get runnable zip + shareable `/wish/:id` + in-browser trial. v2 adds GitHub push, Vercel deploy, chat to refine.

Built for **portfolio + Jan 2027 internship demos** — 5 golden wishes 100% pass (see `docs/BENCHMARK.md`).

### Stack

- **Frontend:** Vite 5 + React 18 + TypeScript + React Router + Tailwind (glass) + jszip + **Sandpack** + **Dexie** — debounced wish input, 5-tab vault (Trial instant + Schemas/Frontend/Backend/Scroll), constellation star map
- **Backend:** FastAPI 0.110 + `google-genai` (Gemini 3.6-flash) + Tenacity retry + **SQLAlchemy** — planner `wish → PRD` + deterministic generators (scaffold + mock) + assembler, guarded JSON, 429 retry, **SQLite fallback**
- **DB:** Supabase Postgres + `pgvector` vector(3072) (fixed from 1536) + RLS — `wishes(id, prompt, prd, artifacts, status)` + `docs` + `wish_logs` + RPC `match_docs` cosine; **Preview uses Dexie IndexedDB relational (no Supabase)**
- **AI:** Gemini `generate_content` (PRD) + `embed_content` (`gemini-embedding-001`, 3072d) + Supabase `vector <=>`, cites `120 chars`

### Quick Start (free-tier, no keys needed for demo)

```bash
# 1. Frontend — Intara shell
cd react-prompt-app
npm install
cp .env.example .env  # optional: VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY (or demo MEM store)
npm run dev            # http://localhost:5173  (proxy /api → :8000)

# 2. Backend — Planet core
cd ../server
pip install -r requirements.txt
cp .env.example .env   # optional: GEMINI_API_KEY + SUPABASE_URL + SUPABASE_KEY
                        # without keys, uses deterministic mock (free, still passes benchmark)
uvicorn main:app --reload --port 8000  # http://localhost:8000/docs

# 3. Supabase (once, if you have Supabase)
# Run supabase/schema.sql then supabase/migrations/001_intara_wishes.sql in SQL editor
# Seed docs:
python -c "from rag import seed_docs; seed_docs()"  # adds Intara lore docs (7 texts)
```

**Demo without Supabase/Gemini:** Works — backend uses in-memory `MEM` store, planner returns mock PRDs (task tracker etc), assembler deterministic, cites fallback. 10 wishes/IP/day limit (in-memory).

### Routes

- `/` — Landing: planet orb + wish input (debounced) + lore strip + archives RAG
- `/wish/:id` — Vault: **5 tabs Trial (Sandpack+Dexie) / Schemas / Frontend / Backend / Scroll** + Copy + Download split runnable zip + Share
- `/constellation` — My wishes: star map (hash id → position) + list, filter, click → vault
- `/archives` — RAG ask docs (`gemini-embedding-001` 3072d, `match_docs`)

### Project Structure

```
react-prompt-app/
  src/App.tsx              — router shell (Landing, WishVault, Constellation, Archives)
  src/theme/intara.css     — dark nebula glass (#0a0a12, #8B5CF6)
  src/components/PlanetOrb.tsx, WishInput.tsx, Header.tsx, ArtifactVault.tsx (5 tabs), Layout.tsx, PreviewTrial.tsx, TableExplorer.tsx
  src/pages/Landing.tsx, WishVault.tsx, Constellation.tsx, Archives.tsx
  src/api/client.ts        — createWish, getWish, listWishes, askRag
  src/lib/zip.ts           — buildWishZip (split runnable) + downloadBlob
  src/lib/sandpack.ts      — toSandpackFiles
  src/hooks/useWish.ts, useAuth.ts
  public/assets/           — planet-intara.png, starfield.png, wish-orb.png, constellation.png, nebula-gradient.png, glyphs/*
server/
  main.py                  — FastAPI + CORSMiddleware + wishes router
  prompts/intara.py        — INTARA_PLANNER_PROMPT
  services/planner.py      — mock_prd + Gemini guarded (free-tier fallback)
  services/generators/schema_gen.py, frontend_gen.py, backend_gen.py, scaffold_gen.py
  services/preview/mock_gen.py — Dexie db.ts, seed.ts, server.ts (IndexedDB mock)
  services/assembler.py    — PRD → runnable artifacts (scaffold + mock + cites)
  routers/wishes.py        — POST /api/wish, GET /api/wish/:id, GET /api/wishes
  rag.py                   — chunk 400/50 + embed 3072d + match_docs → synthesize
  data/intara_lore.md      — planet lore for RAG
supabase/
  schema.sql               — schemas, docs vector(1536) legacy
  migrations/001_intara_wishes.sql — wishes vector(3072) fix + RLS + wish_logs
assets/
  ASSET_PROMPTS.md         — prompts to regenerate planet/starfield/orb/glyphs
  planet-intara.png etc.   — AI-generated, <1MB each, wired to /assets/*
docs/
  INTARA_SCOPE.md          — theme bible + 4 artifacts spec
  BENCHMARK.md             — 5 golden wishes, 6 checks, HumanEval/MBPP adapted
tests/fixtures/wishes.json — 5 ideal wishes
scripts/eval.py            — mocked + live eval (tsc + ruff + ast)
```

### Benchmark — 5 Golden Wishes (must PASS)

```bash
python scripts/eval.py --mocked --verbose
# wish 1 task tracker, 2 blog, 3 e-commerce, 4 booking, 5 forum — all 6 checks pass:
# json_valid, schema (1-3 tables, 2-5 fields), fe_build (tsc), be_parse (ast+ruff), openapi, cites
pytest tests/test_golden_wishes.py -v  # 4/4
# Live (hits backend, costs 5 free calls):
curl -X POST http://localhost:8000/api/wish -H 'Content-Type: application/json' -d '{"prompt":"A task tracker..."}' | python -m json.tool
```

**Why these 5:** Cover 80% CRUD (users+owned, likes/votes, carts/orders, time slots). Standard in Rocket.new/Supabase demos.

### 60-sec Loom Script (Intara)

*[0-10s]* “Hi, I’m Huzefa — I built Intara, Planet of Wishes: prompt goes in, **runnable** frontend + backend + trial come out.”

*[10-25s]* (Show Landing) “Dark nebula glass, planet orb pulses while weaving. Debounce 350ms, guarded planner, mock fallback if Gemini 429, store to wishes.”

*[25-45s]* (Show WishVault Trial) “Vault **Trial** is Sandpack instant + IndexedDB relational — Create in browser, no Supabase, persists. Then 4 tabs: ER + prisma/sql, file tree, FastAPI+SQLite, README + OpenAPI + cites. One click split runnable zip.”

*[45-55s]* (Show Constellation) “Each wish is a star hashed to position, constellation lines, filter, shareable link. Archives is RAG 400/50 chunk → 3072d → pgvector.”

*[55-60s]* “Free-tier $0, 10 wishes/day, eval is build success + cites. v2 adds GitHub push, Vercel deploy, chat diff.”

### Why Intara works

- **Ops:** Template-locked stack (Vite React + FastAPI) + `tsc`/`ruff` gate, not hallucinated infra
- **LLMOps:** JSON guard + repair, 429 retry, pgvector 3072d, cites groundedness — not just demo
- **Theme:** Fictional planet gives distinct portfolio story, not a Bolt clone

---

Built by **Huzefa Mandviwala** — B.Tech AI & DS, SCET Surat — Jan 2027 loop.  
*Intara reuses prototype primitives you type live, now as a production-grade wish forge.*
