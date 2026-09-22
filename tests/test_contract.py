"""
Contract tests — deterministic, $0, no network, no Supabase.
Every generator's template output must satisfy the contract IR:
no stubs/placeholders/template leakage, full CRUD matrix, {id} canonical,
closed dep sets, real DDL. Run: pytest tests/test_contract.py
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "server"))

from services.contract import (  # noqa: E402
    build_contract, ddl_for, canon_path, check_placeholders,
    check_no_template_tokens, check_backend_routes, check_frontend_client,
    check_openapi, check_deps,
)
from services.generators.backend_gen import generate_backend  # noqa: E402
from services.generators.frontend_gen import generate_frontend  # noqa: E402
from services.generators.scaffold_gen import frontend_scaffold, backend_scaffold  # noqa: E402
from services.generators.schema_gen import generate_schema  # noqa: E402
from services.preview.mock_gen import generate_mock  # noqa: E402

PRD = {
    "appName": "TaskNest",
    "tagline": "tasks",
    "tables": [
        {"name": "users", "fields": [
            {"name": "email", "type": "text"},
            {"name": "name", "type": "text"},
            {"name": "created_at", "type": "timestamp"},
        ]},
        {"name": "tasks", "fields": [
            {"name": "title", "type": "text"},
            {"name": "completed", "type": "boolean"},
            {"name": "due", "type": "timestamp"},
            {"name": "priority", "type": "integer"},
        ]},
    ],
    "pages": [
        {"name": "Dashboard", "route": "/", "components": ["TaskList"], "table": "tasks"},
        {"name": "TaskDetail", "route": "/tasks/{id}", "components": ["TaskDetail"], "table": "tasks"},
        {"name": "Profile", "route": "/profile", "components": ["UserProfile"], "table": "users"},
    ],
    "apis": [],
    "entities": [
        {"name": "tasks", "relationships": [{"type": "belongs_to", "target": "users"}]},
    ],
}


def _contract():
    schema = generate_schema({"tables": PRD["tables"], "entities": PRD["entities"]})
    return build_contract(PRD, schema["tables"]), schema


def test_canon_path():
    assert canon_path("/api/tasks/:id") == "/api/tasks/{id}"
    assert canon_path("/api/tasks/{id}") == "/api/tasks/{id}"


def test_schema_carries_fks():
    _, schema = _contract()
    assert "users_id" in schema["sql"], "FK column missing from supabase.sql"
    assert "user" in schema["prisma"].lower()


def test_backend_template_conforms():
    be = generate_backend({**PRD, "entities": None})  # force template path
    files = be["files"]
    assert check_placeholders(files) == []
    assert check_no_template_tokens(files) == []
    assert check_backend_routes(files, build_contract(PRD)) == []
    assert check_openapi(be["openapi"], build_contract(PRD)) == []
    assert "server/routers/" not in " ".join(f["path"] for f in files)
    main = next(f["content"] for f in files if f["path"] == "server/main.py")
    assert "from server.db import" in main


def test_frontend_template_conforms():
    fe = generate_frontend(PRD)
    files = fe["files"]
    assert check_placeholders(files) == []
    assert check_no_template_tokens(files) == []
    assert check_frontend_client(files, build_contract(PRD)) == []
    api = next(f["content"] for f in files if f["path"] == "src/api.ts")
    assert ":id" not in api
    assert "getTasksById" in api and "patchTasksById" in api
    dash = next(f["content"] for f in files if f["path"] == "src/pages/Dashboard.tsx")
    assert "from '../api'" in dash and "fetch('/api/" not in dash.replace('"', "'")


def test_scaffold_closes_deps_and_layout():
    fe = frontend_scaffold("TaskNest")
    assert check_deps(fe["package.json"], fe.get("postcss.config.js")) == []
    be = backend_scaffold("TaskNest", PRD["tables"], ddl_for(build_contract(PRD)))
    assert "db.py" not in be, "root db.py duplicate must not exist"
    assert "SELECT 1" not in be["server/db.py"]
    assert "CREATE TABLE" in be["server/db.py"]
    assert "uvicorn server.main:app" in be["README_BACKEND.md"]


def test_mock_uses_string_ids():
    mock = generate_mock(PRD)
    server = mock["src/mock/server.ts"]
    assert "Number(" not in server, "numeric id casts break UUID parity"
    assert "PUT" in server
    db = mock["src/mock/db.ts"]
    assert "++id" not in db and "Table<any, string>" in db
    seed = mock["src/mock/seed.ts"]
    assert '"id": "tasks-1"' in seed
