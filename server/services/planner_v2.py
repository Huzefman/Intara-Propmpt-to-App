"""
Planner v2 — prompt -> BuildPlan (requirements + IA + DAG)
"""
import os, json, re, uuid
from prompts.build_plan import BUILD_PLAN_PROMPT
from utils.json_parse import parse_json, is_quota_error

GAME_WORDS = ("tic tac", "tictactoe", "tic-tac", "chess", "checkers", "sudoku",
                "minesweeper", "snake", "pong", "tetris", "memory match", "memory game",
                "crossword", "2048", "board game", "card game", "2-player", "two player")


def _is_game_prompt(prompt: str) -> bool:
    p = (prompt or "").lower()
    return any(w in p for w in GAME_WORDS)


def mock_game_plan(prompt: str) -> dict:
    """Deterministic tic-tac-toe-shaped BuildPlan (no-key/quota fallback)."""
    tables = [
        {"name": "scores", "fields": [
            {"name": "player", "type": "text"},
            {"name": "wins", "type": "integer"},
            {"name": "losses", "type": "integer"},
            {"name": "draws", "type": "integer"},
        ]},
    ]
    pages = [
        {"name": "Game", "route": "/", "components": ["Board", "TurnIndicator", "Scoreboard"], "feature": "play"},
        {"name": "Scores", "route": "/scores", "components": ["Scoreboard"], "feature": "scores"},
    ]
    apis = [
        {"method": "GET", "path": "/api/scores", "desc": "list scores"},
        {"method": "POST", "path": "/api/scores", "desc": "save score"},
    ]
    graph = [
        {"id": "schema-foundation", "kind": "schema", "ref": None, "dependsOn": [], "status": "pending", "promptHint": "scores table"},
        {"id": "backend-scores", "kind": "backend_table", "ref": "scores", "dependsOn": ["schema-foundation"], "status": "pending", "promptHint": "scores GET+POST only"},
        {"id": "frontend-Game", "kind": "frontend_page", "ref": "Game", "dependsOn": ["schema-foundation"], "status": "pending", "promptHint": "board page + game logic"},
        {"id": "frontend-Scores", "kind": "frontend_page", "ref": "Scores", "dependsOn": ["schema-foundation"], "status": "pending", "promptHint": "scoreboard page"},
        {"id": "wiring", "kind": "wiring", "ref": None, "dependsOn": ["schema-foundation", "backend-scores", "frontend-Game", "frontend-Scores"], "status": "pending", "promptHint": "App.tsx game shell, scores mock"},
        {"id": "validate", "kind": "validate", "ref": None, "dependsOn": ["wiring"], "status": "pending", "promptHint": "tsc + game rule gates"},
    ]
    return {
        "appName": "TicTacToe",
        "tagline": "Three in a row, forged in stardust",
        "appType": "game",
        "appKind": "interactive",
        "gameType": "tictactoe",
        "requirements": {
            "functional": [
                "As a player I want a 3x3 board so that I can play tic-tac-toe",
                "As a player I want local 2-player mode so that we share one screen",
                "As a player I want an AI opponent so that I can play solo",
                "As a player I want persistent scores so that rivalries survive refresh",
                "As a player I want rematch in one tap so that games keep flowing",
            ],
            "nonFunctional": ["Dark nebula glass, responsive, fluid animations", "Free-tier runnable, Dexie trial scores"],
            "auth": False,
            "roles": ["player"],
        },
        "ia": {"entities": ["scores"], "relations": [], "nav": ["Game -> /", "Scores -> /scores"]},
        "entities": [{"name": "scores", "fields": tables[0]["fields"], "relationships": [], "businessRules": ["one row per player"]}],
        "tables": tables,
        "pages": pages,
        "apis": apis,
        "auth": False,
        "buildGraph": graph,
    }


def mock_build_plan(prompt: str) -> dict:
    if _is_game_prompt(prompt):
        return mock_game_plan(prompt)
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
        if getattr(e, "byok_error", False):
            raise
        if _is_quota_error(e):
            raise
        print(f"analyzer failed, falling back to legacy plan_build: {e}")
    try:
        from services.llm import has_any_llm
        has_llm = has_any_llm()
    except Exception:
        has_llm = bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("NVIDIA_API_KEY") or os.getenv("DEEPSEEK_API_KEY"))
    if not has_llm:
        data = mock_build_plan(prompt)
        data["_meta"] = {"source": "mock", "reason": "no_key", "model": "mock"}
        return data
    try:
        from services.llm import call_llm_with_meta
        from main import parse_json as main_parse
        raw, meta = call_llm_with_meta(BUILD_PLAN_PROMPT.format(prompt=prompt), json_mode=True)
        try:
            data = main_parse(raw)
            if "appName" not in data or "tables" not in data or "pages" not in data:
                raise ValueError("missing keys")
            if "buildGraph" not in data:
                tmp = mock_build_plan(prompt)
                data["requirements"] = data.get("requirements", tmp["requirements"])
                data["ia"] = data.get("ia", tmp["ia"])
                _kind = str(data.get("appKind") or ("interactive" if _is_game_prompt(prompt) else "crud")).lower()
                data["appKind"] = _kind
                for idx, p in enumerate(data.get("pages",[])):
                    if "table" not in p and _kind == "crud":
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
                if "table" not in p and str(data.get("appKind") or "crud").lower() == "crud":
                    p["table"] = data["tables"][0]["name"] if data["tables"] else "items"
            data["_meta"] = meta
            return data
        except Exception as e:
            if _is_quota_error(e):
                raise
            from services.llm import call_llm_with_meta
            raw2, meta2 = call_llm_with_meta(f"Fix to valid BuildPlan JSON with appName,tables,pages,buildGraph: {raw}", json_mode=True)
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
        if getattr(e, "byok_error", False):
            # A bad/expired user key must be visible, not hidden behind a mock.
            raise
        if _is_quota_error(e):
            # All providers exhausted — degrade to mock with warning (never 500).
            print(f"planner_v2 all-providers exhausted, mock fallback with warning: {e}")
            data = mock_build_plan(prompt)
            data["_meta"] = {"source": "mock", "reason": "all_exhausted", "warning": f"All LLM quotas exhausted. Using mock for now. Retry in ~60s. Prompt: {prompt[:40]}"}
            return data
        print(f"planner_v2 fallback: {e}")
        data = mock_build_plan(prompt)
        data["_meta"] = {"source": "mock", "reason": str(e)[:120]}
        return data
