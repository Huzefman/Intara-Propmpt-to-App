"""
AppSpec -> component selections.

Translates a validated BuildPlan/AppSpec (tables/entities/pages/apis) into
[{id, config}] selections the composer can resolve. Pure function, no I/O —
the analyzer calls it, the composer validates the rest.

Mapping rules:
- every table -> crud-entity, except a table literally named `scores` in a
  game spec -> scores-table; a `users` table additionally yields auth-users.
- every page WITH a table binding -> detail-page when the route carries an id
  (:id or {id}), else list-page (dashboard layout pages also gain stat-cards
  when the app is a dashboard).
- every page WITHOUT a table binding (interactive, feature-bound) ->
  game-board for feature play (default), scores-list for feature scores.
  Unrecognized feature pages are skipped with a warning, never forced.
- every entity -> crud-api, except scores in game specs -> scores-api.
"""
from components.registry import CatalogError


def _is_game_spec(data: dict) -> bool:
    return str(data.get("appKind") or "").lower() in ("interactive", "game")


_EXPORT_WORDS = ("export", "csv", "spreadsheet", "download data", "excel")

_UPLOAD_WORDS = ("upload", "attach", "file", "image", "photo", "avatar", "document", "picture")


def _blob_matches(blob: str, words: tuple) -> bool:
    import re as _re
    return any(_re.search(r"\b" + _re.escape(w) + r"s?\b", blob) for w in words)


def _wants_export(data: dict) -> bool:
    req = data.get("requirements") or {}
    blob = " ".join([
        str(data.get("appName") or ""),
        str(data.get("tagline") or ""),
        " ".join(req.get("functional", []) if isinstance(req, dict) else []),
    ]).lower()
    return _blob_matches(blob, _EXPORT_WORDS)


def _wants_upload(data: dict) -> bool:
    req = data.get("requirements") or {}
    blob = " ".join([
        str(data.get("appName") or ""),
        str(data.get("tagline") or ""),
        " ".join(req.get("functional", []) if isinstance(req, dict) else []),
    ]).lower()
    return _blob_matches(blob, _UPLOAD_WORDS)


def selections_for_appspec(data: dict) -> tuple[list[dict], list[str]]:
    """Return (selections, warnings). Never raises on unknown shapes — unknown
    pages/features produce warnings so the caller can fall back to legacy."""
    selections: list[dict] = []
    warnings: list[str] = []
    tables = data.get("tables") or []
    entities = {e.get("name"): e for e in (data.get("entities") or []) if e.get("name")}
    game = _is_game_spec(data)

    for t in tables:
        name = t.get("name", "")
        if game and name == "scores":
            selections.append({"id": "scores-table", "config": {}})
            continue
        cfg: dict = {"table": name, "fields": t.get("fields", [])}
        ent = entities.get(name)
        if ent and ent.get("relationships"):
            cfg["relationships"] = ent["relationships"]
        selections.append({"id": "crud-entity", "config": cfg})
        if name == "users":
            selections.append({"id": "auth-users", "config": {"table": "users"}})

    for p in data.get("pages") or []:
        pname = p.get("name", "")
        route = p.get("route", "/")
        bound = p.get("table")
        if bound:
            if ":id" in route or "{id}" in route:
                selections.append({"id": "detail-page",
                                   "config": {"page": pname, "route": route, "entity": bound}})
            else:
                selections.append({"id": "list-page",
                                   "config": {"page": pname, "route": route, "entity": bound}})
                if (data.get("appType") == "dashboard" and route == "/"
                        and not any(s["id"] == "stat-cards" for s in selections)):
                    selections.append({"id": "stat-cards", "config": {"entity": bound}})
        elif game:
            feature = str(p.get("feature") or "").lower()
            if feature == "scores" or "score" in pname.lower():
                selections.append({"id": "scores-list",
                                   "config": {"page": pname, "route": route, "entity": "scores"}})
            elif feature in ("play", "") or "game" in pname.lower() or "board" in pname.lower():
                selections.append({"id": "game-board",
                                   "config": {"page": pname, "route": route, "feature": p.get("feature", "play")}})
            else:
                warnings.append(f"page {pname!r} has no table binding or known game feature — skipped")
        else:
            warnings.append(f"page {pname!r} has no table binding — skipped")

    table_names = {t.get("name") for t in tables}
    for name in sorted(table_names - {None}):
        if game and name == "scores":
            selections.append({"id": "scores-api", "config": {"entity": name}})
        else:
            selections.append({"id": "crud-api", "config": {"entity": name}})

    if _wants_export(data) and table_names - {None}:
        for name in sorted(table_names - {None}):
            selections.append({"id": "csv-export", "config": {"entity": name}})

    if _wants_upload(data) and table_names - {None}:
        for name in sorted(table_names - {None}):
            selections.append({"id": "file-upload", "config": {"entity": name}})

    return selections, warnings
