"""
Analyzer — prompt -> AppSpec (rich BuildPlan superset)
Single LLM call, template fallback on failure.
"""
import os
import re
from utils.json_parse import parse_json as _parse_json, is_quota_error as _is_quota


def _validate_app_spec(data: dict) -> list[str]:
    errors = []
    if "appName" not in data:
        errors.append("missing appName")
    if "entities" not in data and "tables" not in data:
        errors.append("missing entities/tables")
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
    # pages reference valid entities
    valid_entities = {e["name"] for e in data.get("entities", [])} | {t["name"] for t in data.get("tables", [])}
    for p in data.get("pages", []):
        tbl = p.get("table")
        if tbl and tbl not in valid_entities:
            errors.append(f"page {p.get('name')} table {tbl} not in entities")
    return errors


def _derive_build_graph(app_spec: dict) -> list[dict]:
    """Auto-generate DAG from entities+pages (strict sequential)."""
    entities = app_spec.get("entities") or [{"name": t["name"]} for t in app_spec.get("tables", [])]
    pages = app_spec.get("pages", [])
    graph = []
    graph.append({"id": "schema-foundation", "kind": "schema", "ref": None, "dependsOn": [], "status": "pending", "promptHint": "tables+migrations with FKs"})
    for ent in entities:
        graph.append({"id": f"backend-{ent['name']}", "kind": "backend_table", "ref": ent["name"], "dependsOn": ["schema-foundation"], "status": "pending", "promptHint": f"models+APIs for {ent['name']}"})
    for p in pages:
        graph.append({"id": f"frontend-{p['name']}", "kind": "frontend_page", "ref": p["name"], "dependsOn": ["schema-foundation"], "status": "pending", "promptHint": f"page {p['name']} for table {p.get('table')}"})
    # wiring depends on all previous except schema
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


def analyze_prompt(prompt: str) -> dict:
    """Single LLM call -> AppSpec, fallback to mock_build_plan on failure."""
    from prompts.analyzer import ANALYZER_SYSTEM_PROMPT

    has_llm = bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY"))
    if not has_llm:
        from services.planner_v2 import mock_build_plan
        data = mock_build_plan(prompt)
        # enrich with analyzer defaults
        data["appType"] = data.get("appType", "dashboard")
        data["entities"] = data.get("entities", [{"name": t["name"], "fields": t["fields"], "relationships": [], "businessRules": []} for t in data.get("tables", [])])
        data["uiPatterns"] = data.get("uiPatterns", {"layout": "top-nav-grid", "primaryEntity": data.get("tables", [{}])[0].get("name", "items") if data.get("tables") else "items", "listStyle": "card-grid", "detailStyle": "full-page", "features": ["search"]})
        data["_meta"] = {"source": "mock", "reason": "no_key", "analyzer": True}
        return data

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

        # Ensure pages have table binding
        for p in data.get("pages", []):
            if "table" not in p and data.get("tables"):
                p["table"] = data["tables"][0]["name"]

        # Build DAG if missing
        if "buildGraph" not in data:
            data["buildGraph"] = _derive_build_graph(data)

        # Ensure requirements/ia exist
        if "requirements" not in data:
            from services.planner_v2 import mock_build_plan
            tmp = mock_build_plan(prompt)
            data["requirements"] = tmp["requirements"]
            data["ia"] = tmp["ia"]

        data["_meta"] = {**meta, "analyzer": True}
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
            return data
        print(f"analyzer failed, mock fallback: {e}")
        from services.planner_v2 import mock_build_plan
        data = mock_build_plan(prompt)
        data["_meta"] = {"source": "mock", "reason": str(e)[:120], "analyzer": False}
        return data
