# Review notes — veterinary / education / social gold candidates

Files returned under the same names: `veterinary_candidate.json`, `education_candidate.json`, `social_candidate.json`.
`semantic_lint_prototype.py` is the checker I used (ignore the builder helpers at the top; the part under `# ---- checker` is the part worth porting).

**Verification caveat:** I could not run your G0/G1 — I ran my own checker, which passes all three with 0 errors / 0 warnings. Please run your real G0/G1 before promoting.

## What changed

| | Before | After |
|---|---|---|
| veterinary → **PawCare** | 3 entities, 7 pages, 11 seed rows, 1 requirement | 4 entities (+`treatment`), 8 pages, 28 seed rows, 7 requirements, 4 automations |
| education → **ClubConnect** | 5 entities, 4 pages, 4 seed rows, 2 access rules, 0 automations | 5 entities, 8 pages, 51 seed rows, 11+5 access rules, 3 automations, 7 requirements |
| social → **Page Turners** | 6 entities, 7 pages, 28 seed rows, 1 requirement | 6 entities, 7 pages, 37 seed rows, 5 automations, 8 requirements |

Every file now has: real name/tagline/domain/locale (en-IN, INR, Asia/Kolkata, matching its own assumptions), 3 personas, 7–8 must/should requirements, a trace entry per requirement, cleaned assumptions, and a theme.
**Computed formulas:** only in veterinary — `treatment.line_total = quantity * unit_price` and `visit.total = consultation_fee + sum(treatments.line_total)` (the two patterns the guide specifies). Education/social have none (see "Decisions" below).

## Defects in the raw candidates that G0–G3 did not catch
These are real bugs, not style. All three were "green":

1. **education** — only 2 access rules for 5 entities (4 entities had no rule at all); every role could see only one page (admin couldn't open Clubs; the "owner" role was meaningless for a school); 4 "dashboard" pages and no detail pages; 1 student row and no membership/event/attendance seeds; 11 filler fields (`id`, `created_at`, `updated_at`).
2. **social** — members could only read `status = 'proposed'` books, so nobody could see the selected book; the `owner` role had no rules on any entity but club; `owner` wasn't in the `member_role` enum; "Single club instance" assumption contradicted 3 seeded clubs; `lifecycle.pipeline` placed on a list page (it is per-record); "Reschedule" transitioned from `completed`; 12 filler fields.
3. **veterinary** — nav items pointing at `:id` detail pages; automation emails `{{vet.email}}`, which no entity provides; rules use `current_user.owner_id`, which no model defines; refs named `patient_id`/`owner_id`; cascade-delete from owner → patients → visits (would erase clinical records); seeds were USD/US addresses despite the INR/India assumptions.

### Suggested new G1 rules (all implemented in the prototype)
- Every (page role × block entity) pair needs a `read` rule; also warn when a role displays a dotted ref path (`club.name`) but can't read the traversed entity.
- Every role has ≥ 1 nav item; nav items never target `:id` routes; a nav item's roles ⊆ the page's roles.
- No fields named `id`, `created_at`, `updated_at`; ref fields not named `*_id`.
- All identifiers in `where` / `guard` / `when` / formulas / `{templates}` must resolve (and `$user.*` is the only allowed context variable).
- `lifecycle.pipeline` only on pages with a `record.detail`; `row_link` target must show the same entity as the rows; `related_list.via` must be a ref whose target is the page's record entity.
- Every entity has ≥ 1 seed row and ≥ 1 access rule; seeded enum values, required fields, unique fields, `@refs` (and their target entity) all valid; computed fields never seeded.
- Lifecycle: enum default == `initial`; all states reachable.

## Conventions I normalised — please confirm against `packages/catalog`
The three raw specs used different prop names for the same block (the LLM was improvising, so G1 evidently doesn't enforce `props_schema` strictly). I used the vocabulary from the guide. If your block `props_schema` differs, this table is the sed map:

| Block | Raw variants seen | Used here |
|---|---|---|
| `data.table` | `fields` / `columns`; `rowLink:"/x/:id"` / `row_link` | `columns`, `row_link:"<page_id>"`, `create:true` |
| `record.detail` | flat `fields` | `sections:[{title, fields}]` |
| `record.related_list` | `entity`=parent + `relation` | `entity`=child, `via`=ref field, `columns`, `row_link`, `create` |
| `metric.stat` | `{label,metric}` / `{field,title,value}` | `{entity, items:[{label, agg, field?, where?}]}` |
| `chart.bar` | `{field,title}` / `{x,y,title}` | `{entity, title, x, y:"count"}` |
| `calendar.month`, `activity.timeline` | `dateField` | `date_field` (+ `row_link` / `title`) |
| `data.kanban` | `{entity, group_by}` | adds `card:{title,subtitle,badges}`, `drag_transitions` |
| `filter.bar` | `{entity}` | `{entity, fields, search}` |
| `lifecycle.pipeline` | `field`, `transitions`, `lifecycle` | `{entity}` only |

Expressions: `AND`/`IN`/`=` → `and`/`or`/`==`; user context `current_user.*` / `current_user_id` → `$user.email` (people sign in with the email stored on their record); templates `{{x}}` → `{x}` with the triggering record's fields unprefixed (`{patient.owner.email}`); only functions used: `today()`, `tomorrow()`, `startOfMonth()`, `now()`, `sum(rel.field)`, `!= null`.
Other: refs named after their target entity; trace kinds used: `entity`, `page`, `automation`, `field`, `lifecycle`, `role` (the raw specs only used the first three); theme archetypes `calendar-centric` / `dashboard-first` / `catalog-detail`.
Seeds use `+05:30` offsets and dates around mid-October 2026 so "today" stats are non-empty now; they will go stale (consider relative-date tokens if the runtime supports them).

## Decisions / things to verify
1. **Prop vocabulary** (table above) — confirm or sed.
2. **`$user.email` mapping** — gold specs currently assume the signed-in user's email matches an email on a domain record. If you'd rather have an explicit user→record link, change all `where` strings together; mixed styles will teach the generator inconsistency.
3. **Formulas in education/social** — I held back because I can't confirm `count()` / `avg()` exist. Natural candidates once they do: `event.attendee_count`, `book.average_rating`.
4. **Pipeline prompts** — the root causes are upstream: S2/S4 should be told "no id/timestamp fields", "ref named after target", "one rule per (role, entity) you show", and to emit the guide's block props. That plus the new G1 rules would keep these defects out of the next 17.
