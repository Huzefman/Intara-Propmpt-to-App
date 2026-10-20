# Deploy Intara with accounts — Supabase + Render + Vercel

Goal: **one Supabase project, many accounts.** The landing page and the 10
template apps are public. The Studio, Constellation, Archives and run pages
require an account, and every account only ever sees its own content.

```
Browser (Vercel) ──► FastAPI (Render) ──► Supabase (Postgres + Auth + Storage)
   anon key + JWT      service key           owner-scoped rows + RLS
```

Never put the **service role key** in Vercel or in the browser bundle.

---

## 1. Supabase

### 1a. Apply migrations (in order)

SQL editor → new query → paste the whole file → run:

1. `supabase/migrations/010_llm_calls_outcome_attribution.sql`
2. `supabase/migrations/011_fix_docs_embedding_dim.sql`
3. `supabase/migrations/012_accounts_isolation.sql`

> **012 deletes legacy owner-null wishes** (`delete from wishes where owner is
> null`) — that is the approved cleanup of the old public demo rows. It also
> drops every public-read / open-write policy on wish content, adds
> `profiles`, `build_events`, and tightens storage writes.

Quick verification:

```sql
-- should list only the owner-only policies
select tablename, policyname from pg_policies
where tablename in ('wishes','wish_steps','wish_messages','wish_iterations','wish_components')
order by 1,2;

-- should return build_events
select to_regclass('public.build_events');
```

### 1b. Auth settings

- **Authentication → Providers → Email:** "Confirm email" may stay ON —
  signup goes through the backend (`/api/auth/signup`) which creates a
  pre-confirmed user with the admin API, so accounts are instant either way.
  Turning it OFF also makes Supabase's own `signUp` instant (useful if you
  later add password reset / magic links).
- **Authentication → URL Configuration:**
  - Site URL: `https://<your-app>.vercel.app`
  - Redirect URLs: `https://<your-app>.vercel.app/**`
- **Project Settings → API:** copy the project URL, the **anon/publishable**
  key (frontend) and the **service_role** key (Render only).

---

## 2. Render — backend (FastAPI)

The backend cannot live on Vercel: builds are long-running background tasks.

### Blueprint (recommended)

1. Render → **New → Blueprint** → connect the repo.
2. `render.yaml` at the repo root creates `intara-api` with:
   - **Root Directory:** `server`
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Health check:** `/health`
3. Enter the secrets when prompted:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY` (service_role)
   - `SUPABASE_KEY` (anon/publishable — used by RAG reads)
   - one or more of `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`,
     `NVIDIA_API_KEY`, `DEEPSEEK_API_KEY`
   - `AUTH_REQUIRED=1`, `DAILY_BUILD_LIMIT=3` (already in the blueprint)

### Manual web service (alternative)

| Setting | Value |
|---|---|
| Root Directory | `server` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/health` |
| Python version | `3.12.8` (`PYTHON_VERSION`) |

Copy the public URL, e.g. `https://intara-api.onrender.com`.

**Free-tier caveat:** Render free web services spin down after ~15 minutes
without traffic, and a full build can run ~15 minutes. For reliable builds use
a paid instance or keep the service warm with an uptime ping. Background tasks
are in-process: if Render restarts mid-build, the boot sweeper marks orphaned
runs failed (artifacts already live in Supabase, so no disk is needed).

---

## 3. Vercel — frontend (React)

1. Import the repo; **Root Directory:** `react-prompt-app`.
2. Environment variables (Production **and** Preview):
   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_ANON_KEY` (anon/publishable — safe in the bundle)
   - `VITE_API_URL=https://<render-service>.onrender.com`
   - **Do not set `VITE_DEMO`** for the account app.
3. Deploy. `react-prompt-app/vercel.json` already pins the SPA rewrite, so
   `/auth`, `/constellation` and `/wish/:id` deep links work.
4. Optional: keep the fully-offline static demo as a **second** Vercel project
   (or a branch) with `VITE_DEMO=1` and no other env vars. It needs no backend
   and shows the 10 apps in-browser.

---

## 4. Prove two accounts are isolated

1. Open the site → **Create account** as `a@…` → make a wish.
2. Copy the wish URL, then sign out.
3. Create account `b@…` → open **Constellation**: it must be empty.
4. Paste A's wish URL while signed in as B → **404** (not 403 — the API does
   not reveal that another account's row exists).
5. Sign back in as A → the wish is still there.
6. Approve 3 builds in a day; the 4th returns **429** with a reset notice.

API-level check (optional):

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $TOKEN_A" \
  https://<render>/api/wishes          # 200
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $TOKEN_B" \
  https://<render>/api/wish/<A_WISH>   # 404
```

---

## 5. Security model (what protects what)

- **Identity:** Supabase Auth; the API accepts only `Authorization: Bearer
  <access_token>` and resolves the user server-side (never trusts a body/user
  id). Tokens are cached for 60 s per process.
- **Authorisation:** the backend holds the service key (bypasses RLS) so every
  query is explicitly scoped to `owner = jwt.sub`. Cross-account reads and
  writes return 404.
- **RLS:** owner-only policies remain as defense-in-depth for any future
  direct supabase-js reads.
- **Public surface:** `/health`, `/api/exemplars*` (template gallery),
  `/api/rag` (project docs) and `/api/auth/signup`. Everything else requires a
  session.
- **Build quota:** 3 builds per account per UTC day, metered in
  `build_events`; before 012 is applied an in-memory fallback still enforces
  3/day per process.
- **Signup:** pre-confirmed (no email step, by product decision) and rate
  limited to 10 accounts/hour/IP. Treat this as a demo trade-off; add captcha
  or invite codes for real production.
- **Storage:** `intara-uploads` keeps public reads (preview images) but
  inserts/deletes now require a signed-in session.

---

## 6. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `401 Sign in to continue` | missing/mismatched `VITE_SUPABASE_URL`/`ANON_KEY`, or expired session; sign out/in |
| `503 Build metering is unavailable` | 012 not applied and the DB error isn't the missing-table fallback |
| `503 Could not record build usage` | same as above |
| `429 Daily build limit reached` | 3 builds used today (UTC); resets at midnight UTC |
| `500 Could not create the account` | `SUPABASE_SERVICE_KEY` missing/wrong on Render |
| SSE connects then polling takes over | reverse proxy idle timeout; polling fallback is authoritative |
| Build dies when Render sleeps | free-tier spin-down mid-build; use a paid instance / uptime ping |
