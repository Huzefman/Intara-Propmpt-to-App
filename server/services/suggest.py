"""
Deterministic next-step suggestions derived from the AppSpec.

No LLM calls (free-tier safe): rules keyed on appType + table names,
with generic fillers so the agent always has a move to offer.
Each suggestion carries a prompt_suffix the client appends to the
original wish when forking a v2 plan.
"""

_GENERIC = [
    {"label": "User auth + profiles", "detail": "Sign-in and per-user data", "prompt_suffix": " plus user authentication with profiles"},
    {"label": "Full-text search", "detail": "Search across all records", "prompt_suffix": " plus full-text search across all records"},
    {"label": "Data export", "detail": "CSV export of every table", "prompt_suffix": " plus CSV export of every table"},
]


def _tables(prd: dict) -> list[str]:
    return [str(t.get("name", "")).lower() for t in (prd.get("tables") or []) if isinstance(t, dict)]


def _domain_suggestions(prd: dict) -> list[dict]:
    blob = " ".join(_tables(prd)) + " " + str(prd.get("appType", "")).lower()
    out: list[dict] = []

    if any(w in blob for w in ("game", "move", "score", "board", "arcade")):
        out += [
            {"label": "Local 2-player mode", "detail": "Two people share one screen", "prompt_suffix": " plus a local 2-player mode on the same screen"},
            {"label": "Leaderboard", "detail": "Persistent high scores", "prompt_suffix": " plus a persistent leaderboard"},
            {"label": "Difficulty levels", "detail": "Easy / Medium / Hard", "prompt_suffix": " plus easy, medium and hard difficulty levels"},
        ]
    if any(w in blob for w in ("product", "spell", "cart", "order", "shop", "market", "item")):
        out += [
            {"label": "Shopping cart", "detail": "Add-to-cart across the catalog", "prompt_suffix": " plus a shopping cart across the catalog"},
            {"label": "Checkout flow", "detail": "Place and confirm orders", "prompt_suffix": " plus a checkout flow to place orders"},
            {"label": "Wishlist", "detail": "Save items for later", "prompt_suffix": " plus a wishlist to save items for later"},
        ]
    if any(w in blob for w in ("post", "comment", "thread", "forum", "blog", "question", "social")):
        out += [
            {"label": "Comments", "detail": "Discuss under each post", "prompt_suffix": " plus comments under each post"},
            {"label": "Likes + tags", "detail": "Rank and organize content", "prompt_suffix": " plus likes and tags on every post"},
        ]
    if any(w in blob for w in ("slot", "booking", "appointment", "reservation")):
        out += [
            {"label": "Calendar view", "detail": "See bookings by day", "prompt_suffix": " plus a calendar view of bookings by day"},
            {"label": "Reminders", "detail": "Due-soon notifications", "prompt_suffix": " plus due-soon reminders"},
        ]
    if any(w in blob for w in ("task", "todo", "habit")):
        out += [
            {"label": "Kanban board", "detail": "Drag tasks across columns", "prompt_suffix": " plus a kanban board with drag-and-drop columns"},
            {"label": "Priorities", "detail": "P0–P3 levels with sorting", "prompt_suffix": " plus priority levels with sorting"},
        ]
    if any(w in blob for w in ("recipe", "meal", "ingredient")):
        out += [
            {"label": "Meal planner", "detail": "Plan a week of meals", "prompt_suffix": " plus a weekly meal planner"},
            {"label": "Shopping list", "detail": "Auto-built from recipes", "prompt_suffix": " plus a shopping list auto-built from recipes"},
        ]
    return out


def suggest_next(prd: dict) -> list[dict]:
    """Return up to 4 suggestions: domain rules first, generic fillers after."""
    seen: set[str] = set()
    out: list[dict] = []
    for s in _domain_suggestions(prd or {}) + _GENERIC:
        if s["label"] in seen:
            continue
        seen.add(s["label"])
        out.append(s)
        if len(out) == 4:
            break
    return out
