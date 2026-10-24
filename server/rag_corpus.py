"""
Curated RAG corpus — the Intara Archives.

Each entry is one self-contained, citable fact block about the Intara project
(what it is, how it works, measured numbers, limitations). Entries are kept
short enough to embed whole (no mid-sentence chunking) and factual enough to
check against docs/RESULTS.md and the test suites.

Reseed with: python scripts/seed_rag.py
"""
from __future__ import annotations

PROJECT_DOCS: list[str] = [
    # — What it is ————————————————————————————————————————————————
    "Intara is a prompt-to-app generator built on one bet: LLMs should not write your app code — they should write small, typed, validated JSON App Specs, and a tested engine should execute them. Code is an export target, not the product.",
    "Intara's spec-first architecture means the language model never runs at runtime: a deterministic TypeScript engine executes the validated App Spec (data, screens, roles, formulas, automations) in the browser, so behavior is reproducible and statically tested.",
    "You use Intara by describing an app in plain English (a wish), e.g. 'a task tracker with roles, deadlines and a board view'. The pipeline turns that wish into a validated App Spec, and the runtime renders it as a working app with seeded sample data.",
    "Intara was built by Huzefa Mandviwala (B.Tech AI & DS, SCET Surat), MIT licensed, at github.com/Huzefman/Intara-Propmpt-to-App. The architecture, gates, eval methodology and quota strategy are documented in the repository, and every number is measured by tests in the repo.",

    # — Pipeline ————————————————————————————————————————————————
    "The Intara build pipeline runs staged agents S0 through S6: S0 intake, S1 clarifier (may ask questions), S2 modeler (entities, fields, relations), S3 designer (pages and the role set), S4 logic (transition/automation/formula rules), S5 assembler + critic (gates), S6 seed data.",
    "Every Intara pipeline stage emits typed JSON validated against a schema, with bounded repair loops of at most 2 attempts at cooling temperature. A failed parse gets one capped repair call; quota errors (HTTP 429) never burn a repair attempt.",
    "Intara's gates are fail-closed: G0 schema validation (one JSON Schema generates both the Pydantic and TypeScript types, with a drift check), G1 a semantic lint of 50 rules (R01–R50), G2 requirement coverage, G3 generated engine tests, and G4 render smoke.",
    "Every Intara fallback carries a fallback_reason that propagates from generator to step to artifact to the Studio badge — and counts as a failure in live evals. There is no silent fallback: a fallback that isn't loud is treated as a bug.",
    "Intara's run engine is durable: budgets, content-addressed artifacts, and resume-after-crash by run id. An integration test kills a run mid-build, restarts the process, and proves the sweep-and-retry completes with zero repeated per-step LLM calls.",

    # — Runtime ————————————————————————————————————————————————
    "The Intara runtime executes an App Spec as a real app: tables, kanban boards, calendars, charts, filters, forms, record detail views, lifecycle transitions, notifications and automations — all in the browser, backed by IndexedDB (Dexie) in the static demo.",
    "Intara roles and access are part of the spec: the S3 designer declares the role set, the S4 logic stage must reference a subset of those roles, and the runtime evaluates permissions per screen, per action and per transition through the engine's can() contract.",
    "Intara's formula language is hand-written — tokenizer plus recursive-descent parser — in both Python and TypeScript, with no eval or exec anywhere. It supports arithmetic, comparisons, boolean logic, field refs, and functions like if, sum, count, min, max, avg, len, today and dayShift.",
    "The formula engine is verified with 135 shared conformance cases that both the Python and TypeScript implementations must pass, plus a 500-input fuzzer where only FormulaSyntaxError or FormulaError may escape — the process can never crash on hostile input.",
    "Intara spec edits are RFC 6902 JSON patches with invert() for undo and a version tree for history. The invert logic is validated by randomized fuzzing: 1,175 of 1,175 apply → invert → apply round-trips return the original document.",
    "Intara models reverse relations: a record's related rows (e.g. a project's tasks) are computed by scanning ref fields that target the record's entity, and computed/formula fields fill in dependency order — leaves first, then per-record aggregates.",

    # — Measured numbers ————————————————————————————————————————
    "Intara's golden-wishes eval (python scripts/eval.py --mocked) checks 5 wishes against 6 binary metrics each: valid JSON, schema completeness, frontend TypeScript build, backend parse plus ruff lint, OpenAPI shape, and citations. It passes 5/5 and runs free in CI.",
    "Intara's core20 live eval runs 20 fixed wishes end-to-end against free-tier providers. Progression: 4/20 → 13/20 → 17/20 (the 85% accept bar), with a median of 9 LLM calls per build (budget ≤14) and median wall time of about 4.4 minutes, throttled by free-tier quota.",
    "Intara reports its tuned number next to a held-out number: on 5 domains never used for tuning (invoicing, gym memberships, helpdesk, restaurant orders, school fees) the result was 3/5 green — honest generalization, not just the tuned 17/20.",
    "Intara's test suites total roughly 470 automated tests: 267 Python tests (pytest, including TypeScript-twin formula and runtime suites run through Node) and 206 Node tests passing with 1 environment-skip.",
    "Intara has 10 curated gold App Specs in its gallery: BookWell (appointments), PipeDrive Lite (CRM), ClubConnect (school clubs), GardenPlan (gardening), Stockroom (retail inventory), TimeOff (HR leave), TaskFlow (task management), FixIt (repair shop), Page Turners (book club), PawCare (veterinary clinic).",

    # — Failure stories (the interesting ones) ——————————————————
    "Intara's first baseline eval looked fine from outside — 10 of 20 wishes 'succeeded' — but every one of the 10 full plans had silently fallen back to a mock PRD because the LLM's JSON envelopes were malformed. The true parse rate was 0 of 10 full plans.",
    "Intara fixed the 0-percent parse failure with a parse ladder: strip code fences, extract the root braces, detect truncation, then make exactly one capped repair call — plus structured-output (json_mode) wiring and the fail-closed fallback_reason rule. The rerun parsed 15 of 15 full plans with zero fallbacks.",
    "Intara's eval-overfitting lesson: core20 is a fixed prompt set, so fixing its failures makes the number partly overfit. The honest check is held-out domains never tuned for — 3/5 — and both numbers belong next to each other or neither means anything.",
    "The 'hollow resume' bug in Intara: resumed builds replayed steps as done, but step rows stored file paths while content lived in process memory, so a killed build could finish with empty artifacts. Fix: a content-addressed artifact store, restore by hash, and store failure must fail the step — never a hollow persist.",

    # — Free-tier reality ————————————————————————————————————————
    "Intara runs on a chain of free-tier LLM providers: Gemini primary, then OpenRouter, Groq and Nvidia (DeepSeek optional), chosen by whichever has quota. Quota-exhausted providers get a cooldown and the call falls through to the next provider automatically.",
    "Telemetry from 429 live calls shows how free-tier works in practice: 62% of calls succeeded only after burning an earlier provider, and 85% of those burn-outs were quota (HTTP 429) errors — the dominant failure class is capacity, not model quality.",
    "Provider latency in Intara's telemetry is bimodal: Groq (gpt-oss-20b) at about 8 seconds median per call versus Nvidia's Nemotron reasoning model at about 76 seconds median (up to 336 seconds) — which provider wins decides whether a build takes 2 or 8 minutes.",
    "About 17.5% of Groq calls in Intara's telemetry hit finish_reason length (truncated JSON output) — JSON truncation is a routine occurrence there, which is why the parse ladder's truncation detection and capped repair call are load-bearing.",
    "Intara records per-call LLM telemetry (llm_calls table): provider, model, tokens, latency, finish reason, and parse outcome — prompts are never stored. The telemetry is analysed in notebooks/telemetry.ipynb.",

    # — Limitations (stated, not hidden) ————————————————————————
    "Intara's stated limitations: free-tier quota dominates failures (roughly half of observed live failures are quota-shaped; a paid key removes that class); role-coherence mismatches fail closed with specific errors and no automatic repair; and one uvicorn worker means a heavy build can stall /health.",
    "More Intara limitations: there is no hosting or publish path inside the app (the spec preview and the downloadable code zip are siblings, not the same artifact), email is intent-only, and there has been no human user-acceptance testing yet — the eval numbers are lab numbers, stated as such.",
    "Intara's current limits: accounts are single-owner with no teams, sharing or cross-account collaboration; there is no hosting or publish path; email is intent-only; and free-tier provider capacity dominates live failures. The engineering claim remains testable: validated specs, fail-closed gates, measurable evals, and honest documentation of what fails.",

    # — Accounts, keys and deployment ————————————————————————————
    "Intara's public deployment has per-account workspaces: instant email/password signup, one owner per app, no teams or sharing. The landing page and the ten template demos are public; wishes, builds, runs, archives, Constellation and statistics require a session.",
    "Intara enforces account isolation twice: the FastAPI backend verifies the Supabase bearer JWT and scopes every query to that user, while Postgres row-level security independently restricts wishes, profiles and related rows. The browser's anon key cannot read another account's rows; the service key is server-side only.",
    "Intara's shared free LLM pool allows 3 builds per account per UTC day, recorded in build_events and reset at midnight UTC. The counter is durable in Supabase; a missing metering table fails closed with HTTP 503 rather than silently allowing unlimited builds.",
    "Intara supports bring-your-own-key (BYOK) per account: keys are Fernet-encrypted at rest in user_llm_keys, masked in API responses, and never returned to the browser. Saved keys are tried first; if a BYOK call fails, the build fails with an explicit error and never silently falls back to Intara's shared keys. A BYOK account bypasses the 3/day shared quota.",
    "Intara's live deployment is free-tier: React/Vite frontend on Vercel, FastAPI backend on Render, Supabase Postgres/Auth/pgvector. The same repository builds the static template demo with VITE_DEMO=1; account mode leaves VITE_DEMO unset so Studio routes are gated.",
    "The template gallery's demo data is browser-local and session-scoped: each account and browser tab gets its own IndexedDB namespace, seeded from a reviewed App Spec. Edits such as adding an appointment in BookWell survive a reload in that tab but are never written back to the shared template or visible to another account.",
    "Intara's public health endpoint reports only liveness and Supabase connectivity; provider names, model IDs, quota details and account identifiers are kept server-side.",

    # — How to run it ————————————————————————————————————————————
    "Run Intara's static demo with zero backend: cd react-prompt-app, npm install, then VITE_DEMO=1 npm run build and npm run preview — it bundles 10 gold apps that run fully in the browser (IndexedDB, no network calls, no keys).",
    "Run the full Intara Studio locally: in server/ install requirements and start uvicorn main:app --port 8000 (keys optional — without them the planner uses a deterministic mock and the eval still passes), then npm run dev in react-prompt-app and open localhost:5173.",
    "Intara's CI is GitHub Actions: a Python job (3.12) runs the pytest suite including TypeScript-twin suites via pinned Node 24, then the mocked golden eval; a web job runs the runtime Node test suite, both typechecks, and the VITE_DEMO=1 production build.",
    "The Intara Studio flow: type a wish → the S1 clarifier may ask questions → approve the blueprint → the staged pipeline builds (visible progress via SSE) → preview the running app in the browser → iterate by chat (spec patches) or export the runnable zip.",

    # — This archives feature itself (meta) ————————————————————
    "These archives answer questions about the Intara project itself: docs are retrieved from Supabase pgvector (match_docs cosine, top 5) after embedding the question, with a lexical BM25 fallback when embedding providers are unavailable — the retrieval mode is labelled in every answer.",
    "The Intara archives synthesize answers with whichever free provider has quota (the same fallback chain the builds use), grounded strictly in retrieved project documentation, with numbered citations — and say 'not in the archives' instead of inventing facts.",
    "Intara's stack: FastAPI + Python backend (Pydantic, staged agents), React 18 + TypeScript + Vite frontend, a framework-free TypeScript spec runtime package, Supabase (Postgres + pgvector + RLS) for persistence and telemetry, and Vercel for the frontend and static template demo.",
]
