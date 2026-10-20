# Deploy the static demo — exact steps (GitHub rename → Vercel)

> **Deploying the account-based app instead?** Follow
> [`DEPLOY_ACCOUNTS.md`](./DEPLOY_ACCOUNTS.md) (Supabase migrations + Render
> backend + Vercel frontend). This file covers only the fully-offline static
> demo (`VITE_DEMO=1`), which remains a useful portfolio fallback and needs no
> backend, keys, or database.

> Do this once. Everything below is user-side; nothing here needs the backend,
> keys, or a database. The goal: a public URL that shows the 10 gold apps
> running fully in the browser (`VITE_DEMO=1`, zero network calls after load).

Current state: repo is `github.com/Huzefman/prompt-to-app` (private). The demo
code already links to the *future* URL `github.com/Huzefman/intara`
(`react-prompt-app/src/demo.ts`), so the rename below is the expected step.

---

## A. GitHub — rename to `intara` and make public

1. Open **https://github.com/Huzefman/prompt-to-app/settings**
2. Under **General → Repository name**, change `prompt-to-app` → `intara`, click **Rename**.
   *(GitHub keeps a redirect from the old name, so nothing breaks if the old URL is cached somewhere.)*
3. Update the local remote and push:

   ```bash
   git remote set-url origin https://github.com/Huzefman/intara.git
   git push
   ```

4. **Make it public:** Settings → **General** → scroll to **Danger Zone** →
   **Change repository visibility** → **Make public** → type the repo name to confirm.

   Secrets sanity check (already done, pass 1): full-history gitleaks scan found
   only false positives (seed invite tokens in example specs). No real credentials
   were ever committed — `.env` files were never tracked. Safe to publish.

## B. Vercel — import and deploy

1. Go to **https://vercel.com** → sign in **with GitHub** (Huzefman account).
2. **Add New… → Project** → import the repository **`Huzefman/intara`**.
3. On the configure screen set exactly this:
   - **Root Directory:** `react-prompt-app` *(click Edit, pick the folder)*
   - **Framework Preset:** `Vite` (auto-detected; if not, pick it)
   - **Build Command:** leave default (`npm run build`; the committed
     `react-prompt-app/vercel.json` pins install/build/output + SPA routing)
   - **Environment Variables:** `VITE_DEMO=1` — tick **Production** and **Preview**
   - **Node.js version:** leave default (24.x)
4. Click **Deploy**. First build takes ~1–2 minutes.
5. Copy the production URL (something like `https://intara-abc123.vercel.app`).

*No other env vars or keys are needed — the static demo is zero-backend by design.
The FastAPI backend stays local-only; never put `GEMINI_API_KEY` etc. in Vercel.*

## C. Verify the deployment

- Open the URL: landing page shows the demo panel (“This is the static demo…”).
- Click **Open the 10 live apps** → all 10 cards render → open TaskFlow →
  board loads, drag a card, switch role, open Export CSV.
- Direct-link check: open `<URL>/templates` in a fresh tab — it must load
  (that’s the `vercel.json` SPA rewrite working, not a 404).

## D. Land the URL in the repo

Send the production URL back and it gets wired into:

1. `README.md` — replace the “▶ Live demo: deployment pending” line.
2. `docs/process/DEMO_SCRIPT.md` — reference for the video recording.

*(Or do it manually — both files contain the literal string `deployment pending`
/ `once deployed` near the top.)*

## Troubleshooting

- **Build fails on `tsc`:** the Studio type-checks before `vite build`; run
  `npm run build` locally first — it’s green on the pinned lockfile (`npm ci`).
- **`/templates` 404s:** `react-prompt-app/vercel.json` wasn’t picked up —
  confirm the Root Directory is `react-prompt-app` and redeploy.
- **Blank page:** check the browser console; the demo must make **zero** network
  calls. If it calls `/api`, `VITE_DEMO=1` wasn’t set at build time.
