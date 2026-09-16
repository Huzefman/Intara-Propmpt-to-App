# Intara — Planet of Wishes — Project Scope & Theme Bible

> **One-line vision:** Intara is a distinct fictional planet — the Planet of Wishes — where every software wish drifts across space, is heard, and returns as ready-to-use code. You describe your wish, Intara weaves the artifacts.

---

## 1. Vision & Positioning

*   **Theme:** Fictional planet **Intara** (3.7 light years beyond the heliopause, dark nebula, obsidian oceans, violet auroras). Intara listens. Wishes become stardust, then schemas, then code.
*   **Tagline:** "Make a software wish come true — describe it, Intara builds it."
*   **Differentiator vs prototype:** Prototype = `prompt → {tables} → list` (70 lines `react-prompt-app/src/App.tsx`). Intara = `wish → PRD → 4 artifact vault` (schemas + frontend + backend + spec) — full runnable project, not just tables.
*   **Positioning:** Mini Rocket.new / Lovable / Bolt, but themed, opinionated, and free-tier runnable. Built for portfolio + Jan 2027 internship demos — every generation is explainable.

## 2. User & Journey

**Primary user:** Solo maker / student / indie hacker who can describe an app but hates boilerplate. Non-technical enough to wish, technical enough to run `npm install`.

**Core journey:**
1.  Lands on Intara — sees planet orb, starfield, lore strip, example wish chips.
2.  Types wish in central glowing textarea (debounced 350ms, same as `App.tsx:26`).
3.  Sees "Intara is listening... weaving..." (Gemini planner).
4.  Lands in **Vault** — 4 tabs of artifacts, copy/download/share.
5.  Saves to **My Constellation** (history, each wish = star).
6.  Makes another wish or regenerates.

**Future (v2, out of scope):** Chat to refine ("add auth"), live preview, one-click deploy.

## 3. Scope — What Intara v1 *Does* and *Does Not* Do

### Does (4 Artifacts per wish, runnable but not deployed)

| Artifact | Output | Format | Example |
|---|---|---|---|
| **Schemas** | Tables + fields + types, validated | `schema.json` + `schema.prisma` (Prisma) + `supabase.sql` (migration) + Mermaid ER | `users {email:text, created_at:timestamp}` |
| **Frontend Code** | Vite React 18 + TS + Tailwind pages/components, typed, with API client | File tree `{path: content}` + syntax highlight + zip | `src/pages/Dashboard.tsx`, `src/components/TaskCard.tsx`, `src/api.ts` |
| **Backend Code** | FastAPI + Pydantic models, CRUD routes, error handling, CORS | File tree + `requirements.txt` + `.env.example` + `main.py` | `server/main.py`, `server/models.py`, `server/routers/tasks.py` |
| **Scroll (Spec)** | PRD, API spec, setup guide, citations | `README.md` + `openapi.json` (OpenAPI 3.0) + `PRD.md` + cites from `rag.py` | How to run, env vars, API table |

All artifacts bundled as `intara-{wishSlug}.zip` + shareable link `/wish/:id`.

### Does Not (v1, deferred)

*   No sandboxed `npm install && vite build` preview (v1 shows code, not running app) — saves free-tier cost. Placeholder "Preview coming soon" with static screenshot.
*   No auto-deploy to Vercel / GitHub push (button present but disabled with "v2").
*   No multi-stack choice (locked to **React + Vite + TS + Tailwind + FastAPI + Supabase + Prisma**). No Next.js, Vue, Firebase v1.
*   No real-time collaboration, billing, team workspaces.

## 4. Stack & Constraints (Free-Tier $0)

*   **Locked stack for generated code:** `Vite + React 18 + TypeScript + Tailwind` (FE) + `FastAPI 0.110.1 + Pydantic + Supabase` (BE/DB) — mirrors prototype `README.md:22` and your HR SaaS patterns. Template-driven, LLM fills gaps, not hallucinated infra.
*   **Free-tier infra for Intara itself:** 
    *   LLM: `Gemini 3.6-flash` (`GEMINI_MODEL` `server/.env.example`) free 60 RPM / 1500 RPD / 1M tokens/day — use `tenacity` retry `server/main.py:46`, debounce 350ms, 10 wishes/IP/day limit.
    *   Embeddings: `gemini-embedding-001` 3072d (`server/rag.py:34`) — **fix required:** migrate `docs.embedding vector(1536)` `supabase/schema.sql:17` → `3072`, truncate/pad logic already in `rag.py:37`.
    *   DB/Auth/Storage: Supabase Free (500MB, 50k MAU, RLS). Replace `allow all` `schema.sql:22` with `auth.uid()=owner`.
    *   Hosting: Vercel Hobby Free (FE) + Render Free (BE sleeps, ok for demo) or localhost `vite.config.ts:5` proxy.
    *   Preview: No server cost v1 (no sandbox). v2 uses WebContainers (browser, $0) not Docker.
*   **Quality gates:** `parse_json` guard `server/main.py:37` + repair prompt, `tsc --noEmit` on generated FE, `ruff` on BE, `openapi` validator.

## 5. Theme — Dark Nebula Glass

