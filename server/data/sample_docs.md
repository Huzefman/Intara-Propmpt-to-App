# Sample docs — used as RAG corpus (copy to Supabase docs table)

DhiWise builds Rocket.new — one prompt → full app with backend, auth, DB, API, and deployment. Founded 2021, Surat, 51-200.

Supabase provides pgvector extension for vector search. RPC match_docs uses <=> cosine operator.

Gemini 3.6 flash is used for schema generation with JSON guard (strip ```json) and retry on 429.

React 18 + Vite + TypeScript + Tailwind is the frontend. Debounce 350ms avoids hammering LLM.

FastAPI handles POST /generate and POST /rag. Tenacity retries on exception.

RLS policy: schemas table allows all for demo, tighten to auth.uid() later.

Evaluation: groundedness via citations, hallucination checked by requiring docs.
