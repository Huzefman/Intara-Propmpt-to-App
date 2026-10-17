# Architecture — Prompt → App (Whiteboard Version)

```
┌─────────┐     ┌─────────────────────────────────────────┐
│  Prompt │────▶│  Gemini 3.6  (research + schema + code) │
└─────────┘     └─────────┬───────────────────────────────┘
                          │ 1.1 Research market
                          │ 1.2 Decide features
                          │ 1.3 Design UI/UX (copy + layout)
                          │ 1.4 Generate tables/APIs
                          ▼
┌──────────┐    ┌──────────────────┐    ┌──────────────────┐
│  React   │◀───│  FastAPI / Node  │───▶│   Supabase       │
│  Vite    │    │  /generate       │    │  Postgres + RLS  │
│  Tailwind│    │  /rag            │    │  pgvector        │
└──────────┘    └────────┬─────────┘    └──────────────────┘
                         │ embed + match_docs
                         ▼
                 ┌──────────────────┐
                 │  Gemini answer   │
                 │  + citations     │
                 └──────────────────┘
                         │
                         ▼
                 ┌──────────────────┐
                 │  Deploy (Vercel) │
                 └──────────────────┘
```

### 10-min whiteboard script (say this)

> “I’d take the prompt, run a Gemini research pass to decide features, then a second pass to generate a JSON schema — tables, fields, types. I’d guard that JSON with a try/except and a repair prompt if it fails. I’d write it to Supabase with RLS (policy: user can read own rows). Frontend is Vite React — debounced input, fetch with loading/error, optimistic insert. For RAG I’d chunk docs to 400 chars, embed with text-embedding-3-small, store in pgvector, then at query time do `match_docs` cosine search top 5, then prompt Gemini with `Context + Q + Cite`. I’d eval groundedness by checking citations exist, and handle 429 with tenacity retry + streaming later if needed.”

### Key decisions to defend

- **Why pgvector vs Pinecone?** You know Supabase (43 Edge Functions) → no new infra, RLS same DB.
- **Why chunk 400?** Fits embedding window, balances recall vs noise. Overlap 50 optional.
- **Why guard JSON?** LLMs often wrap in ```json or add prose — you strip and retry.
- **Why debounce 350ms?** Avoids hammering LLM on every keystroke, still feels instant.
- **Failure modes:** Hallucination → citations, PII → RLS, rate limit → retry, bad schema → repair prompt.

### Tables

```sql
-- schemas: id, prompt, tables jsonb, created_at
-- docs: id, content, embedding vector(1536)
-- rpc match_docs(query_embedding, match_count) returns docs ordered by cosine
```

Draw this in interview — 5 boxes + DB. Done.
