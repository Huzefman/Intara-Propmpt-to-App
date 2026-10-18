# Ownership test — written answers (interview prep)

> The five questions from `intara-portfolio-shift.md`, answered from this repo's
> actual code. Read the referenced files once, end to end, before using these —
> the point is to be able to defend them, not recite them.

## 1. Why spec-first instead of generating code?

Because LLM output must be *verifiable before it runs*, and a small typed JSON
spec can be verified four different ways at $0:

- **G0 schema** — one JSON Schema generates both the Pydantic and TS types
  (`scripts/gen_spec_types.py --check` fails on drift), so the contract can't rot.
- **G1 semantic lint** — R01–R50 catch whole classes of nonsense (unreachable
  pages, role mismatches, bad bindings) before execution.
- **G2 coverage + G3 generated tests** — requirements are traced, and the spec
  gets executable engine tests generated for it.
- **Determinism** — the runtime has no LLM in it: same spec in, same behavior
  out (statically tested). Specs are diffable and patchable: RFC 6902 patches
  with invert → safe undo, version tree.

Generated code can't be gated to that depth on free tiers, and code is still an
export target (Track B path) — it's just not the product.

## 2. Walk one wish from prompt to running preview

`POST /api/wish` → the run engine creates **one** run row (`run_id` passthrough
— an earlier bug created two, and the client polled a shell forever) →
S0 intake → S1 clarifier (may ask questions; approve) → S2 modeler (entities,
fields, relations) → S3 designer (pages + **declares the role set**) →
S4 logic (transitions/automations/formulas — must be a **subset** of S3's roles,
this is the S3-declares/S4-subset contract) → S5 assembler + critic (gates run
here, fail closed) → S6 seed data.

Every stage: versioned prompt, typed JSON output, schema validation, ≤2 repair
loops at cooling temperature, quota-aware retries (429 never burns a repair).
Artifacts are content-addressed and resume-restorable by hash. The Studio
subscribes to SSE, shows the blueprint, and the **RuntimePreview** executes the
spec in the browser (memory/Dexie adapter) — the same engine that runs the
gallery apps.

## 3. How does the eval work, and what's wrong with 17/20?

Two evals:

- `scripts/eval.py --mocked` — 5 golden wishes, 6 binary checks each
  (json_valid, schema shape, FE `tsc`, BE `ast` + `ruff`, openapi, cites).
  Free, runs in CI.
- `scripts/core20.py --live` — 20 fixed prompts end-to-end; per wish: status,
  G0/G1 result, LLM calls, wall time, degraded steps; **fail-closed: any silent
  fallback counts as failure**; records diversity (distinct feature combos,
  entity overlap).

What's wrong with 17/20:

1. **It's the tuned set.** I fixed failure *classes* against these exact
   prompts — that's partial overfitting. The honest generalization number is
   the held-out domains: **3/5**. Report them together or neither means anything.
2. **Small n.** 20 and 5 are not statistics, they're signals.
3. **Quota-shaped.** ~Half of live failures are free-tier quota, not logic —
   the number moves with provider weather.
4. **G0/G1 green ≠ usable.** No human UAT has happened yet. That's the next gate.

## 4. The formula parser and the patch/invert logic

**Parser:** hand-written tokenizer + recursive-descent parser → AST, in **both**
Python (`server/engine/formula.py`) and TypeScript
(`packages/spec/formula/`). No `eval`/`exec` anywhere. Precedence: `or` → `and`
→ `not` → comparisons → `+ -` → `* /` → unary. Functions: `if`, `sum`, `count`,
`min`, `max`, `avg`, `len`, `str`, date helpers (`today()`, `dayShift`,
`start_of_month` — UTC-anchored after fixing an IST off-by-one). Two
implementations run the **same 135 conformance cases** plus a 500-input fuzzer
(only `FormulaSyntaxError`/`FormulaError` may escape; the process cannot crash).
Computed fields evaluate in dependency order.

**Patch/invert** (`server/engine/patch.py`, RFC 6902): every spec edit is a
patch; `invert()` returns the undo patch. The subtle part is existence
semantics — for `add`/`remove`/`replace`/`move`/`copy`, invert *simulates*
applying the patch to see whether a target existed (add-vs-replace behave
differently on undo). Validated by randomized round-trip fuzzing: **1,175/1,175
apply→invert→apply returns the original**. This fuzzer caught a real bug: invert
of a dict-key overwrite removed the key instead of restoring the old value.

## 5. Paid API key vs none

**With a paid key:** the biggest single change — quota-shaped failures (~half of
all observed) disappear overnight for ~cents per build. Then: let repairs
actually land instead of dying at 429, use one strong model instead of a
4-provider chain, re-measure honestly, and push the median wall time under the
3-minute target (currently 4.4 min, quota-throttled).

**With none (current):** a chain of free-tier providers (Gemini / Groq /
OpenRouter / Nvidia) with quota-aware retries, cooldowns, per-provider monthly
budgets, deterministic *labelled* fallbacks, template floor for worst case,
cassettes + mocked evals so CI costs $0, and the static gold-app gallery as the
$0 demo surface. The discipline that makes $0 workable is fail-closed +
separating quota deaths from logic deaths in every eval.

---

**Files to read once, end to end:** `server/services/run_engine.py` ·
`server/engine/formula.py` + `packages/spec/formula/formula.ts` ·
`server/engine/patch.py` · `scripts/core20.py` · `scripts/eval.py` ·
`react-prompt-app/src/runtime/RuntimePreview.tsx`.