**Palette:** Background `#0a0a12` (near-black), nebula purple `#8B5CF6`, indigo `#6366f1`, star white `#f8fafc` at 60% opacity, glass `rgba(255,255,255,0.06)` + border `rgba(255,255,255,0.08)`, glow `0 0 40px rgba(139,92,246,0.4)`.

**Typography:** Display `Space Grotesk` (headings, planet lore), body `Inter` (existing `App.tsx:54` `fontFamily`), mono `JetBrains Mono` for code.

**Components:**
*   **Planet Orb** — `assets/planet-intara.png` (1024 transparent) — hero, pulsates on `loading` (`App.tsx:62` pattern), glow.
*   **Starfield** — `assets/starfield.jpg` (1920, tileable, low opacity 0.6).
*   **Wish Input** — centered glass card, glowing textarea `App.tsx:60` rethemed, placeholder "I wish for a...", example chips: "task tracker with users...", "blog with...", "booking system..."
*   **Vault Tabs** — 4 tabs with glyphs `assets/glyphs/*.png`: Schemas / Frontend / Backend / Scroll. Glass cards, syntax highlight (prism vs shiki).
*   **Constellation** — history view: each wish = star positioned by hash(prompt) on SVG `assets/constellation.svg`, hover shows prompt snippet.
*   **Motion:** Orb pulse 2s ease-in-out, tab switch fade 150ms, no heavy Three.js v1 (CSS only).

**Lore snippets (reuse in UI):**
*   "Intara listens from 3.7 light years away."
*   "Your wish drifts, Intara weaves stardust into schema."
*   "The planet has granted {n} wishes."
*   "Consult the archives" — RAG box `App.tsx:87` rethemed.

**Out-of-scope theming:** No 3D globe, no WebGL particles v1 — keep bundle <200KB.

## 6. Routes & Data Model

**Routes:**
*   `/` — Landing (planet + wish input + lore + recent wishes count + RAG ask)
*   `/wish/:id` — Vault (4 tabs, copy/zip/share, regenerate)
*   `/constellation` — My Wishes (grid or star map, search/filter, auth-gated)
*   `/archives` — RAG ask docs (reuses `askRag` `react-prompt-app/src/api.ts:15`)

**Supabase tables (extends `supabase/schema.sql`):**
```sql
-- existing: schemas, docs (keep for backward compat, or migrate)
-- new:
wishes (
  id uuid pk default gen_random_uuid(),
  owner uuid references auth.users,
  prompt text not null,
  prd jsonb not null, -- {appName, tagline, tables, pages, apis, auth}
  artifacts jsonb not null, -- {schema:{tables,prisma,sql}, frontend:{files}, backend:{files,requirements}, spec:{readme,openapi,cites}}
  status text default 'ready', -- weaving | ready | failed
  created_at timestamptz default now()
)
-- fix:
alter table docs alter column embedding type vector(3072);
-- RLS:
alter table wishes enable row level security;
create policy "owners full" on wishes for all using (auth.uid()=owner) with check (auth.uid()=owner);
create policy "public read demo" on wishes for select using (true); -- tighten later
```

**Types (FE):**
```ts
type Wish = { id:string, prompt:string, prd:PRD, artifacts:Artifacts, created_at:string }
type PRD = { appName:string, tagline:string, tables:{name:string, fields:{name:string,type:string}[]}[], pages:{name:string,route:string,components:string[]}[], apis:{method:string,path:string,desc:string}[], auth:boolean }
```

## 7. Generation Flow (No Deploy)

```
Wish text
 → POST /api/wish {prompt} (FastAPI, from main.py:53)
 → Planner LLM (Gemini, INTARA_PLANNER_PROMPT) → PRD json → validate → store wishes.prd (status weaving)
 → Parallel (3 LLM calls, guarded parse_json + repair):
     SchemaGen → {tables, prisma, sql}
     FrontendGen → {files: [{path, content}]} (template from App.tsx + api.ts patterns)
     BackendGen → {files, requirements.txt, openapi.json}
 → Assembler → artifacts jsonb + README.md + cites (rag.py:42 answer) → wishes.artifacts (status ready)
 → FE: Vault tabs render, jszip builds zip client-side
```

Each LLM call uses `call_gemini` `server/main.py:47` with `temperature 0.2` (`rag.py:54`), `parse_json` `main.py:37`, 1 repair retry.

## 8. Success Criteria (v1 Demo)

*   Wish "task tracker..." (`App.tsx:11`) → vault shows 2-3 tables, 3-5 FE files, 2-4 BE files, openapi + readme, all copyable, zip downloads and `unzip && npm install` works (tsc 0 errors).
*   Golden wishes (5) pass `docs/BENCHMARK.md` (build success 100%).
*   Free-tier: 10 wishes/IP/day, no 429 visible to user (queue + retry).
*   Lighthouse >90, bundle <200KB, works on mobile.

## 9. Future Roadmap

*   **v2:** WebContainers preview (in-browser `npm run dev`), chat diff iteration ("add dark mode"), GitHub push, Vercel deploy button.
*   **v3:** Multi-stack (Next.js, + auth templates), team workspaces, billing.
*   **v4:** Sandboxed Docker deploys, eval dashboard.

---

*This scope locks v1. Any change to artifacts, stack, or theme requires updating this doc first.*
