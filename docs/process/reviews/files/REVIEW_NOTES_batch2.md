# Review notes — batch 2 (gardening, productivity)

Same conventions, same caveats as `REVIEW_NOTES.md` (prop vocabulary, `$user.email`, `{template}` syntax, trace kinds, +05:30 seeds). Read that first; nothing here changes it.
Verification: my own checker (updated `semantic_lint_prototype.py`) passes both with 0 errors / 0 warnings. Your real G0/G1 has not been run.

## What changed

| | Before | After |
|---|---|---|
| gardening → **GardenPlan** | 4 entities, 6 pages, 16 seed rows, 1 requirement, role `planner` | 6 entities (+`harvest`, +`care_task`), 11 pages, 36 seed rows, 7 requirements, 5 automations, roles owner/helper |
| productivity → **TaskFlow** | 2 entities, 5 pages, 8 seed rows, 1 role, 1 requirement | 4 entities (+`comment`, +`time_entry`), 6 pages, 29 seed rows, 8 requirements, 4 automations, roles owner/member |

**Formulas (now 3 golds exercise them):**
- gardening: `planting.total_harvested = sum(harvests.quantity_kg)`
- productivity: `task.hours_logged = sum(time_entries.hours)` and `task.hours_remaining = estimate_hours - hours_logged` (a computed field reading another computed field — worth confirming the engine evaluates in dependency order)

## Defects in the raw candidates (both were "green")
- **gardening:** 3 of 6 nav items pointed at `:id` pages; `garden.beds` and `bed.plantings` were `multi_ref` fields duplicating the `ref` in the other direction (two sources of truth); 5 filler fields; 3 `data.table` blocks with no columns; per-record `lifecycle.pipeline` on a list page; notifications interpolating `{{record.id}}`; the `plant_status` enum was unused; `planner` could reach only detail pages and the owner couldn't open Bed or Planting detail; a `planting_created` automation re-set a status that was already the default.
- **productivity:** 2 of 5 nav items at `:id` pages; the same six block ids reused across pages (`task_filter`, `task_table`, `task_form`, `task_lifecycle`, …); a project detail page embedding the whole task table plus a task create form; per-record pipeline on the list page; a placeholder `https://example.com/webhook`; "Reopen" going from in-progress back to to-do; empty transition roles; 2024 seed dates; USD/UTC with no money anywhere.

### New lint rules from this batch (added to the prototype)
- Block ids unique across the whole spec, and never equal to a page id.
- Flag `multi_ref` that mirrors an existing `ref` (store the relation once, on the child).
- Reject webhook targets that are placeholder hosts (`example.com`) and notification templates that interpolate only an id.

## Decisions to confirm
1. **`task.hours_remaining` reads `hours_logged`**, itself computed. If the engine doesn't support chained computed fields, change it to `estimate_hours - sum(time_entries.hours)`.
2. **Reminder recipients** — gardening/productivity automations email an address reached through a ref path (`planting.bed.garden.owner_email`, `project.owner_email`). Confirm the executor resolves multi-hop paths in `to`.
3. **`set_field` value `today()`** (gardening `care_completed_stamp`) — confirm the executor evaluates function calls in `value`; `now()` is used the same way in education/social.
4. **Care tasks have no notify recipients other than the garden owner** by design (no user entity exists in the model).
