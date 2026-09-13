# Prompt → App + RAG — Mini Rocket.new

> Tiny **Prompt → Full-stack App + RAG** — 257 lines total. Built to practice the *exact* stack DhiWise uses for `Rocket.new`: React + Supabase + Gemini.

![Demo](https://img.shields.io/badge/demo-live-black) ![React](https://img.shields.io/badge/React-18-149eca) ![FastAPI](https://img.shields.io/badge/FastAPI-Python-009688) ![Gemini](https://img.shields.io/badge/Gemini-3.6-8B5CF6) ![Supabase](https://img.shields.io/badge/Supabase-pgvector-3fcf8e)

```
Prompt --(Gemini)--> Research --> Schema (Supabase) --> React UI --> Deploy
                      └─ RAG (pgvector) → answer with citations
```

### What it is

A miniature **Prompt to App**. Type *“A task tracker with users, tasks, and due dates”* → Gemini generates `{tables: [{name, fields}]}` → saved to Supabase (`schemas` table) → React shows it. Second box is **RAG over docs**: chunk → embed → `pgvector` cosine → synthesize with citations.

Built for **live practical interviews** — every line is something you type in 60 minutes (not a black-box clone).

### Stack

- **Frontend:** Vite + React 18 + TypeScript + Tailwind — debounced input (350ms), loading/error, optimistic Supabase insert
- **Backend:** FastAPI + `google-genai` (Gemini-3.6-flash) + Tenacity retry — guarded JSON parsing (`strip ```json` + regex), 429 retry
- **DB:** Supabase Postgres + `pgvector` + RLS — single table `schemas` + `docs` + RPC `match_docs`
- **AI:** Gemini `generate_content` (schema) + `embed_content` (`text-embedding-004`, 1536d) + Supabase `vector <=>`

### Quick Start

```bash
# 1. Frontend
cd react-prompt-app
npm install
cp .env.example .env  # add VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY
npm run dev            # http://localhost:5173

# 2. Backend
cd ../server
pip install -r requirements.txt
cp .env.example .env   # add GEMINI_API_KEY + SUPABASE_URL + SUPABASE_KEY
uvicorn main:app --reload --port 8000  # http://localhost:8000/docs
```

Supabase setup (once):

```sql
-- Run supabase/schema.sql in SQL editor
-- creates tables schemas, docs + vector + RPC match_docs + RLS
```

Seed docs for RAG:

```bash
python -c "from rag import seed_docs; seed_docs()"
```

### Structure

```
react-prompt-app/
  src/App.tsx      — 70 lines (useState, debounce, fetch, Supabase)
  src/supabase.ts  — 15 lines
  src/api.ts       — 25 lines
server/
  main.py          — 65 lines (POST /generate, POST /rag)
  rag.py           — 45 lines (chunk 400 + embed + pgvector + cite)
  data/sample_docs.md
supabase/schema.sql — 18 lines
architecture.md     — whiteboard you draw in interview
LOOM.md            — 60-sec narration word-for-word
```

### 60-min Interview Script

**0–5m:** “I’ll debounce the prompt, call a guarded LLM endpoint, persist to Supabase. For RAG I’ll chunk → embed → vector search → cite.”

**5–25m:** Type `App.tsx` — `useState` → `useEffect` debounce → `fetch('/api/generate')` → `supabase.from('schemas').insert()`.

**25–45m:** Type `main.py` — `FastAPI` → `genai.Client` → `parse_json` guard → `supabase.insert` → `@retry` on 429.

**45–55m:** Type `rag.py` — `chunk(text,400)` → `embed` → `supabase.rpc("match_docs")` → `prompt = f"Context:\n{docs}\nQ: {q}"` → `generate_content`.

**55–60m:** Whiteboard: 5 boxes `Prompt → Gemini → FastAPI → Supabase → React` + RAG loop. Mention eval (groundedness via citations).

### Why this works

- Mirrors **Rocket.new**: prompt → research → UI → code → DB/auth/API → deploy
- Shows **LLMOps**: JSON guard, retry, pgvector, citations, RLS — not just a demo
- Reuses real patterns from HR SaaS (43 Edge Functions + RLS) and Gemini video pipeline

---

Built by **Huzefa Mandviwala** — B.Tech AI & DS, SCET Surat (CGPA 9.61) — Jan 2027 internship loop.  
*This is a learning scaffold, not a DhiWise clone — built to practice primitives you type live.*
