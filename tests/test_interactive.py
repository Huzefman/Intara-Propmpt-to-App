"""
Interactive appKind tests — contract minimal modes + game rule gates. $0.
Run: pytest tests/test_interactive.py -v
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "server"))

from services.contract import (  # noqa: E402
    build_contract, table_routes, check_backend_routes, check_frontend_client,
    check_openapi,
)
from services.gates import run_game_gates  # noqa: E402

GAME_PRD = {
    "appName": "TicTacToe",
    "appKind": "game",
    "tagline": "play",
    "tables": [
        {"name": "scores", "fields": [
            {"name": "player", "type": "text"},
            {"name": "wins", "type": "integer"},
            {"name": "losses", "type": "integer"},
            {"name": "draws", "type": "integer"},
        ]},
    ],
    "pages": [{"name": "Game", "route": "/", "components": ["Board"]}],
    "apis": [
        {"method": "GET", "path": "/api/scores", "desc": "list scores"},
        {"method": "POST", "path": "/api/scores", "desc": "save score"},
    ],
    "auth": False,
}


def test_table_routes_subset():
    assert len(table_routes("scores")) == 6
    mini = table_routes("scores", ["GET", "POST"])
    assert [(r["method"], r["path"]) for r in mini] == [
        ("GET", "/api/scores"), ("POST", "/api/scores")]


def test_game_contract_minimal_routes():
    c = build_contract(GAME_PRD)
    assert c["appKind"] == "game"
    assert [(r["method"], r["path"]) for r in c["routes"]] == [
        ("GET", "/api/scores"), ("POST", "/api/scores")]


def test_game_contract_backendless():
    prd = {**GAME_PRD, "tables": [], "apis": []}
    c = build_contract(prd, [])
    assert c["routes"] == []
    # no backend files at all: exempt, not an error
    assert check_backend_routes([], c) == []
    assert check_openapi({}, c) == []


def test_crud_contract_unchanged():
    prd = {k: v for k, v in GAME_PRD.items() if k != "appKind"}
    c = build_contract(prd)
    assert len(c["routes"]) == 6
    assert "appKind" in c and c["appKind"] == "crud"


def test_backend_routes_minimal_accepts_scores_only():
    c = build_contract(GAME_PRD)
    main = '''from fastapi import FastAPI
app = FastAPI()
@app.get("/api/scores")
def list_scores(): return []
@app.post("/api/scores")
def create_scores(body: dict): return body
'''
    files = [{"path": "server/main.py", "content": main}]
    assert check_backend_routes(files, c) == []


def test_backend_routes_still_catches_missing_declared():
    c = build_contract(GAME_PRD)
    files = [{"path": "server/main.py", "content": "from fastapi import FastAPI\napp = FastAPI()\n"}]
    errs = check_backend_routes(files, c)
    assert any("POST /api/scores" in e for e in errs)


def test_frontend_client_minimal():
    c = build_contract(GAME_PRD)
    api = "export const listScores = () => baseFetch('/api/scores').then(r => r.json())\nexport const createScores = (body:any) => baseFetch('/api/scores', {method:'POST'}).then(r => r.json())\n"
    files = [{"path": "src/api.ts", "content": api},
             {"path": "src/pages/Game.tsx", "content": "import { listScores } from '../api'"}]
    assert check_frontend_client(files, c) == []


def test_openapi_minimal():
    c = build_contract(GAME_PRD)
    assert check_openapi({"openapi": "3.0.0", "paths": {
        "/api/scores": {"get": {}, "post": {}}}}, c) == []
    assert check_openapi({"openapi": "3.0.0", "paths": {}}, c) != []


GOOD_LOGIC = """
export type Cell = "X" | "O" | null;
export function calcWinner(b: Cell[]): "X" | "O" | null {
  const L = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
  for (const [a,c,d] of L) { if (b[a] && b[a] === b[c] && b[a] === b[d]) return b[a]; }
  return null;
}
export function isDraw(b: Cell[]): boolean {
  return b.every((v) => v !== null) && calcWinner(b) === null;
}
export function legalMoves(b: Cell[]): number[] {
  const out: number[] = [];
  b.forEach((v, i) => { if (v === null) out.push(i); });
  return out;
}
export function applyMove(b: Cell[], i: number, p: "X" | "O"): Cell[] {
  if (b[i] !== null) throw new Error("occupied");
  const nb = b.slice(); nb[i] = p; return nb;
}
function minimax(b: Cell[], turn: "X" | "O", me: "X" | "O", depth: number): number {
  const w = calcWinner(b);
  if (w === me) return 10 - depth;
  if (w) return depth - 10;
  if (isDraw(b)) return 0;
  const moves = legalMoves(b);
  let best = turn === me ? -Infinity : Infinity;
  for (const m of moves) {
    const nb = b.slice(); nb[m] = turn;
    const s = minimax(nb, turn === "X" ? "O" : "X", me, depth + 1);
    best = turn === me ? Math.max(best, s) : Math.min(best, s);
  }
  return best;
}
export function bestMove(b: Cell[], me: "X" | "O"): number {
  let bi = -1, bs = -Infinity;
  for (const m of legalMoves(b)) {
    const nb = b.slice(); nb[m] = me;
    const s = minimax(nb, me === "X" ? "O" : "X", me, 0);
    if (s > bs) { bs = s; bi = m; }
  }
  return bi;
}
"""

BAD_LOGIC = """
export function calcWinner(b: any[]): any {
  if (b[0] && b[0] === b[1] && b[0] === b[2]) return b[0];
  return null;
}
"""


def _tree(logic_src: str):
    return [{"path": "src/game/logic.ts", "content": logic_src}]


def test_game_gates_green_on_good_logic():
    import shutil
    if shutil.which("node") is None or shutil.which("npx") is None:
        import pytest
        pytest.skip("node toolchain missing")
    errs = run_game_gates(_tree(GOOD_LOGIC), {"gameType": "tictactoe"})
    assert errs == [], errs[:3]


def test_game_gates_red_on_bad_logic():
    import shutil
    if shutil.which("node") is None or shutil.which("npx") is None:
        import pytest
        pytest.skip("node toolchain missing")
    errs = run_game_gates(_tree(BAD_LOGIC), {"gameType": "tictactoe"})
    assert errs, "expected rule failures for col/diag-blind logic"


def test_game_gates_skip_without_logic():
    assert run_game_gates([{"path": "src/pages/Game.tsx", "content": "x"}], {"gameType": "tictactoe"}) == []
    assert run_game_gates(_tree(GOOD_LOGIC), {"gameType": "chess"}) == []


def test_game_gates_reject_imports():
    errs = run_game_gates(
        [{"path": "src/game/logic.ts", "content": 'import { x } from "./x"\nexport function calcWinner(b:any){return null}'}],
        {"gameType": "tictactoe"})
    assert any("import-free" in e for e in errs)


# ---------- phase 2: analyzer taxonomy + game prompts ----------

def test_analyzer_accepts_game_spec():
    from services.analyzer import _validate_app_spec, _app_kind
    spec = {
        "appName": "TicTacToe", "appType": "game", "appKind": "interactive",
        "gameType": "tictactoe",
        "entities": [{"name": "scores", "fields": [{"name": "player", "type": "text"}],
                      "relationships": [], "businessRules": []}],
        "tables": [{"name": "scores", "fields": [{"name": "player", "type": "text"}]}],
        "pages": [{"name": "Game", "route": "/", "components": ["Board"], "feature": "play"}],
        "apis": [{"method": "GET", "path": "/api/scores"}, {"method": "POST", "path": "/api/scores"}],
    }
    assert _validate_app_spec(spec) == []
    assert _app_kind(spec) == "interactive"


def test_analyzer_rejects_crud_page_without_table():
    from services.analyzer import _validate_app_spec
    spec = {"appName": "X", "appType": "dashboard",
            "tables": [{"name": "tasks", "fields": [{"name": "title", "type": "text"}]}],
            "pages": [{"name": "Dashboard", "route": "/"}]}
    assert any("needs a table binding" in e for e in _validate_app_spec(spec))


def test_analyzer_derives_appkind_from_apptype():
    from services.analyzer import _validate_app_spec, _app_kind
    assert _app_kind({"appType": "game"}) == "interactive"
    assert _app_kind({"appType": "tool"}) == "interactive"
    assert _app_kind({"appType": "dashboard"}) == "crud"
    assert _app_kind({"appKind": "crud", "appType": "game"}) == "crud"


def test_mock_game_plan_shape():
    from services.planner_v2 import mock_build_plan, mock_game_plan
    plan = mock_build_plan("a tic tac toe game with local 2-player")
    assert plan["appKind"] == "interactive" and plan["gameType"] == "tictactoe"
    assert [t["name"] for t in plan["tables"]] == ["scores"]
    assert all("table" not in p for p in plan["pages"])
    assert sorted((a["method"], a["path"]) for a in plan["apis"]) == [
        ("GET", "/api/scores"), ("POST", "/api/scores")]
    assert plan["auth"] is False
    kinds = [n["kind"] for n in plan["buildGraph"]]
    assert "backend-scores" in [n["id"] for n in plan["buildGraph"]]
    assert "validate" in kinds and "wiring" in kinds
    # crud prompts unaffected
    crud = mock_build_plan("a task tracker with users and tasks")
    assert crud.get("appKind", "crud") != "interactive"
    assert crud["tables"] and crud["pages"][0].get("table")


def test_game_plan_contract_minimal():
    from services.planner_v2 import mock_game_plan
    c = build_contract(mock_game_plan("tic tac toe"))
    assert c["appKind"] == "interactive"
    assert [(r["method"], r["path"]) for r in c["routes"]] == [
        ("GET", "/api/scores"), ("POST", "/api/scores")]


def test_analyzer_no_key_game_fallback(monkeypatch):
    import os
    for k in ["OPENROUTER_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY",
              "DEEPSEEK_API_KEY", "LLM_ONLY"]:
        monkeypatch.delenv(k, raising=False)
    from services.analyzer import analyze_prompt
    data = analyze_prompt("tic tac toe with AI opponent")
    assert data["appKind"] == "interactive"
    assert data["_meta"]["source"] == "mock"
    assert data["uiPatterns"]["layout"] == "board-grid"


def test_derive_graph_skips_schema_without_tables():
    from services.analyzer import _derive_build_graph
    g = _derive_build_graph({"entities": [], "tables": [], "pages": [{"name": "Game", "route": "/"}]})
    ids = [n["id"] for n in g]
    assert "schema-foundation" not in ids
    assert ids[0] == "frontend-Game" and ids[-2:] == ["wiring", "validate"]


def test_game_page_prompt_directives():
    from prompts.frontend_page_v2 import build_frontend_game_prompt
    page = {"name": "Game", "route": "/", "components": ["Board"]}
    spec = {"appName": "TicTacToe", "tagline": "play", "gameType": "tictactoe",
            "uiPatterns": {"features": ["local-2-player"]}}
    prompt = build_frontend_game_prompt(page, spec)
    assert "export default function Game" in prompt
    assert "src/game/logic.ts" in prompt
    assert "calcWinner" in prompt and "bestMove" in prompt
    assert "ZERO imports in logic.ts" in prompt


def test_scores_prompt_minimal():
    from prompts.backend_table_v2 import build_backend_scores_prompt
    table = {"name": "scores", "fields": [{"name": "player", "type": "text"}]}
    spec = {"appName": "TicTacToe",
            "apis": [{"method": "GET", "path": "/api/scores"}, {"method": "POST", "path": "/api/scores"}]}
    prompt = build_backend_scores_prompt(table, spec)
    assert "Declared routes ONLY" in prompt
    assert "PUT" not in prompt and "DELETE" not in prompt


def test_schema_game_prompt_no_fk_demands():
    from prompts.schema_v2 import build_schema_game_prompt
    prompt = build_schema_game_prompt({"appName": "T", "tables": [
        {"name": "scores", "fields": [{"name": "player", "type": "text"}]}]})
    assert "REQUIRED FK" not in prompt
    assert "scores" in prompt


# ---------- phase 3: deterministic game templates ----------

GAME_TEMPLATE_PRD = {
    "appName": "TicTacToe",
    "appKind": "interactive",
    "gameType": "tictactoe",
    "tagline": "play",
    "tables": [
        {"name": "scores", "fields": [
            {"name": "player", "type": "text"},
            {"name": "wins", "type": "integer"},
            {"name": "losses", "type": "integer"},
            {"name": "draws", "type": "integer"},
        ]},
    ],
    "pages": [
        {"name": "Game", "route": "/", "components": ["Board"], "feature": "play"},
        {"name": "Scores", "route": "/scores", "components": ["Scoreboard"], "feature": "scores"},
    ],
    "apis": [
        {"method": "GET", "path": "/api/scores", "desc": "list"},
        {"method": "POST", "path": "/api/scores", "desc": "save"},
    ],
    "entities": [{"name": "scores", "fields": [], "relationships": [], "businessRules": []}],
    "auth": False,
}


def _template_only(monkeypatch):
    monkeypatch.setenv("INTARA_TEMPLATE_ONLY", "1")


def test_game_template_emits_board_and_logic(monkeypatch):
    _template_only(monkeypatch)
    from services.generators.frontend_gen import generate_frontend
    files = {f["path"]: f["content"] for f in generate_frontend(GAME_TEMPLATE_PRD)["files"]}
    assert "src/game/logic.ts" in files
    assert "src/pages/Game.tsx" in files and "src/pages/Scores.tsx" in files
    assert "export default function Game" in files["src/pages/Game.tsx"]
    assert "export default function Scores" in files["src/pages/Scores.tsx"]
    assert "import" not in files["src/game/logic.ts"].split("export")[0]
    for name in ("calcWinner", "isDraw", "legalMoves", "applyMove", "bestMove"):
        assert name in files["src/game/logic.ts"]


def test_game_template_api_minimal(monkeypatch):
    _template_only(monkeypatch)
    from services.generators.frontend_gen import generate_frontend
    files = {f["path"]: f["content"] for f in generate_frontend(GAME_TEMPLATE_PRD)["files"]}
    api = files["src/api.ts"]
    assert "listScores" in api and "createScores" in api
    assert "putScoresById" not in api and "deleteScoresById" not in api


def test_game_template_passes_contract_checks(monkeypatch):
    _template_only(monkeypatch)
    from services.contract import build_contract, check_backend_routes, check_frontend_client, check_openapi, check_placeholders, check_no_template_tokens
    from services.generators.frontend_gen import generate_frontend
    from services.generators.backend_gen import generate_backend
    c = build_contract(GAME_TEMPLATE_PRD)
    fe = generate_frontend(GAME_TEMPLATE_PRD)["files"]
    be = generate_backend(GAME_TEMPLATE_PRD)
    assert check_placeholders(fe + be["files"]) == []
    assert check_no_template_tokens(fe + be["files"]) == []
    assert check_backend_routes(be["files"], c) == []
    assert check_frontend_client(fe, c) == []
    assert check_openapi(be["openapi"], c) == []


def test_game_template_logic_passes_rule_gates(monkeypatch):
    _template_only(monkeypatch)
    import shutil
    if shutil.which("node") is None or shutil.which("npx") is None:
        import pytest
        pytest.skip("node toolchain missing")
    from services.generators.frontend_gen import generate_frontend
    files = generate_frontend(GAME_TEMPLATE_PRD)["files"]
    errs = run_game_gates(files, {"gameType": "tictactoe"})
    assert errs == [], errs[:3]


def test_game_backend_template_scores_only(monkeypatch):
    _template_only(monkeypatch)
    from services.generators.backend_gen import generate_backend
    be = generate_backend(GAME_TEMPLATE_PRD)
    main = next(f["content"] for f in be["files"] if f["path"] == "server/main.py")
    assert '@app.get("/api/scores")' in main and '@app.post("/api/scores")' in main
    assert "@app.put(" not in main and "@app.patch(" not in main and "@app.delete(" not in main
    compile(main, "server/main.py", "exec")
    assert set(be["openapi"]["paths"].keys()) == {"/api/scores"}


def test_game_mock_scores_only(monkeypatch):
    _template_only(monkeypatch)
    from services.preview.mock_gen import generate_mock
    mock = generate_mock(GAME_TEMPLATE_PRD)
    server = mock["src/mock/server.ts"]
    assert "/api/scores" in server
    assert "PUT" not in server and "PATCH" not in server and "DELETE" not in server
    assert "scores" in mock["src/mock/db.ts"]


def test_be_matrix_enforces_declared_post(monkeypatch):
    _template_only(monkeypatch)
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")
    from services.generators.backend_gen import generate_backend
    from services.generators.scaffold_gen import backend_scaffold
    from services.contract import build_contract, ddl_for
    from services.gates import run_be_gates
    prd = dict(GAME_TEMPLATE_PRD)
    c = build_contract(prd)
    be = generate_backend(prd)
    scaf = backend_scaffold("TicTacToe", c["tables"], ddl_for(c))
    tree = [{"path": p, "content": v} for p, v in scaf.items()] + be["files"]
    seen, full = set(), []
    for f in tree:
        if f["path"] not in seen:
            seen.add(f["path"])
            full.append(f)
    assert run_be_gates(full, c) == []
    # break POST -> matrix must go red (declared routes are enforced, not optional)
    broken = [dict(f) for f in full]
    for f in broken:
        if f["path"] == "server/main.py":
            f["content"] = f["content"].replace('@app.post("/api/scores")', '@app.get("/api/scores-dummy")', 1)
    assert run_be_gates(broken, c) != []
