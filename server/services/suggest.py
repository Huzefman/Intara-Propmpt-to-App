"""
Deterministic next-step suggestions derived from the AppSpec or PRD.

No LLM calls (free-tier safe): inspects model entities, fields, UI pages,
blocks, automations, and access roles to propose high-value, non-technical
next steps. Each suggestion carries a human-friendly label, a plain-English
detail explanation, and a ready-to-run prompt string for Studio iterations.
"""
from __future__ import annotations

_GENERIC = [
    {
        "label": "Full-text search",
        "detail": "Search across all records and fields instantly",
        "prompt": "Add a search bar to filter records across all fields",
        "prompt_suffix": " plus full-text search across all records",
    },
    {
        "label": "Data export",
        "detail": "Download spreadsheet backups of your data",
        "prompt": "Add CSV export buttons to all data tables",
        "prompt_suffix": " plus CSV export of every table",
    },
    {
        "label": "User profiles",
        "detail": "Profile information and personal settings",
        "prompt": "Add a user profile and settings page",
        "prompt_suffix": " plus user profiles and settings",
    },
]


def _extract_spec_meta(spec: dict) -> dict:
    """Extract structured meta from either v2 AppSpec or v1 PRD."""
    model = spec.get("model") or {}
    entities = list(model.get("entities") or [])
    ui = spec.get("ui") or {}
    pages = list(ui.get("pages") or [])
    automations = list(spec.get("automations") or [])
    access = spec.get("access") or {}
    roles = [r.get("id") if isinstance(r, dict) else r for r in access.get("roles") or []]

    # If v1 PRD format (tables instead of entities)
    if not entities and spec.get("tables"):
        for t in spec.get("tables", []):
            if isinstance(t, dict):
                entities.append({
                    "id": str(t.get("name", "record")).lower(),
                    "label": t.get("name", "Record"),
                    "fields": [{"id": f.get("name"), "type": f.get("type", "text")}
                               for f in t.get("fields", []) if isinstance(f, dict)],
                })

    block_types = {b.get("type") for p in pages for b in p.get("blocks", []) if isinstance(b, dict)}
    field_types = {f.get("type") for e in entities for f in e.get("fields", []) if isinstance(f, dict)}
    field_ids = {str(f.get("id", "")).lower() for e in entities for f in e.get("fields", []) if isinstance(f, dict)}
    entity_names = [str(e.get("label") or e.get("id") or "") for e in entities]

    app_name = (spec.get("app") or {}).get("name") or spec.get("appName") or ""
    app_type = spec.get("appType") or (spec.get("app") or {}).get("domain") or ""
    text_blob = (" ".join(entity_names) + " " + app_name + " " + app_type + " " + " ".join(field_ids)).lower()

    return {
        "entities": entities,
        "entity_names": entity_names,
        "pages": pages,
        "block_types": block_types,
        "field_types": field_types,
        "field_ids": field_ids,
        "automations": automations,
        "roles": roles,
        "text_blob": text_blob,
    }


