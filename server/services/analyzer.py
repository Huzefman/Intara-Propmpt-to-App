"""
Analyzer — prompt -> AppSpec (rich BuildPlan superset)
Single LLM call, template fallback on failure.
"""
import os
import re
from utils.json_parse import parse_json as _parse_json, is_quota_error as _is_quota


CRUD_TYPES = {"catalog", "dashboard", "marketplace", "social", "booking",
                "form-wizard", "content-management"}
INTERACTIVE_TYPES = {"game", "tool", "showcase"}


def _app_kind(data: dict) -> str:
    """Authoritative appKind: explicit key wins, else derived from appType."""
    k = str(data.get("appKind") or "").lower()
    if k in ("crud", "interactive"):
        return k
    return "interactive" if str(data.get("appType") or "") in INTERACTIVE_TYPES else "crud"


def _validate_app_spec(data: dict) -> list[str]:
    errors = []
    if "appName" not in data:
        errors.append("missing appName")
    if "entities" not in data and "tables" not in data:
        errors.append("missing entities/tables")
    kind = _app_kind(data)
    data["appKind"] = kind
    if kind == "interactive":
        game_type = data.get("gameType")
        if data.get("appType") == "game" and game_type not in ("tictactoe", "memory", "arcade", "custom", None):
            errors.append(f"gameType {game_type!r} unknown (want tictactoe|memory|arcade|custom)")
    # check entity names snake_case
    for ent in data.get("entities", []):
        name = ent.get("name", "")
        if not re.match(r"^[a-z][a-z0-9_]*$", name):
            errors.append(f"entity name {name} not snake_case")
        # relationships reference valid entities
        valid = {e["name"] for e in data.get("entities", [])}
        for rel in ent.get("relationships", []):
            if rel.get("target") not in valid:
                errors.append(f"relationship target {rel.get('target')} not in entities")
    # pages reference valid entities — crud pages MUST bind a table, interactive
    # pages are feature-bound and need no table key at all
    valid_entities = {e["name"] for e in data.get("entities", [])} | {t["name"] for t in data.get("tables", [])}
    for p in data.get("pages", []):
        tbl = p.get("table")
        if tbl and tbl not in valid_entities:
            errors.append(f"page {p.get('name')} table {tbl} not in entities")
        elif kind == "crud" and not tbl:
            errors.append(f"page {p.get('name')} needs a table binding in crud mode")
    return errors


def _derive_build_graph(app_spec: dict) -> list[dict]:
    """Auto-generate DAG from entities+pages (strict sequential). Pure-frontend
    specs (no entities/tables) skip schema-foundation — there is no DDL to weave."""
    entities = app_spec.get("entities") or [{"name": t["name"]} for t in app_spec.get("tables", [])]
    pages = app_spec.get("pages", [])
    graph = []
    if entities:
        graph.append({"id": "schema-foundation", "kind": "schema", "ref": None, "dependsOn": [], "status": "pending", "promptHint": "tables+migrations with FKs"})
    for ent in entities:
        graph.append({"id": f"backend-{ent['name']}", "kind": "backend_table", "ref": ent["name"], "dependsOn": ["schema-foundation"], "status": "pending", "promptHint": f"models+APIs for {ent['name']}"})
    for p in pages:
        graph.append({"id": f"frontend-{p['name']}", "kind": "frontend_page", "ref": p["name"], "dependsOn": ["schema-foundation"] if entities else [], "status": "pending", "promptHint": f"page {p['name']}" + (f" for table {p.get('table')}" if p.get("table") else "")})
    # wiring depends on all previous (except schema when skipped)
    wiring_deps = [n["id"] for n in graph if n["id"] != "schema-foundation"]
    graph.append({"id": "wiring", "kind": "wiring", "ref": None, "dependsOn": wiring_deps, "status": "pending", "promptHint": "App.tsx nav, api wiring, mock FK seeds"})
    graph.append({"id": "validate", "kind": "validate", "ref": None, "dependsOn": ["wiring"], "status": "pending", "promptHint": "tsc/ast/openapi + FK consistency"})
    return graph


def _derive_tables_from_entities(entities: list[dict]) -> list[dict]:
    """Strip relationships/businessRules for backward compat with schema_gen."""
    tables = []
    for ent in entities:
        tables.append({"name": ent["name"], "fields": ent.get("fields", [])})
    return tables


_CATALOG_CACHE: dict | None = None


def _compose_or_legacy_dag(data: dict) -> list[dict]:
    """Resolve the AppSpec through the component catalog when possible.

    Success: buildGraph from composer.to_dag() + data['_components'] record
    (order/units/warnings/catalog version) for persistence. Any CatalogError:
    legacy _derive_build_graph() + a warning surfaced in _meta. Never raises.
    """
    global _CATALOG_CACHE
    try:
        from components.composer import compose, to_dag
        from components.registry import CatalogError, load_catalog
        from components.select import selections_for_appspec
        if _CATALOG_CACHE is None:
            _CATALOG_CACHE = load_catalog()
        selections, select_warnings = selections_for_appspec(data)
        comp = compose(_CATALOG_CACHE, selections)
        graph = to_dag(_CATALOG_CACHE, comp)
        data["_components"] = {
            "order": comp["order"],
            "units": comp["units"],
            "warnings": comp["warnings"] + select_warnings,
            "catalog_version": _CATALOG_CACHE.get("version", "0.0.0"),
        }
        return graph
    except CatalogError as e:
        data["_components_warning"] = str(e)[:200]
        print(f"component composition fell back to legacy DAG: {e}")
    except Exception as e:
        data["_components_warning"] = f"composer unavailable: {str(e)[:120]}"
        print(f"component composition error, legacy DAG: {e}")
    data.pop("_components", None)
    return _derive_build_graph(data)


