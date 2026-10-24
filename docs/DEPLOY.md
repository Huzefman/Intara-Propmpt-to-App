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
4. `supabase/migrations/013_user_llm_keys.sql` (required for BYOK; without it
   accounts still work on the shared pool and the Account page shows a setup
   warning)

> **012 deletes legacy owner-null wishes** (`delete from wishes where owner is
> null`) — that is the intentional cleanup of the old public demo rows. It also
> drops every public-read / open-write policy on wish content, adds
> `profiles`, `build_events`, and tightens storage writes.
>
> **013 is service-key only.** It stores encrypted per-account LLM keys, enables
> RLS with no policies, and never exposes the table to the browser.

Quick verification:

```sql
-- should list only the owner-only policies
select tablename, policyname from pg_policies
where tablename in ('wishes','wish_steps','wish_messages','wish_iterations','wish_components')
order by 1,2;

-- should return build_events
select to_regclass('public.build_events');

-- BYOK: should return user_llm_keys, RLS on, and zero policies
select to_regclass('public.user_llm_keys');
select relrowsecurity from pg_class where oid = 'public.user_llm_keys'::regclass;
select count(*) from pg_policies where tablename = 'user_llm_keys';
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
   - `KEY_ENCRYPTION_SECRET` — **recommended for BYOK.** Generate once with:
     `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
     If omitted, the server derives a key from `SUPABASE_SERVICE_KEY`; saved
     user keys then become unreadable if that service key is rotated.
   - one or more of `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`,
     `NVIDIA_API_KEY`, `DEEPSEEK_API_KEY` (the shared free pool)
   - `AUTH_REQUIRED=1`, `DAILY_BUILD_LIMIT=3` (already in the blueprint)
   - optional BYOK defaults: `BYOK_OPENAI_MODEL`, `BYOK_ANTHROPIC_MODEL`

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

## 4. Verify two accounts are isolated

1. Open the site → **Create account** as `a@…` → make a wish.
2. Copy the wish URL, then sign out.
3. Create account `b@…` → open **Constellation**: it must be empty.
4. Paste A's wish URL while signed in as B → **404** (not 403 — the API does
   not reveal that another account's row exists).
5. Sign back in as A → the wish is still there.
6. Approve 3 builds in a day; the 4th returns **429** with a reset notice.
7. Open **Account** as A → add a provider key → **Test before saving** →
   **Save**. The saved key is shown masked and the mode flips to **Your own
   key**.
8. Sign in as B → **Account**: zero saved keys and the shared pool. A's key is
   invisible (service-key table, RLS with no policies).
9. With A's key saved, start a build. It runs on A's key and does not increment
   the shared 3/day meter. If the key is bad, the build must fail with
   “Your saved LLM key could not complete this request” — it must never
   quietly fall back to Intara's shared pool.

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

## 5. BYOK — accounts bring their own LLM keys

The shared free pool remains the default (3 builds/day). A signed-in account
can add its own provider key on **Account** (`/account`) and build on it
without the shared quota.

### Supported providers

| Provider | Default model | Notes |
|---|---|---|
| Google Gemini | `GEMINI_MODEL` | Native Gemini API |
| OpenRouter | `OPENROUTER_MODEL` | One key for many models |
| Groq | `GROQ_MODEL` | Fast open models |
| NVIDIA NIM | `NVIDIA_MODEL` | OpenAI-compatible endpoint |
| DeepSeek | `DEEPSEEK_MODEL` | Native API |
| OpenAI | `BYOK_OPENAI_MODEL` (default `gpt-4o-mini`) | Chat Completions |
| Anthropic | `BYOK_ANTHROPIC_MODEL` (default `claude-3-5-haiku-latest`) | Messages API |
| Custom | user supplies | Any **public HTTPS** OpenAI-compatible API |

Model is optional except for Custom; blank uses the default above.

### How it behaves

- On save, the API encrypts the key with Fernet
  (`KEY_ENCRYPTION_SECRET`) and stores only ciphertext in `user_llm_keys`, one
  row per `(owner, provider)`.
- `GET /api/account` returns masked hints only. No endpoint returns plaintext.
- On a planning/build/chat call, if the account has any saved key, the gateway
  tries the most recently updated key first, then the next saved key. If all
  fail, the request fails with a clear error.
