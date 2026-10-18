# Intara — Results write-up

> One page, real numbers, measured by this repo's evals. Run them yourself:
> `python scripts/eval.py --mocked` (free) · `python scripts/core20.py --live` (costs free-tier quota).
> Raw reports: `evals/reports/`. All fallbacks count as failures (fail-closed eval).

## The headline numbers

| Run (date) | What | Result |
|---|---|---|
| Baseline (2026-10-12) | 20 wishes, plan stage | 10/20 "success" — but **0 of 10 full plans actually parsed**; the other 10 fell back to the mock PRD (silently) |
| Rerun (2026-10-12) | same 20, after the parse ladder | **20/20 success · 15/15 full plans parsed · 0 fallbacks** |
| core20 run 1 (2026-10-13) | 20 wishes, live, end-to-end | **4/20** G0/G1 green |
| core20 rerun 1 (2026-10-14) | after failure-taxonomy fixes | **13/20** |
| core20 final (2026-10-15) | after fix batch 2/3 | **17/20 (85% — the accept bar)** · median 9 LLM calls (budget ≤14) · median 4.4 min wall (target ≤3 min, quota-throttled) · diversity 12 combos, 0.028 entity overlap |
| Held-out domains | 5 domains never used for tuning | **3/5 green** (invoicing, gym memberships, helpdesk; restaurant orders and school fees failed) |
| Unit suites (2026-10-17) | pytest / node | **201/201** · **206 pass** (+1 env-skip) |
| Adapter contract | memory / Dexie / live Supabase | 12/12 · 12/12 · **6/6 live** (scratch app, zero residue) |

## The three failures worth talking about

### 1. Silent template fallbacks hid a 0% parse rate

The first baseline looked *fine* from the outside: 10 of 20 wishes "succeeded". Reading the metadata showed all 10 were clarify-path responses — and **every one of the 10 full plans had fallen back to a mock PRD** because the LLM's JSON envelopes were malformed or truncated. The product reported success while doing none of the requested work. That's the worst kind of bug: a green dashboard over a dead pipeline.

**Fix:** a parse ladder (strip code fences → root-brace extraction → truncation detection → **one** capped repair call), `json_mode` structured-output wiring at all 17 JSON-expecting call sites, and — most importantly — fail-closed semantics: every fallback carries a `fallback_reason` that propagates generator → step → artifact → Studio badge, and counts as a failure in evals. The rerun parsed 15/15 full plans with zero fallbacks.

**Lesson:** if a fallback isn't loud, it isn't a fallback — it's a lie.

### 2. Eval overfitting (and how we measured it)

core20 is 20 fixed prompts. When run 1 came back 4/20, I categorised every failure (role mismatches, unreachable pages, kanban group-by, quota deaths, empty responses) and fixed the *classes*, not the symptoms: S3-declares/S4-subset role contract, reachability gates, formula `&&`/`||` aliases, id-text rules. Rerun 1 jumped to 13/20; batch 2/3 landed 17/20.

But fixing bugs against a fixed set means the tuned number is part overfit. The honest check is **held-out domains — prompts never tuned for: 3/5**. Both numbers are small samples, and roughly half of live-run failures are quota-shaped (free-tier daily caps), so a paid key would move these numbers again.

**Lesson:** report the tuned number *next to* the held-out number, or neither means anything.

### 3. The "hollow resume" bug

The run engine is resumable by design, and the first version *looked* resumable: after a crash, done steps were replayed as done. But `wish_steps` only stored file *paths* — content lived in process memory. A killed build would "resume", report green steps, and finish with empty artifacts. Hollow resume: the state machine was right, the data model lied.

**Fix:** content-addressed artifact store (`artifact_contents`), resume restores real bytes by content hash (`step_restored`), store failure **fails the step** (never a hollow persist). Kill-resume is now an integration test: crash mid-wiring → fresh process → sweep → retry completes `ready` with **zero repeated per-step LLM calls**.

**Lesson:** durability is not "does it resume?" but "are the bytes the real bytes?"

## Telemetry analysis (the data-science angle)

429 live calls logged to `llm_calls` (2026-10-12 → 16), analysed in
[`notebooks/telemetry.ipynb`](../notebooks/telemetry.ipynb):

- **62% of calls (265/429) succeeded only after burning an earlier provider** — and 85% of those burn-outs were quota/429s, not model quality. The fallback chain *is* the production path on $0.
- **Latency is bimodal:** Groq ~8 s median vs Nvidia ~76 s (reasoning model, max 336 s) — which provider wins decides whether a build takes 2 or 8 minutes.
- **17.5% of Groq calls truncate** (`finish_reason: length`) — JSON truncation is routine, which is why the parse ladder's truncation detection + capped repair call is load-bearing.
- **A schema gap found while analysing:** parse outcomes were tracked per *stage*, never per *call* → fixed with row-id attribution (migration 010 grants update on exactly `parse_outcome, repair_used`); historical rows stay NULL by design.

Regenerate with: `python scripts/export_llm_calls.py` → re-run the notebook.

## What the pipeline still fails at (standing, documented)

- **Free-tier quota** shapes roughly half of observed live failures — labelled, retried across providers, still there. A paid key removes this class outright.
- **Role coherence** mismatches fail closed with specific errors; there is no automatic repair (by design — silent repair would be fail-open).
- **No human UAT yet.** All numbers above are lab numbers. That's the next real gate, not another benchmark.

*Full failure register and per-step costs: `docs/process/AGENT.md` (§5, §6). Full limitations, no softening: `docs/process/PROJECT_HANDOFF.md` §6.*
