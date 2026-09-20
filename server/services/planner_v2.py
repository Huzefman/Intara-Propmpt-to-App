"""
Planner v2 — prompt -> BuildPlan (requirements + IA + DAG)
"""
import os, json, re, uuid
from prompts.build_plan import BUILD_PLAN_PROMPT
from utils.json_parse import parse_json, is_quota_error

def mock_build_plan(prompt: str) -> dict:
    # Reuse planner mock_prd and enrich to BuildPlan
    from services.planner import mock_prd
    base = mock_prd(prompt)
    # enrich with requirements / IA / buildGraph
    tables = base["tables"]
    pages = base["pages"]
    # add table binding to pages if missing
    for idx, p in enumerate(pages):
        if "table" not in p:
            # guess from name/components
            cand = (p["name"] + " " + " ".join(p.get("components", []))).lower()
            chosen = None
            for t in tables:
                if t["name"] in cand or t["name"][:-1] in cand:
                    chosen = t["name"]; break
            if not chosen:
                chosen = tables[idx % len(tables)]["name"] if tables else "items"
            p["table"] = chosen
    req = {
        "functional": [
            f"As a user I want to {prompt[:60]}",
            f"As a user I want to create and list {tables[0]['name'] if tables else 'items'}",
            f"As a user I want to view {pages[0]['name']} at {pages[0]['route']}",
            "As a user I want auth and persistent data",
            "As a user I want to trial in browser without Supabase"
        ][:5],
        "nonFunctional": ["Dark nebula glass, responsive, fluid animations", "Free-tier runnable, SQLite fallback, Dexie trial"],
        "auth": base.get("auth", True),
        "roles": ["user", "admin"] if base.get("auth") else ["user"]
    }
    ia = {
        "entities": [t["name"] for t in tables],
        "relations": [f"users 1:N {t['name']}" for t in tables if t["name"] != "users"][:3],
        "nav": [f"{p['name']} -> {p['route']}" for p in pages]
    }
    # DAG: schema first, then per-table backend, per-page frontend, then wiring+validate
    graph = []
    graph.append({"id":"schema-foundation","kind":"schema","ref":None,"dependsOn":[],"status":"pending","promptHint":"tables+migrations"})
    for t in tables:
        graph.append({"id":f"backend-{t['name']}","kind":"backend_table","ref":t["name"],"dependsOn":["schema-foundation"],"status":"pending","promptHint":f"models+APIs for {t['name']}"})
    for p in pages:
        graph.append({"id":f"frontend-{p['name']}","kind":"frontend_page","ref":p["name"],"dependsOn":["schema-foundation"],"status":"pending","promptHint":f"page {p['name']} for table {p.get('table')}"})
    graph.append({"id":"wiring","kind":"wiring","ref":None,"dependsOn":[n["id"] for n in graph if n["id"]!="schema-foundation"],"status":"pending","promptHint":"App.tsx nav, api wiring, mock"})
    graph.append({"id":"validate","kind":"validate","ref":None,"dependsOn":["wiring"],"status":"pending","promptHint":"tsc/ast/openapi"})
    return {
        "appName": base["appName"],
        "tagline": base["tagline"],
        "requirements": req,
        "ia": ia,
        "entities": [{"name": t["name"], "fields": t["fields"], "relationships": [], "businessRules": []} for t in tables],
        "tables": tables,
        "pages": pages,
        "apis": base["apis"],
        "auth": base["auth"],
        "buildGraph": graph
    }

def _is_quota_error(e: Exception) -> bool:
    return is_quota_error(e)

def plan_build(prompt: str) -> dict:
    # LLM-first via analyzer (single call), fallback to mock
    try:
        from services.analyzer import analyze_prompt
        return analyze_prompt(prompt)
    except Exception as e:
        # analyzer already handles quota and fallback; if it raises 429, surface
        if _is_quota_error(e):
            raise
        print(f"analyzer failed, falling back to legacy plan_build: {e}")
    has_llm = bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY"))
    if not has_llm:
        data = mock_build_plan(prompt)
        data["_meta"] = {"source": "mock", "reason": "no_key", "model": "mock"}
        return data
    try:
        from services.llm import call_llm_with_meta
        from main import parse_json as main_parse
        raw, meta = call_llm_with_meta(BUILD_PLAN_PROMPT.format(prompt=prompt))
        try:
            data = main_parse(raw)
            if "appName" not in data or "tables" not in data or "pages" not in data:
                raise ValueError("missing keys")
            if "buildGraph" not in data:
                tmp = mock_build_plan(prompt)
                data["requirements"] = data.get("requirements", tmp["requirements"])
                data["ia"] = data.get("ia", tmp["ia"])
                for idx, p in enumerate(data.get("pages",[])):
                    if "table" not in p:
                        p["table"] = data["tables"][idx % len(data["tables"])]["name"] if data["tables"] else "items"
                graph = []
                graph.append({"id":"schema-foundation","kind":"schema","ref":None,"dependsOn":[],"status":"pending","promptHint":"schema"})
                for t in data["tables"]:
                    graph.append({"id":f"backend-{t['name']}","kind":"backend_table","ref":t["name"],"dependsOn":["schema-foundation"],"status":"pending","promptHint":f"backend {t['name']}"})
                for p in data["pages"]:
                    graph.append({"id":f"frontend-{p['name']}","kind":"frontend_page","ref":p["name"],"dependsOn":["schema-foundation"],"status":"pending","promptHint":f"frontend {p['name']}"})
                graph.append({"id":"wiring","kind":"wiring","ref":None,"dependsOn":[n["id"] for n in graph if n["id"]!="schema-foundation"],"status":"pending","promptHint":"wiring"})
                graph.append({"id":"validate","kind":"validate","ref":None,"dependsOn":["wiring"],"status":"pending","promptHint":"validate"})
                data["buildGraph"] = graph
            for p in data.get("pages",[]):
                if "table" not in p:
                    p["table"] = data["tables"][0]["name"] if data["tables"] else "items"
            data["_meta"] = meta
            return data
        except Exception as e:
            if _is_quota_error(e):
                raise
            from services.llm import call_llm_with_meta
            raw2, meta2 = call_llm_with_meta(f"Fix to valid BuildPlan JSON with appName,tables,pages,buildGraph: {raw}")
            try:
                data = main_parse(raw2)
                data["_meta"] = {**meta2, "repaired": True}
                return data
            except Exception as e2:
                if _is_quota_error(e2):
                    raise
                print(f"build plan repair failed: {e}, mock fallback")
                data = mock_build_plan(prompt)
                data["_meta"] = {"source": "mock", "reason": "repair_failed"}
                return data
    except Exception as e:
        if _is_quota_error(e):
            raise RuntimeError(f"429 LLM quota exhausted: {e}")
        print(f"planner_v2 fallback: {e}")
        data = mock_build_plan(prompt)
        data["_meta"] = {"source": "mock", "reason": str(e)[:120]}
        return data