- **There is no fallback to the shared pool while a user key exists.** This
  prevents a dummy key from bypassing the quota and then spending Intara's
  budget. Remove all keys to return to shared mode.
- BYOK builds skip the 3/day shared meter. `build_events` is only written for
  shared-pool builds.
- Background tasks pin the key set at build/plan start, so changing or deleting
  a key mid-build does not switch pools halfway through.
- Embeddings for Archives still use the app's embedding key; BYOK covers the
  chat/planning/build generation calls.

### Add a key

1. Sign in → **Account**.
2. Pick a provider; paste the key; optionally set a model (required for
   Custom).
3. **Test before saving** makes a tiny live call. Then **Save key**.
4. The key appears masked with **Test** and **Remove** actions. **Test** on a
   saved key runs server-side; the plaintext never returns to the browser.
5. Remove the last key to return the account to the shared 3/day pool.

Endpoints (all require the account bearer token):

```
GET    /api/account
PUT    /api/account/keys/{provider}          {api_key, model?, base_url?}
DELETE /api/account/keys/{provider}
POST   /api/account/keys/test                {provider, api_key, model?, base_url?}
POST   /api/account/keys/{provider}/test     (tests the saved key server-side)
```

Key tests are capped at 20/hour/account.

### Custom endpoints

`base_url` must be a **public HTTPS** URL ending at the API root (usually
`.../v1`). The backend rejects `http://`, localhost, `.local`/`.internal`,
private/link-local IPs, and URLs with embedded credentials. This is an SSRF
guard, not a full egress proxy; keep the endpoint under your control.

### Secret rotation

- Changing `KEY_ENCRYPTION_SECRET` makes existing saved keys undecryptable
  (they are skipped; accounts fall back to shared mode and must re-enter keys).
- Set the secret once and keep it in Render. Do not regenerate it casually.
- Removing a key deletes the row; the ciphertext is gone.

---

## 6. Security model (what protects what)

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
  3/day per process. Accounts with a saved BYOK key bypass this meter.
- **BYOK storage:** keys are encrypted with Fernet before reaching Postgres
  (`user_llm_keys`), accessible only through the backend's service role, with
  RLS enabled and zero policies. The API returns masked hints only.
- **BYOK routing:** when an account has saved keys, the gateway uses only those
  keys (no silent shared fallback) and skips the shared quota. Background
  builds pin the key set at start. Key tests are rate limited; custom base URLs
  must pass a public-HTTPS SSRF guard.
- **Signup:** pre-confirmed (no email step, by product decision) and rate
  limited to 10 accounts/hour/IP. Treat this as a demo trade-off; add captcha
  or invite codes for real production.
- **Storage:** `intara-uploads` keeps public reads (preview images) but
  inserts/deletes now require a signed-in session.

---

## 7. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `401 Sign in to continue` | missing/mismatched `VITE_SUPABASE_URL`/`ANON_KEY`, or expired session; sign out/in |
| `503 Build metering is unavailable` | 012 not applied and the DB error isn't the missing-table fallback |
| `503 Could not record build usage` | same as above |
| `429 Daily build limit reached` | 3 shared builds used today (UTC); resets at midnight UTC |
| Account shows “Key storage is not set up” or save returns `503 … migration 013` | apply `013_user_llm_keys.sql` in the Supabase SQL editor, then restart Render |
| `Your saved LLM key could not complete this request` | provider rejected the key, the model id is wrong, or the provider is down. Open **Account → Test**, or remove the key to use the shared pool |
| “Could not load saved keys — try again” | transient DB/service-role error or `KEY_ENCRYPTION_SECRET` problem; check Render logs |
| `429 Too many key tests` | 20 test calls/hour/account; wait |
| Custom key rejected (`Base URL must…`) | use a public HTTPS URL ending at the API root; localhost/private IPs are intentionally blocked |
| Saved key disappears after a redeploy | `KEY_ENCRYPTION_SECRET` was changed (or the derived service key rotated); re-enter the key |
| `500 Could not create the account` | `SUPABASE_SERVICE_KEY` missing/wrong on Render |
| SSE connects then polling takes over | reverse proxy idle timeout; polling fallback is authoritative |
| Build dies when Render sleeps | free-tier spin-down mid-build; use a paid instance / uptime ping |