def suggest_next(spec_or_prd: dict) -> list[dict]:
    """Return up to 4 high-value, plain-English next-step suggestions."""
    meta = _extract_spec_meta(spec_or_prd or {})
    blob = meta["text_blob"]
    block_types = meta["block_types"]
    field_types = meta["field_types"]
    field_ids = meta["field_ids"]
    entities = meta["entities"]
    roles = meta["roles"]
    automations = meta["automations"]

    out: list[dict] = []
    seen: set[str] = set()

    def add(s: dict):
        if s["label"] not in seen and len(out) < 4:
            seen.add(s["label"])
            out.append(s)

    # 1. Calendar view (if dates exist, but no calendar block)
    has_dates = bool({"date", "datetime"} & field_types or any("date" in f or "due" in f or "time" in f for f in field_ids))
    if has_dates and "calendar.month" not in block_types:
        add({
            "label": "Visual calendar",
            "detail": "See deadlines and schedules on a monthly calendar",
            "prompt": "Add a calendar view page using calendar.month to track records by date",
            "prompt_suffix": " plus a calendar view of records by date",
        })

    # 2. Kanban board (if status/lifecycle exists, but no kanban block)
    has_status = bool({"enum"} & field_types or any(k in field_ids for k in ("status", "stage", "state", "phase", "priority")))
    if has_status and "data.kanban" not in block_types:
        add({
            "label": "Kanban board",
            "detail": "Move cards across visual drag-and-drop workflow columns",
            "prompt": "Add a kanban board page grouped by status so records can be moved across stages",
            "prompt_suffix": " plus a kanban board with drag-and-drop columns",
        })

    # 3. Analytics / Summary dashboard (if metrics exist, but no chart or stats)
    has_metrics = bool({"int", "decimal", "money", "rating"} & field_types or len(entities) >= 2)
    if has_metrics and "chart.bar" not in block_types and "metric.stat" not in block_types:
        add({
            "label": "Summary dashboard",
            "detail": "Key stat cards and bar charts summarizing totals",
            "prompt": "Add an overview dashboard page with metric stat blocks and a bar chart",
            "prompt_suffix": " plus an analytics dashboard with stat metrics and bar charts",
        })

    # 4. Automated alerts & notifications (if automations are absent)
    if len(automations) == 0 and len(entities) > 0:
        add({
            "label": "Automated alerts",
            "detail": "Notify the owner when records are updated or created",
            "prompt": "Add an automation that triggers when a record is updated to notify the owner",
            "prompt_suffix": " plus automated alerts when records are updated",
        })

    # 5. Team collaboration & Roles (if app is single-user)
    if len(roles) <= 1 and not any(r in roles for r in ("member", "manager", "staff", "editor")):
        add({
            "label": "Team collaboration",
            "detail": "Add a team member role and record assignments",
            "prompt": "Add a team member role and an assigned-to field for collaboration",
            "prompt_suffix": " plus team collaboration with member roles and assignments",
        })

    # 6. Quick filter bar (if tables exist without filter bar)
    if "data.table" in block_types and "filter.bar" not in block_types:
        add({
            "label": "Quick filters",
            "detail": "Filter table records instantly by status or category",
            "prompt": "Add a filter.bar block above data tables to quickly filter by category or status",
            "prompt_suffix": " plus quick filter bars for tables",
        })

    # 7. File & document attachments
    if not ({"file", "image"} & field_types):
        add({
            "label": "File attachments",
            "detail": "Attach receipts, documents, or photos to records",
            "prompt": "Add file and image attachment fields to upload and store documents",
            "prompt_suffix": " plus file and image attachment fields",
        })

    # 8. Domain-specific suggestions
    if any(w in blob for w in ("game", "score", "player", "board", "match", "tournament")):
        add({
            "label": "Leaderboard",
            "detail": "High scores and player ranking standings",
            "prompt": "Add a leaderboard view ranking players by score",
            "prompt_suffix": " plus a persistent leaderboard",
        })
    if any(w in blob for w in ("product", "shop", "cart", "order", "item", "catalog", "store")):
        add({
            "label": "Order checkout flow",
            "detail": "Place and confirm orders with receipt summary",
            "prompt": "Add an order checkout flow with order status tracking",
            "prompt_suffix": " plus a checkout flow to place orders",
        })
    if any(w in blob for w in ("booking", "appointment", "clinic", "patient", "doctor", "slot")):
        add({
            "label": "Appointment reminders",
            "detail": "Automated reminders for upcoming scheduled visits",
            "prompt": "Add an automation that sends reminders for upcoming appointments",
            "prompt_suffix": " plus automated appointment reminders",
        })
    if any(w in blob for w in ("recipe", "meal", "ingredient", "kitchen", "food")):
        add({
            "label": "Shopping list",
            "detail": "Auto-built grocery list from meal recipes",
            "prompt": "Add a shopping list view auto-generated from ingredients",
            "prompt_suffix": " plus an auto-generated shopping list",
        })
    if any(w in blob for w in ("inventory", "stock", "warehouse", "item", "supplier")):
        add({
            "label": "Low-stock alerts",
            "detail": "Automatic notification when quantity falls below threshold",
            "prompt": "Add an automation alerting when inventory quantity falls below reorder level",
            "prompt_suffix": " plus low-stock threshold alert automations",
        })

    # Fill remaining with generic fallbacks
    for g in _GENERIC:
        add(g)

    return out[:4]
