# 2-minute demo script — Intara (portfolio)

> Record with the **static demo** open (`VITE_DEMO=1` build, or the live URL once deployed). ~300 words of narration; keep clicks slow and deliberate. Every claim here is one the repo's tests measure.

---

**[0:00–0:15] Hook — landing page**

“Most app builders ask an LLM to write all the code and hope it compiles. Intara takes the other bet: the LLM writes small, typed JSON *specs*, and a tested runtime engine executes them. Same wish in — a working app out.”

**[0:15–0:40] The gallery — 10 gold apps**

“This is the builder's output gallery — ten human-reviewed apps covering bookings, CRM, clubs, inventory, HR, repairs and more. The whole thing runs in your browser: no backend, no LLM at runtime. Let me open one.”

*(Click “Open the 10 live apps”, then TaskFlow.)*

**[0:40–1:30] One app, end to end — TaskFlow**

“TaskFlow was produced from a single sentence: projects, tasks, deadlines and hours, with a board view. Everything here is the spec runtime doing the work.

- This is a **kanban board** — dragging a card fires a workflow transition, with role checks.
- **Computed fields**: hours remaining is a formula — a hand-written parser, no `eval`, running in TypeScript.
- **Filters, roles, CSV export, print views** — all executed by the same engine.
- Switch the role in the header — the nav and permissions change, because access rules are part of the spec.”

*(Drag a card, open a detail view, switch role, open the CSV export.)*

**[1:30–1:55] How the build works (talk over the repo)**

“Locally, the full pipeline runs: intake, clarify, model, design, logic, assembly — every stage emits schema-validated JSON with bounded repair loops, then gates decide: schema, a 50-rule semantic lint, requirement coverage, generated engine tests. The run engine is resumable — I've killed a build mid-run and watched it finish after a restart. Eval numbers: 5 of 5 golden wishes, 17 of 20 on the live tuned set, 3 of 5 on held-out domains never tuned for. Roughly 400 tests.”

**[1:55–2:00] Close**

“Spec-first, fail-closed, measurable. Repo and full write-up are linked below — including the failures.”

---

## Production notes

- 1440×900 browser, zoom ~110% so the app text is readable.
- Pre-open a wish? **No** — the static demo has no LLM; don't imply live generation from the recorder. Say “built from this sentence” instead.
- Have the gallery and TaskFlow already loaded before recording; cut dead time.
- B-roll option (15–20s, over narration): the repo README numbers table + `docs/RESULTS.md` on screen during the 1:30–1:55 segment.
- Upload to YouTube (unlisted) or Loom; then put the link in `README.md` (search for “🎥”).
