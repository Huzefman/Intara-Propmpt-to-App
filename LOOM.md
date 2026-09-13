# 60-sec Loom Script — Say this word-for-word

> Record with screen share on `demo-hired/react-prompt-app` + `server/main.py` open. Keep to 60 sec.

---

**[0-10s] Hook**
“Hi, I’m Huzefa — B.Tech AI & DS, SCET. I built a miniature Rocket.new: prompt goes in, app comes out. I’ll show the three places I’d type in a live round.”

**[10-25s] React (show App.tsx)**
“I debounce the prompt 350ms to avoid hammering the LLM, then I call a guarded endpoint. I handle loading and error, and on success I do an optimistic Supabase insert and show the new schema in the list. That’s the 70 lines here — useState, useEffect with setTimeout cleanup, fetch with if(!res.ok) throw.”

**[25-45s] Backend (show main.py)**
“Backend is FastAPI. I prompt Gemini for JSON with a strict schema, then I guard it — strip ```json and regex the braces — if it still fails I do a repair call. Tenacity retries on 429. Then I insert into Supabase schemas table. That’s 65 lines.”

**[45-55s] RAG (show rag.py)**
“For RAG I chunk docs to 400 chars with 50 overlap, embed with text-embedding-004, store in pgvector, then at query I rpc match_docs cosine top 5, then synthesize with Context + Question + Cite. I keep citations to check groundedness.”

**[55-60s] Close**
“Deployed to Vercel + Supabase, eval is citation existence, and RLS is open for demo. Happy to rebuild any part live from scratch.”

---

### Tips

- Speak while typing, not after.
- If you forget, narrate the *why*: “I debounce because…”, “I guard JSON because LLMs wrap it…”.
- End with: “Want me to retype the debounce or the JSON guard from scratch?”
