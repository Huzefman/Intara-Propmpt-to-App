# Intara Lore — Planet of Wishes

Intara is a fictional planet 3.7 light years beyond the heliopause, where every software wish drifts across space and is heard. Its obsidian oceans shimmer with violet auroras, and its atmosphere weaves stardust into schemas.

## The Weaving

When a maker whispers "I wish for a task tracker...", the wish travels as a photon packet to Intara. The planet listens, then forges four artifacts:
- **Schemas** — tables, Prisma schema, Supabase SQL (the bones)
- **Frontend** — Vite React + TypeScript + Tailwind pages and components (the skin)
- **Backend** — FastAPI + Pydantic, CRUD routes, requirements.txt, OpenAPI (the breath)
- **Scroll** — PRD, README, API spec, and cites from the archives (the story)

## Stack

Intara forges only with a locked stack to stay free and runnable: Vite + React 18 + TypeScript + Tailwind (frontend), FastAPI + Pydantic (backend), Supabase Postgres + pgvector + RLS (database), Prisma (schema). Deployed on Vercel hobby, Gemini free tier.

## Constellation

Each wish becomes a star in the constellation map. Hash the wish id to place it, hash appName for size. Together they form the Intara sigil.

## Archives

The archives are RAG over docs: chunk 400 chars + 50 overlap, embed with gemini-embedding-001 (3072d), pgvector match_docs cosine via `<=>`, synthesize with Context + Q + Cite. Cites prove groundedness.

## Philosophy

Intara does not deploy in v1 — it grants artifacts, not hosting. The maker runs `npm install && npm run dev` and `uvicorn main:app --reload`. v2 will add WebContainers preview, chat to refine, GitHub push, Vercel deploy.

Wishes are rate-limited 10 per IP per day to stay on Gemini free 1500/day.
