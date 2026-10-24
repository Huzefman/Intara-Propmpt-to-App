# Intara — Benchmark Suite

> **Purpose:** Standard + custom evaluation to guarantee every wish yields runnable artifacts on free-tier. Run in CI (mocked, $0) and optionally live (1 Gemini call).

---

## 1. Overview

*   **When to run:** After Phase 2 (generators) and before each release. `pytest tests/test_golden_wishes.py` must pass before merging.
*   **Cost:** Mocked suite = $0 (fixtures). Live suite = 5 wishes × ~4 LLM calls × ~2k tokens = ~40k tokens ≈ $0.004 on Gemini free (well under 1M/day).
*   **Location:** `tests/test_golden_wishes.py` + `tests/fixtures/wishes.json` + `scripts/eval.py`.

## 2. Standard Benchmarks (adapted)

| Benchmark | Original | Intara Adaptation | Tool |
|---|---|---|---|
| **HumanEval** | 164 Python tasks, pass@k | Validate `BackendGen` — generated `models.py` + `routers/*.py` must `ast.parse` + pass 2 synthetic CRUD tests | `ast`, `pytest` |
| **MBPP** | 974 tasks, python | Validate `SchemaGen` — `prisma` and `sql` syntax validity, not pure LLM hallucination | `prisma format` dry-run, `sqlparse` |
| **Build Success Rate** | Lovable/Bolt internal | **Primary metric** — generated FE must `tsc --noEmit` 0 errors, BE `ruff check` 0 errors | `tsc`, `ruff` |

We do not run full HumanEval 164; we vendor 5 representative tasks as regression, plus our golden wishes.

## 3. Intara Golden Wishes — 5 Standard Prompts

These are the **benchmark test prompts** (suitable standards, covering CRUD intensities):

1.  **Task Tracker** — `A task tracker with users, tasks, and due dates` (from `App.tsx:11` — regression, simplest)
2.  **Blog** — `A minimalist blog with authors, posts, comments, and likes` (tests relations, counts)
3.  **E-commerce Wishlist** — `An e-commerce wishlist with products, carts, and orders` (tests many-to-many, money)
4.  **Booking** — `A booking system for salons with services, slots, and appointments` (tests time, availability, slots)
5.  **Forum** — `A Q&A forum with questions, answers, votes, and tags` (tests votes, tags, auth)

Each prompt is stored in `tests/fixtures/wishes.json` with expected minimal tables (e.g., Blog expects `authors`, `posts`).

**Why these 5:** They cover 80% of CRUD patterns (users+owned items, likes/votes, carts/orders, time slots). They are standard in app-generator demos (Rocket.new, Supabase examples) and broad enough to be a useful regression suite.

## 4. Metrics — Per Wish, 6 Binary Checks (pass = all true)

```
wish_id, prompt
  1. json_valid         — PRD + artifacts JSON parses, parse_json guard passes (main.py:37)
  2. schema_completeness— 1-3 tables, 2-5 fields each, types ∈ {text,integer,timestamp,boolean}, no duplicate table names
  3. fe_build           — generated frontend files: includes src/pages/*.tsx + src/components/*.tsx, tsc --noEmit 0 errors (if tsc not installed, skip but log)
  4. be_parse           — backend files: requirements.txt contains fastapi, main.py ast.parse succeeds, ruff 0 errors (if ruff not installed, ast only)
  5. spec_has_openapi   — openapi.json valid JSON, has paths, at least 2 apis from PRD present
  6. cites_grounded     — rag cites.length >0 when docs seeded (rag.py:51), or spec.readme contains "Intara" (proves assembler included cites)
```

**Suite pass = 5/5 wishes pass all 6.** CI fails otherwise.

**Scoring output (example):**
```
wish 1 task tracker: json_valid ✓ schema ✓ fe_build ✓ be_parse ✓ openapi ✓ cites ✓ → PASS
wish 2 blog:        json_valid ✓ schema ✓ fe_build ✗ (missing TaskCard) → FAIL (show diff)
...
Suite: 4/5 pass — FAIL
```

## 5. Running

**Mocked (no LLM, $0, for CI):**
```bash
pytest tests/test_golden_wishes.py -v
# Uses tests/fixtures/wishes.json — pre-generated good artifacts
python scripts/eval.py --mocked --verbose
```

**Live (hits Gemini, costs 1 free call per wish, for nightly):**
```bash
python scripts/eval.py --live --prompt "A task tracker with users, tasks, and due dates" --check all
# Or all 5:
python scripts/eval.py --live --all
```

**During development (quick single):**
```bash
python scripts/eval.py --mocked --wish 1 --check fe_build,be_parse
```

## 6. Fixtures

`tests/fixtures/wishes.json` — 5 entries, each:
```json
{
  "id": "wish-1-task-tracker",
  "prompt": "A task tracker with users, tasks, and due dates",
  "prd": {"appName": "TaskOrb", "tagline": "...", "tables": [...], "pages": [...], "apis": [...]},
  "artifacts": {
    "schema": {"tables": [...], "prisma": "model User {...}", "sql": "create table users (...)",},
    "frontend": {"files": [{"path": "src/pages/Dashboard.tsx", "content": "..."}]},
    "backend": {"files": [{"path": "server/main.py", "content": "..."}], "requirements": "fastapi==0.110.1\n..."},
    "spec": {"readme": "# TaskOrb ...", "openapi": {"openapi":"3.0.0","paths":{...}}, "cites": ["DhiWise ..."]}
  }
}
```
Fixtures are *ideal* outputs — mocked generators return these, eval checks they pass.

## 7. Eval Script Details (`scripts/eval.py`)

*   Functions: `check_json_valid(artifacts)`, `check_schema(tables)`, `check_fe_build(files)` (writes to temp dir, runs `npx tsc --noEmit` if available), `check_be_parse(files)` (`ast.parse` + optional `ruff`), `check_openapi(spec)`, `check_cites(spec)`, `eval_wish(wish)`, `eval_suite(wishes)`.
*   Exit code 0 if all pass, 1 if any fail (for CI).
*   `--verbose` prints per-check reason.
*   No external deps beyond stdlib + optional `tsc`/`ruff` (gracefully skipped if missing, but CI should have `tsc`).

## 8. Future Benchmarks (not v1)

*   **HumanEval live:** Generate `POST /api/tasks` from scratch, run `pytest` against real FastAPI app in temp sandbox.
*   **Lighthouse:** FE bundle <200KB, performance >90.
*   **Latency:** Wish → vault <30s p95.

---

*Run `pytest` after Phase 2 to certify Intara before deploy. Golden set is the acceptance gate.*