def _attach_composition(data: dict) -> dict:
    """Best-effort composition for mock-fallback plans (no-key/quota paths).

    Replaces the legacy mock DAG with the composer equivalent and attaches the
    _components record. Never raises; on any failure the mock DAG stands.
    """
    try:
        data["buildGraph"] = _compose_or_legacy_dag(data)
    except Exception as e:
        print(f"mock composition skipped: {e}")
    return data


def analyze_prompt(prompt: str) -> dict:
    """Single LLM call -> AppSpec, fallback to mock_build_plan on failure."""
    from prompts.analyzer import ANALYZER_SYSTEM_PROMPT

    try:
        from services.llm import has_any_llm
        has_llm = has_any_llm()
    except Exception:
        has_llm = bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("NVIDIA_API_KEY") or os.getenv("DEEPSEEK_API_KEY"))
    if not has_llm:
        from services.planner_v2 import mock_build_plan
        data = mock_build_plan(prompt)
        # enrich with analyzer defaults
        data["appType"] = data.get("appType", "dashboard")
        data["appKind"] = data.get("appKind", "interactive" if data.get("appType") in ("game", "tool", "showcase") else "crud")
        data["entities"] = data.get("entities", [{"name": t["name"], "fields": t["fields"], "relationships": [], "businessRules": []} for t in data.get("tables", [])])
        if "uiPatterns" not in data:
            if data["appKind"] == "interactive":
                data["uiPatterns"] = {"layout": "board-grid", "primaryEntity": None, "listStyle": "none", "detailStyle": "none",
                                      "features": ["local-2-player", "ai-opponent", "win-detection", "score-persistence"]}
            else:
                data["uiPatterns"] = {"layout": "top-nav-grid", "primaryEntity": data.get("tables", [{}])[0].get("name", "items") if data.get("tables") else "items", "listStyle": "card-grid", "detailStyle": "full-page", "features": ["search"]}
        data["_meta"] = {"source": "mock", "reason": "no_key", "analyzer": True}
        return _attach_composition(data)

    try:
        from services.llm import call_llm_with_meta
        from main import parse_json as main_parse
        full_prompt = ANALYZER_SYSTEM_PROMPT.replace("{prompt}", prompt)
        raw, meta = call_llm_with_meta(full_prompt)
        data = _parse_json(raw) if isinstance(raw, str) else raw
        # also try main_parse for robustness
        if not isinstance(data, dict) or "appName" not in data:
            try:
                data = main_parse(raw)
            except:
                pass
        errors = _validate_app_spec(data)
        if errors:
            raise ValueError(f"validation failed: {errors}")

        # Ensure tables derived if missing
        if "tables" not in data and "entities" in data:
            data["tables"] = _derive_tables_from_entities(data["entities"])
        elif "entities" not in data and "tables" in data:
            data["entities"] = [{"name": t["name"], "fields": t["fields"], "relationships": [], "businessRules": []} for t in data["tables"]]

        # Ensure pages have table binding (crud only — interactive pages are feature-bound)
        if _app_kind(data) == "crud":
            for p in data.get("pages", []):
                if "table" not in p and data.get("tables"):
                    p["table"] = data["tables"][0]["name"]

        # Build DAG if missing — prefer component composition (fail-soft to legacy)
        if "buildGraph" not in data:
            data["buildGraph"] = _compose_or_legacy_dag(data)

        # Ensure requirements/ia exist
        if "requirements" not in data:
            from services.planner_v2 import mock_build_plan
            tmp = mock_build_plan(prompt)
            data["requirements"] = tmp["requirements"]
            data["ia"] = tmp["ia"]

        data["_meta"] = {**meta, "analyzer": True}
        if "_components_warning" in data:
            data["_meta"]["components_warning"] = data.pop("_components_warning")
        return data

    except Exception as e:
        if _is_quota(e):
            # Graceful fallback to mock on quota (don't block user, just warn)
            print(f"analyzer quota hit, mock fallback with warning: {e}")
            from services.planner_v2 import mock_build_plan
            data = mock_build_plan(prompt)
            # Extract retry time if available
            retry_msg = str(e)
            # Try to parse retry time from Groq message like "Please try again in 3m55.44s"
            import re
            m = re.search(r"try again in ([\d\.]+[msh]+)", retry_msg, re.I)
            retry_hint = m.group(1) if m else "a few minutes"
            data["_meta"] = {"source": "mock", "reason": f"quota_fallback_retry_{retry_hint}", "analyzer": False, "warning": f"LLM quota hit (Groq 200k TPD). Using mock for now. Retry in {retry_hint} or add credits. Prompt: {prompt[:40]}"}
            return _attach_composition(data)
        print(f"analyzer failed, mock fallback: {e}")
        from services.planner_v2 import mock_build_plan
        data = mock_build_plan(prompt)
        data["_meta"] = {"source": "mock", "reason": str(e)[:120], "analyzer": False}
        return _attach_composition(data)
