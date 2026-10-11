"""
Component architecture tests — catalog validity, composer resolution, migration safety.
Deterministic, $0, no network, no Supabase. Run: pytest tests/test_components.py -v
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "server"))

from components.registry import (  # noqa: E402
    CatalogError,
    check_params,
    get_component,
    load_catalog,
    pack_for_category,
    validate_entry,
)
from components.composer import compose, compose_category, to_dag  # noqa: E402

ANALYZER_TYPES = {"catalog", "dashboard", "marketplace", "social", "booking",
                  "form-wizard", "content-management", "game", "tool", "showcase"}


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def test_catalog_loads_clean(catalog):
    assert len(catalog["components"]) >= 12
    kinds = {e["kind"] for e in catalog["components"].values()}
    assert {"entity", "page", "api", "widget", "integration", "workflow"} <= kinds
    statuses = {e["status"] for e in catalog["components"].values()}
    assert "stable" in statuses and "planned" in statuses


def test_packs_cover_analyzer_taxonomy(catalog):
    assert ANALYZER_TYPES <= set(catalog["categories"].keys()), \
        f"missing packs: {ANALYZER_TYPES - set(catalog['categories'].keys())}"
    for cat, ids in catalog["categories"].items():
        for cid in ids:
            assert cid in catalog["components"], f"pack {cat} -> unknown {cid}"


def test_stable_entries_have_generators(catalog):
    for eid, e in catalog["components"].items():
        if e["status"] == "stable":
            assert isinstance(e["generator"], dict), eid
            assert e["generator"].get("module", "").startswith("services.generators"), eid
            assert e["gates"], f"{eid} stable but gateless"


def test_validate_entry_rejects_bad_shapes():
    assert validate_entry({"id": "x"}, "t") != []
    assert validate_entry({"id": "x", "version": "1.0.0", "kind": "nope",
                           "title": "", "description": "", "categories": ["dashboard"],
                           "status": "stable", "requires": [], "conflicts": [],
                           "params": {}, "generator": {}, "gates": [],
                           "capabilities": []}, "t") != []
    assert validate_entry({"id": "x", "version": "v1", "kind": "page",
                           "title": "", "description": "", "categories": ["dashboard"],
                           "status": "stable", "requires": [], "conflicts": [],
                           "params": {}, "generator": {}, "gates": [],
                           "capabilities": []}, "t") != []


def test_check_params_defaults_and_required(catalog):
    entry = get_component(catalog, "crud-entity")
    problems, filled = check_params(entry, {"table": "tasks", "fields": [{"name": "title", "type": "text"}]})
    assert problems == [] and filled["table"] == "tasks"
    problems, _ = check_params(entry, {"table": "tasks"})
    assert any("fields" in p for p in problems)
    auth = get_component(catalog, "auth-users")
    problems, filled = check_params(auth, {})
    assert problems == [] and filled["table"] == "users"


def test_compose_game_pack(catalog):
    comp = compose_category(catalog, "game")
    ids = comp["order"]
    assert "scores-table" in ids and "game-board" in ids and "scores-api" in ids
    assert "charts" not in ids  # planned never auto-included
    dag = to_dag(catalog, comp)
    node_ids = [n["id"] for n in dag]
    assert len(node_ids) == len(set(node_ids)), "DAG ids must be unique"
    assert node_ids[0] == "schema-foundation"
    assert "backend-scores" in node_ids
    assert "frontend-Game" in node_ids  # game-board defaults to the canonical Game page
    assert node_ids[-2:] == ["wiring", "validate"]
    for n in dag:
        assert set(n) >= {"id", "kind", "ref", "dependsOn", "status", "promptHint"}


def test_compose_explicit_crud_selection(catalog):
    comp = compose(catalog, [
        {"id": "crud-entity", "config": {"table": "tasks", "fields": [{"name": "title", "type": "text"}]}},
        {"id": "list-page", "config": {"page": "Dashboard", "route": "/", "entity": "tasks"}},
        {"id": "crud-api", "config": {"entity": "tasks"}},
    ])
    dag = to_dag(catalog, comp)
    ids = [n["id"] for n in dag]
    assert ids == ["schema-foundation", "backend-tasks", "frontend-Dashboard", "wiring", "validate"]
    # dependency order: entity backend before its page
    assert ids.index("backend-tasks") < ids.index("frontend-Dashboard")


def test_compose_rejects_planned_unknown_and_conflicts(catalog):
    with pytest.raises(CatalogError):
        compose(catalog, [{"id": "charts", "config": {"entity": "tasks"}}])
    with pytest.raises(CatalogError):
        compose(catalog, [{"id": "no-such-thing", "config": {}}])
    with pytest.raises(CatalogError):
        compose(catalog, [{"id": "list-page", "config": {"page": "X", "route": "/"}}])  # missing entity


def test_compose_conflict_and_cycle():
    base = {"components": {
        "a": {"id": "a", "version": "1.0.0", "kind": "page", "title": "", "description": "",
              "categories": ["dashboard"], "status": "stable", "requires": [],
              "conflicts": ["b"], "params": {}, "generator": {}, "gates": [], "capabilities": []},
        "b": {"id": "b", "version": "1.0.0", "kind": "page", "title": "", "description": "",
              "categories": ["dashboard"], "status": "stable", "requires": [],
              "conflicts": [], "params": {}, "generator": {}, "gates": [], "capabilities": []},
        "x": {"id": "x", "version": "1.0.0", "kind": "page", "title": "", "description": "",
              "categories": ["dashboard"], "status": "stable", "requires": ["y"],
              "conflicts": [], "params": {}, "generator": {}, "gates": [], "capabilities": []},
        "y": {"id": "y", "version": "1.0.0", "kind": "page", "title": "", "description": "",
              "categories": ["dashboard"], "status": "stable", "requires": ["x"],
              "conflicts": [], "params": {}, "generator": {}, "gates": [], "capabilities": []},
    }, "categories": {}, "version": "1.0.0"}
    with pytest.raises(CatalogError, match="conflict"):
        compose(base, [{"id": "a"}, {"id": "b"}])
    with pytest.raises(CatalogError, match="cycle"):
        compose(base, [{"id": "x"}])
    with pytest.raises(CatalogError, match="unknown category"):
        compose_category(base, "nope")


def test_compose_deterministic(catalog):
    sel = [{"id": "stat-cards", "config": {"entity": "tasks"}},
           {"id": "crud-entity", "config": {"table": "tasks", "fields": []}},
           {"id": "list-page", "config": {"page": "Dashboard", "route": "/", "entity": "tasks"}}]
    assert compose(catalog, sel)["order"] == compose(catalog, sel)["order"]


def test_migration_is_additive_and_safe():
    sql = (ROOT / "supabase" / "migrations" / "005_component_registry.sql").read_text()
    assert "create table if not exists component_defs" in sql
    assert "create table if not exists wish_components" in sql
    assert "references wishes(id) on delete cascade" in sql
    lowered = sql.lower()
    assert "drop table" not in lowered
    assert "delete from wishes" not in lowered and "delete from wish_steps" not in lowered
    assert "truncate" not in lowered


# ---------- seed script credentials + errors (no network) ----------

def _load_seed_module():
    import importlib.util
    path = ROOT / "scripts" / "seed_components.py"
    spec = importlib.util.spec_from_file_location("seed_components", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hermetic_env_file(monkeypatch, tmp_path, body: str) -> str:
    """Isolated env file + cleared credential vars (auto-restored by monkeypatch)."""
    path = tmp_path / ".env.test"
    path.write_text(body)
    for k in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY"):
        monkeypatch.delenv(k, raising=False)
    return str(path)


def test_seed_prefers_service_key(monkeypatch, tmp_path):
    mod = _load_seed_module()
    env_file = _hermetic_env_file(
        monkeypatch, tmp_path,
        "SUPABASE_URL=https://x.supabase.co\n"
        "SUPABASE_KEY=publishable\n"
        "SUPABASE_SERVICE_KEY=service-role\n")
    url, key, using_service = mod.resolve_seed_credentials(env_file)
    assert (url, key, using_service) == ("https://x.supabase.co", "service-role", True)


def test_seed_falls_back_with_flag(monkeypatch, tmp_path):
    mod = _load_seed_module()
    env_file = _hermetic_env_file(
        monkeypatch, tmp_path,
        "SUPABASE_URL=https://x.supabase.co\nSUPABASE_KEY=publishable\n")
    url, key, using_service = mod.resolve_seed_credentials(env_file)
    assert (url, key, using_service) == ("https://x.supabase.co", "publishable", False)


def test_seed_explains_rls_denial():
    mod = _load_seed_module()
    msg = mod.explain_seed_error(Exception('{"message": "new row violates row-level security policy", "code": "42501"}'))
    assert "SUPABASE_SERVICE_KEY" in msg and "service_role" in msg


def test_seed_explains_missing_table():
    mod = _load_seed_module()
    msg = mod.explain_seed_error(Exception('relation "component_defs" does not exist'))
    assert "005_component_registry" in msg


def test_seed_dry_run_ok(capsys):
    mod = _load_seed_module()
    import sys as _sys
    old = _sys.argv
    _sys.argv = ["seed_components.py", "--dry-run"]
    try:
        assert mod.main() == 0
    finally:
        _sys.argv = old
    out = capsys.readouterr().out
    from components.registry import load_catalog
    assert f"{len(load_catalog()['components'])} components" in out


# ---------- AppSpec -> selections + analyzer integration ----------

def _taskorb_spec():
    return {
        "appName": "TaskOrb", "appType": "dashboard", "appKind": "crud",
        "tables": [
            {"name": "users", "fields": [{"name": "email", "type": "text"}]},
            {"name": "tasks", "fields": [{"name": "title", "type": "text"},
                                         {"name": "completed", "type": "boolean"}]},
        ],
        "entities": [
            {"name": "users", "fields": [{"name": "email", "type": "text"}], "relationships": []},
            {"name": "tasks", "fields": [{"name": "title", "type": "text"}],
             "relationships": [{"target": "users", "type": "belongs_to", "fk": "user_id"}]},
        ],
        "pages": [
            {"name": "Dashboard", "route": "/", "components": ["TaskList"], "table": "tasks"},
            {"name": "TaskDetail", "route": "/tasks/:id", "components": ["TaskForm"], "table": "tasks"},
            {"name": "Profile", "route": "/profile", "components": ["UserProfile"], "table": "users"},
        ],
        "apis": [
            {"method": "GET", "path": "/api/tasks"},
            {"method": "POST", "path": "/api/tasks"},
        ],
        "auth": True,
    }


def _game_spec():
    return {
        "appName": "TicTacToe", "appType": "game", "appKind": "interactive",
        "gameType": "tictactoe",
        "tables": [{"name": "scores", "fields": [{"name": "player", "type": "text"}]}],
        "entities": [{"name": "scores", "fields": [{"name": "player", "type": "text"}],
                      "relationships": [], "businessRules": []}],
        "pages": [
            {"name": "Game", "route": "/", "components": ["Board"], "feature": "play"},
            {"name": "Scores", "route": "/scores", "components": ["Scoreboard"], "feature": "scores"},
        ],
        "apis": [
            {"method": "GET", "path": "/api/scores"},
            {"method": "POST", "path": "/api/scores"},
        ],
        "auth": False,
    }


def test_select_crud_spec():
    from components.select import selections_for_appspec
    sel, warnings = selections_for_appspec(_taskorb_spec())
    ids = [s["id"] for s in sel]
    assert "crud-entity" in ids and "list-page" in ids and "detail-page" in ids
    assert "crud-api" in ids and "auth-users" in ids
    assert warnings == []
    by_id = {}
    for s in sel:
        by_id.setdefault(s["id"], []).append(s.get("config", {}))
    assert {"tasks", "users"} <= {c.get("table") or c.get("entity") for cfgs in by_id.values() for c in cfgs}


def test_select_game_spec():
    from components.select import selections_for_appspec
    sel, warnings = selections_for_appspec(_game_spec())
    ids = [s["id"] for s in sel]
    assert ids.count("scores-table") == 1
    assert "game-board" in ids and "scores-list" in ids and "scores-api" in ids
    assert "crud-entity" not in ids and warnings == []


def test_select_unknown_feature_warns():
    from components.select import selections_for_appspec
    spec = _game_spec()
    spec["pages"] = [{"name": "Mystery", "route": "/mystery", "components": ["X"], "feature": "teleport"}]
    sel, warnings = selections_for_appspec(spec)
    assert warnings and "Mystery" in warnings[0]
    assert all(s["id"] != "game-board" or s["config"].get("page") != "Mystery" for s in sel)


def test_composed_dag_matches_legacy_shape():
    from components.composer import compose, to_dag
    from components.registry import load_catalog
    from components.select import selections_for_appspec
    from services.analyzer import _derive_build_graph
    spec = _taskorb_spec()
    sel, warnings = selections_for_appspec(spec)
    assert warnings == []
    catalog = load_catalog()
    composed = to_dag(catalog, compose(catalog, sel))
    legacy = _derive_build_graph(spec)
    assert [n["id"] for n in composed] == [n["id"] for n in legacy]
    assert [(n["kind"], n["ref"]) for n in composed] == [(n["kind"], n["ref"]) for n in legacy]
    for cn, ln in zip(composed, legacy):
        assert cn["dependsOn"] == ln["dependsOn"]
        assert cn["status"] == "pending"


def test_game_composed_dag_shape():
    from components.composer import compose, to_dag
    from components.registry import load_catalog
    from components.select import selections_for_appspec
    catalog = load_catalog()
    comp = compose(catalog, selections_for_appspec(_game_spec())[0])
    ids = [n["id"] for n in to_dag(catalog, comp)]
    assert ids == ["schema-foundation", "backend-scores", "frontend-Game",
                   "frontend-Scores", "wiring", "validate"]


def test_analyzer_attaches_composition_no_key(monkeypatch):
    for k in ["OPENROUTER_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY",
              "DEEPSEEK_API_KEY", "LLM_ONLY"]:
        monkeypatch.delenv(k, raising=False)
    from services.analyzer import analyze_prompt
    data = analyze_prompt("a task tracker with users and tasks")
    assert data["_components"]["order"]
    assert data["_components"]["catalog_version"]
    assert [n["id"] for n in data["buildGraph"]][:2] == ["schema-foundation", "backend-users"]
    game = analyze_prompt("tic tac toe with AI opponent")
    gids = [n["id"] for n in game["buildGraph"]]
    assert "backend-scores" in gids and "frontend-Game" in gids


def test_rows_for_wish_pure():
    from components.registry import load_catalog
    from components.store import rows_for_wish
    catalog = load_catalog()
    prd = {"_components": {"order": ["scores-table", "game-board"],
                           "units": [{"component": "scores-table", "config": {}},
                                     {"component": "game-board", "config": {"page": "Game"}}]}}
    rows = rows_for_wish("wid-1", prd, catalog)
    assert [(r["component_id"], r["status"]) for r in rows] == [
        ("scores-table", "pending"), ("game-board", "pending")]
    assert all(r["wish_id"] == "wid-1" and r["version"] for r in rows)
    assert rows_for_wish("wid-1", {}, catalog) == []
    assert rows_for_wish("wid-1", {"_components": {"units": [{"component": "nope", "config": {}}]}}, catalog) == []


# ---------- csv-export component (stable) ----------

def _csv_prd(entity="tasks"):
    return {
        "appName": "T", "appKind": "crud", "tables": [
            {"name": "tasks", "fields": [{"name": "title", "type": "text"}]},
            {"name": "users", "fields": [{"name": "email", "type": "text"}]},
        ],
        "pages": [
            {"name": "Dashboard", "route": "/", "components": [], "table": "tasks"},
            {"name": "Members", "route": "/members", "components": [], "table": "users"},
        ],
        "apis": [], "auth": False,
        "_components": {"order": ["crud-entity", "csv-export"],
                        "units": [{"component": "crud-entity", "config": {"table": "tasks"}},
                                  {"component": "csv-export", "config": {"entity": entity}}]},
    }


def test_csv_template_emits_button_and_helper(monkeypatch):
    monkeypatch.setenv("INTARA_TEMPLATE_ONLY", "1")
    from services.generators.frontend_gen import generate_frontend
    files = {f["path"]: f["content"] for f in generate_frontend(_csv_prd())["files"]}
    assert "src/lib/csv.ts" in files
    dash = files["src/pages/Dashboard.tsx"]
    assert "downloadCsv(" in dash and "Export CSV" in dash
    assert "from '../lib/csv'" in dash
    assert "__CSV" not in dash


def test_csv_template_entity_scoped(monkeypatch):
    monkeypatch.setenv("INTARA_TEMPLATE_ONLY", "1")
    from services.generators.frontend_gen import generate_frontend
    files = {f["path"]: f["content"] for f in generate_frontend(_csv_prd(entity="users"))["files"]}
    assert "downloadCsv(" in files["src/pages/Members.tsx"]
    assert "downloadCsv(" not in files["src/pages/Dashboard.tsx"]
    assert "src/lib/csv.ts" in files  # helper still emitted once


def test_csv_template_off_without_component(monkeypatch):
    monkeypatch.setenv("INTARA_TEMPLATE_ONLY", "1")
    from services.generators.frontend_gen import generate_frontend
    prd = _csv_prd()
    del prd["_components"]
    files = {f["path"]: f["content"] for f in generate_frontend(prd)["files"]}
    assert "src/lib/csv.ts" not in files
    assert "downloadCsv(" not in files["src/pages/Dashboard.tsx"]


def test_check_csv_export_pass_and_fail():
    from services.contract import check_csv_export
    comps = [{"component": "csv-export", "config": {"entity": "tasks"}}]
    good = [{"path": "src/lib/csv.ts", "content": "export function downloadCsv() {}"},
            {"path": "src/pages/Dashboard.tsx", "content": "downloadCsv(rows)"}]
    assert check_csv_export(good, comps) == []
    assert check_csv_export([], []) == []
    no_button = [{"path": "src/lib/csv.ts", "content": "x"},
                 {"path": "src/pages/Dashboard.tsx", "content": "nothing here"}]
    errs = check_csv_export(no_button, comps)
    assert len(errs) == 1 and "src/pages/Dashboard.tsx" in errs[0]
    no_helper = [{"path": "src/pages/Dashboard.tsx", "content": "downloadCsv(rows)"}]
    assert any("src/lib/csv.ts" in e for e in check_csv_export(no_helper, comps))


def test_csv_check_runs_in_contract_battery(monkeypatch):
    monkeypatch.setenv("INTARA_TEMPLATE_ONLY", "1")
    from services.contract import build_contract
    from services.gates import run_contract_checks
    from services.generators.frontend_gen import generate_frontend
    from services.generators.backend_gen import generate_backend
    from services.generators.scaffold_gen import frontend_scaffold
    prd = _csv_prd()
    c = build_contract(prd)
    fe = generate_frontend(prd)["files"]
    be = generate_backend(prd)
    scaf = frontend_scaffold("T")
    errs = run_contract_checks(c, fe, be["files"], be["openapi"], scaf.get("package.json", ""), scaf.get("postcss.config.js"))
    assert not [e for e in errs if "csv" in e.lower() or "downloadCsv" in e], errs[:5]


def test_csv_catalog_stable():
    from components.registry import load_catalog
    e = load_catalog()["components"]["csv-export"]
    assert e["status"] == "stable"
    assert e["generator"]["module"] == "services.generators.frontend_gen"
    assert "check_csv_export" in e["gates"]


def test_select_export_keyword_adds_units():
    from components.select import selections_for_appspec
    spec = {
        "appName": "TaskOrb", "appType": "dashboard", "appKind": "crud",
        "tagline": "Track tasks and export weekly CSV reports",
        "tables": [{"name": "tasks", "fields": [{"name": "title", "type": "text"}]}],
        "entities": [{"name": "tasks", "fields": [], "relationships": []}],
        "pages": [{"name": "Dashboard", "route": "/", "components": [], "table": "tasks"}],
        "requirements": {"functional": ["As a user I want to download data so that I can share it"]},
    }
    sel, warnings = selections_for_appspec(spec)
    assert warnings == []
    assert {"id": "csv-export", "config": {"entity": "tasks"}} in [
        {"id": s["id"], "config": s["config"]} for s in sel]
    plain = dict(spec)
    plain["tagline"] = "Track tasks across the cosmos"
    plain["requirements"] = {"functional": ["As a user I want to browse tasks"]}
    sel2, _ = selections_for_appspec(plain)
    assert all(s["id"] != "csv-export" for s in sel2)


# ---------- file-upload component (stable) ----------

def _upload_prd(entity="tasks", bucket="docs"):
    return {
        "appName": "T", "appKind": "crud",
        "tables": [{"name": "tasks", "fields": [{"name": "title", "type": "text"}]}],
        "pages": [
            {"name": "Dashboard", "route": "/", "components": [], "table": "tasks"},
            {"name": "TaskDetail", "route": "/tasks/:id", "components": [], "table": "tasks"},
        ],
        "apis": [], "auth": False,
        "_components": {"order": ["crud-entity", "file-upload"],
                        "units": [{"component": "crud-entity", "config": {"table": "tasks"}},
                                  {"component": "file-upload",
                                   "config": {"entity": entity, "bucket": bucket}}]},
    }


def test_upload_template_emits_section_and_helper(monkeypatch):
    monkeypatch.setenv("INTARA_TEMPLATE_ONLY", "1")
    from services.generators.frontend_gen import generate_frontend
    files = {f["path"]: f["content"] for f in generate_frontend(_upload_prd())["files"]}
    assert "src/lib/upload.ts" in files
    assert "supabase_bucket_docs" not in files["src/lib/upload.ts"]
    assert '"docs"' in files["src/lib/upload.ts"]
    assert "__BUCKET__" not in files["src/lib/upload.ts"]
    d = files["src/pages/TaskDetail.tsx"]
    assert "Attachments" in d and "uploadAttachment(" in d
    assert "from '../lib/upload'" in d
    assert "uploadUrls" in d
    for tok in ("__UPLOAD_IMPORT__", "__UPLOAD_STATE__", "__UPLOAD_SECTION__", "__BUCKET__"):
        assert tok not in d
    # list pages untouched
    assert "Attachments" not in files["src/pages/Dashboard.tsx"]


def test_upload_template_entity_scoped_and_off(monkeypatch):
    monkeypatch.setenv("INTARA_TEMPLATE_ONLY", "1")
    from services.generators.frontend_gen import generate_frontend
    prd = _upload_prd(entity="nope")
    files = {f["path"]: f["content"] for f in generate_frontend(prd)["files"]}
    assert "uploadAttachment(" not in files["src/pages/TaskDetail.tsx"]
    assert "src/lib/upload.ts" in files  # helper guaranteed regardless
    prd2 = dict(_upload_prd())
    del prd2["_components"]
    files2 = {f["path"]: f["content"] for f in generate_frontend(prd2)["files"]}
    assert "src/lib/upload.ts" not in files2
    assert "uploadAttachment" not in files2["src/pages/TaskDetail.tsx"]
    assert "__UPLOAD" not in files2["src/pages/TaskDetail.tsx"]


def test_upload_template_passes_gates(monkeypatch):
    monkeypatch.setenv("INTARA_TEMPLATE_ONLY", "1")
    from services.generators.frontend_gen import generate_frontend
    from services.validator import validate_tsx
    from services.contract import check_placeholders, check_no_template_tokens
    files = generate_frontend(_upload_prd())["files"]
    for f in files:
        if f["path"].endswith((".tsx", ".ts")):
            assert validate_tsx(f["content"], f["path"]) == [], (f["path"], validate_tsx(f["content"], f["path"]))
    assert check_placeholders(files) == []
    assert check_no_template_tokens(files) == []


def test_check_file_upload_pass_and_fail():
    from services.contract import check_file_upload
    comps = [{"component": "file-upload", "config": {"entity": "tasks"}}]
    good = [{"path": "src/lib/upload.ts", "content": "export async function uploadAttachment() {}"},
            {"path": "src/pages/TaskDetail.tsx", "content": "uploadAttachment(f)"}]
    assert check_file_upload(good, comps) == []
    assert check_file_upload([], []) == []
    no_section = [{"path": "src/lib/upload.ts", "content": "x"},
                  {"path": "src/pages/TaskDetail.tsx", "content": "nothing here"}]
    errs = check_file_upload(no_section, comps)
    assert len(errs) == 1 and "src/pages/TaskDetail.tsx" in errs[0]
    no_helper = [{"path": "src/pages/TaskDetail.tsx", "content": "uploadAttachment(f)"}]
    assert any("src/lib/upload.ts" in e for e in check_file_upload(no_helper, comps))


def test_upload_check_runs_in_contract_battery(monkeypatch):
    monkeypatch.setenv("INTARA_TEMPLATE_ONLY", "1")
    from services.contract import build_contract
    from services.gates import run_contract_checks
    from services.generators.frontend_gen import generate_frontend
    from services.generators.backend_gen import generate_backend
    from services.generators.scaffold_gen import frontend_scaffold
    prd = _upload_prd()
    c = build_contract(prd)
    fe = generate_frontend(prd)["files"]
    be = generate_backend(prd)
    scaf = frontend_scaffold("T")
    errs = run_contract_checks(c, fe, be["files"], be["openapi"], scaf.get("package.json", ""), scaf.get("postcss.config.js"))
    assert not [e for e in errs if "upload" in e.lower() or "Attachments" in e], errs[:5]


def test_upload_catalog_stable_and_select_keywords():
    from components.registry import load_catalog
    e = load_catalog()["components"]["file-upload"]
    assert e["status"] == "stable"
    assert e["generator"]["module"] == "services.generators.frontend_gen"
    assert "check_file_upload" in e["gates"]
    assert e["params"]["entity"]["required"] is False
    from components.select import selections_for_appspec
    spec = {"appName": "PhotoVault", "appType": "catalog", "appKind": "crud",
            "tagline": "Upload and organize team photos",
            "tables": [{"name": "photos", "fields": [{"name": "title", "type": "text"}]}],
            "entities": [{"name": "photos", "fields": [], "relationships": []}],
            "pages": [{"name": "PhotoDetail", "route": "/photos/:id", "components": [], "table": "photos"}],
            "requirements": {"functional": []}}
    sel, warnings = selections_for_appspec(spec)
    assert warnings == []
    assert {"id": "file-upload", "config": {"entity": "photos"}} in [
        {"id": s["id"], "config": s["config"]} for s in sel]
    # 'profile' must NOT trigger on the 'file' substring
    plain = dict(spec)
    plain["tagline"] = "Browse user profiles"
    plain["appName"] = "TeamDir"
    sel2, _ = selections_for_appspec(plain)
    assert all(s["id"] != "file-upload" for s in sel2)


def test_upload_scaffold_storage_sql(monkeypatch):
    from services.generators.scaffold_gen import backend_scaffold
    from services.contract import check_placeholders, check_no_template_tokens
    files = backend_scaffold("T", [], "")
    assert "storage.sql" in files
    assert "storage.buckets" in files["storage.sql"]
    assert "uploads" in files["storage.sql"]
    assert "window.__INTARA_ENV__" in files["README_BACKEND.md"]
    flat = [{"path": p, "content": c} for p, c in files.items()]
    assert check_placeholders(flat) == []
    assert check_no_template_tokens(flat) == []
