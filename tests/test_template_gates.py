"""
Template + validator regression gates — $0, no network, no Supabase.
Covers the Sandpack `checked={{!!form.x}}` class of bug:
- templates must render single-brace JSX expressions,
- validate_tsx must flag double-wrapped attributes even without esbuild,
- generated backend must compile, contract checks must pass.
Run: pytest tests/test_template_gates.py -v
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)

os.environ["INTARA_TEMPLATE_ONLY"] = "1"

PRD = {
    "appName": "BugHunt",
    "tagline": "t",
    "tables": [
        {"name": "tasks", "fields": [
            {"name": "title", "type": "text"},
            {"name": "due_date", "type": "timestamp"},
            {"name": "completed", "type": "boolean"},
            {"name": "count", "type": "integer"},
        ]},
    ],
    "pages": [
        {"name": "Dashboard", "route": "/", "components": ["TaskList"]},
        {"name": "TaskDetail", "route": "/tasks/:id", "components": ["TaskForm"]},
    ],
    "apis": [
        {"method": "GET", "path": "/api/tasks", "desc": "list"},
        {"method": "POST", "path": "/api/tasks", "desc": "create"},
    ],
    "auth": True,
}


def test_boolean_input_renders_single_braces():
    from services.generators.frontend_gen import generate_frontend
    files = {f["path"]: f["content"] for f in generate_frontend(PRD)["files"]}
    dash = files["src/pages/Dashboard.tsx"]
    assert "checked={!!form.completed}" in dash
    assert "checked={{!!form.completed}}" not in dash


def test_no_double_wrapped_attributes_in_templates():
    import re
    from services.generators.frontend_gen import generate_frontend
    from services.generators.scaffold_gen import frontend_scaffold
    from services.preview.mock_gen import generate_mock
    contents = [f["content"] for f in generate_frontend(PRD)["files"]]
    contents += list(frontend_scaffold("BugHunt").values())
    contents += list(generate_mock(PRD).values())
    pat = re.compile(r"=\{\{(.*?)\}\}", re.S)
    for content in contents:
        for m in pat.finditer(content):
            inner = m.group(1).strip()
            assert not re.match(r"^[!]", inner), f"double-wrapped negation: {inner[:60]}"
            assert not re.match(r"^[\w\$][\w\$.]*$", inner), f"double-wrapped ident: {inner[:60]}"


def test_validate_tsx_flags_user_broken_snippet():
    from services.validator import validate_tsx
    bad = '<input type="checkbox" checked={{!!form.completed}} onChange={e=>setX(e)} />'
    assert any("double-brace" in e for e in validate_tsx(bad))


def test_validate_tsx_passes_valid_patterns():
    from services.validator import validate_tsx
    valid = [
        '<div style={{ display: "flex", gap: 6 }} />',
        '<input value={form.title} onChange={e=>setQ(e.target.value)} />',
        '<button onClick={()=>toggle(item.id)} style={{ padding: 1 }}>{saving ? "a" : "b"}</button>',
        '<div>{items.length}</div>',
    ]
    for snippet in valid:
        assert not [e for e in validate_tsx(snippet) if "double-brace" in e], snippet


def test_template_tsx_brace_clean():
    from services.validator import validate_tsx
    from services.generators.frontend_gen import generate_frontend
    for f in generate_frontend(PRD)["files"]:
        if f["path"].endswith(".tsx"):
            errs = [e for e in validate_tsx(f["content"]) if "double-brace" in e or "Unbalanced" in e]
            assert not errs, f"{f['path']}: {errs}"


def test_generated_backend_compiles():
    from services.generators.backend_gen import generate_backend
    for f in generate_backend(PRD)["files"]:
        if f["path"].endswith(".py"):
            compile(f["content"], f["path"], "exec")


def test_contract_checks_pass_on_templates():
    from services.generators.frontend_gen import generate_frontend
    from services.generators.backend_gen import generate_backend
    from services.generators.scaffold_gen import frontend_scaffold
    from services.preview.mock_gen import generate_mock
    from services.contract import build_contract
    from services.gates import run_contract_checks
    contract = build_contract(PRD, PRD["tables"])
    fe = [{"path": p, "content": c} for p, c in frontend_scaffold("BugHunt").items()]
    seen = {f["path"] for f in fe}
    for p, c in generate_mock(PRD).items():
        if p not in seen:
            fe.append({"path": p, "content": c})
    for f in generate_frontend(PRD)["files"]:
        if f["path"] not in {x["path"] for x in fe}:
            fe.append(f)
    be_out = generate_backend(PRD)
    be = be_out["files"]
    scaf = frontend_scaffold("BugHunt")
    errs = run_contract_checks(contract, fe, be, be_out.get("openapi", {}), scaf.get("package.json", ""), scaf.get("postcss.config.js"))
    assert not errs, errs[:5]


def test_validate_tsx_needs_no_node_modules():
    """Regression: bare react imports must NOT error (esbuild-bundle check removed)."""
    from services.validator import validate_tsx
    page = 'import React from "react"\nimport { Link } from "react-router-dom"\nexport default function Dashboard() { return <div className="glass"><Link to="/">x</Link></div> }'
    assert validate_tsx(page, "src/pages/Dashboard.tsx") == []
    comp = 'export function TaskCard({ item }: { item: any }) { return <div>{item.title}</div> }'
    assert validate_tsx(comp, "src/components/TaskCard.tsx") == []


# ---------- P1.3: fallback_reason metadata flow ----------

def test_schema_meta_template_and_llm_paths(monkeypatch):
    monkeypatch.setenv("INTARA_TEMPLATE_ONLY", "1")
    from services.generators.schema_gen import generate_schema
    out = generate_schema({"tables": [{"name": "tasks", "fields": [{"name": "title", "type": "text"}, {"name": "done", "type": "boolean"}]}]})
    assert out["_meta"]["source"] == "template"
    assert set(out) >= {"tables", "prisma", "sql", "_meta"}


def test_frontend_meta_collects_per_page_fallbacks(monkeypatch):
    monkeypatch.setenv("INTARA_TEMPLATE_ONLY", "1")
    from services.generators.frontend_gen import generate_frontend
    prd = {"appName": "T", "tables": [{"name": "tasks", "fields": [{"name": "title", "type": "text"}]}],
           "pages": [{"name": "Dashboard", "route": "/", "components": [], "table": "tasks"}],
           "apis": [], "auth": False}
    out = generate_frontend(prd)
    meta = out["_meta"]
    assert meta["source"] == "template"
    assert len(meta["fallbacks"]) == 1 and meta["fallbacks"][0]["page"] == "Dashboard"
    assert "Dashboard" in (meta["fallback_reason"] or "")


def test_backend_meta_collects_per_table_fallbacks(monkeypatch):
    monkeypatch.setenv("INTARA_TEMPLATE_ONLY", "1")
    from services.generators.backend_gen import generate_backend
    prd = {"appName": "T",
           "tables": [{"name": "tasks", "fields": [{"name": "title", "type": "text"}]}],
           "entities": [{"name": "tasks", "fields": [{"name": "title", "type": "text"}],
                         "relationships": [], "businessRules": []}],
           "apis": []}
    out = generate_backend(prd)
    assert out["_meta"]["source"] == "template"
    assert out["_meta"]["fallbacks"] == []  # template-only mode: no LLM attempted, nothing failed


def test_frag_fallback_helper():
    import sys
    sys.path.insert(0, "server")
    from services.orchestrator import _frag_fallback
    assert _frag_fallback({"_meta": {"fallback_reason": "boom"}}) == "boom"
    assert _frag_fallback({"_meta": {"source": "llm"}}) is None
    assert _frag_fallback({}) is None
    assert _frag_fallback(None) is None
    assert _frag_fallback("nope") is None


def test_page_ident_slugifies():
    import sys
    sys.path.insert(0, "server")
    from services.generators.frontend_gen import page_ident, normalize_frag
    assert page_ident("Daily Attendance") == "DailyAttendance"
    assert page_ident("leave_requests") == "LeaveRequests"
    assert page_ident("9 lives") == "Page9Lives"
    assert page_ident("") == "Page"
    assert page_ident("Settings") == "Settings"


def test_normalize_frag_fixes_spaced_llm_output():
    import sys
    sys.path.insert(0, "server")
    from services.generators.frontend_gen import normalize_frag
    frag = {"files": [{"path": "src/pages/Daily Attendance.tsx",
                       "content": "export default function Daily Attendance() { return 1 }"}]}
    out = normalize_frag(frag)
    assert out["files"][0]["path"] == "src/pages/DailyAttendance.tsx"
    assert "export default function DailyAttendance" in out["files"][0]["content"]
    # already-clean frags pass through untouched
    clean = {"files": [{"path": "src/pages/Home.tsx", "content": "export default function Home() { return 1 }"}]}
    assert normalize_frag(clean)["files"][0]["path"] == "src/pages/Home.tsx"


def test_template_tree_has_no_spaced_identifiers():
    import sys, re
    sys.path.insert(0, "server")
    from services.generators.frontend_gen import generate_frontend
    prd = {"appName": "T", "tables": [{"name": "t", "fields": [{"name": "n", "type": "text"}]}],
           "pages": [{"name": "Daily Attendance", "route": "/", "table": "t", "components": []},
                     {"name": "Leave Requests", "route": "/leaves", "table": "t", "components": []}],
           "apis": []}
    import os
    os.environ["INTARA_TEMPLATE_ONLY"] = "1"
    try:
        out = generate_frontend(prd)
    finally:
        os.environ.pop("INTARA_TEMPLATE_ONLY", None)
    paths = [f["path"] for f in out["files"]]
    assert "src/pages/DailyAttendance.tsx" in paths
    assert "src/pages/LeaveRequests.tsx" in paths
    assert not any(" " in p for p in paths if p.startswith("src/pages/")), paths
    by_path = {f["path"]: f["content"] for f in out["files"]}
    barrel = by_path.get("src/pages/index.ts", "")
    assert "DailyAttendance" in barrel and "Daily Attendance\"" not in barrel
    for path, content in by_path.items():
        if not path.endswith(".tsx"):
            continue
        for m in re.finditer(r"import\s*\{([^}]*)\}", content):
            for name in m.group(1).split(","):
                assert " " not in name.strip(), name
        for m in re.finditer(r"export\s+default\s+function\s+([A-Za-z][\w ]*)", content):
            assert " " not in m.group(1), m.group(1)


def test_seed_values_look_human():
    import sys
    sys.path.insert(0, "server")
    from services.preview.mock_gen import _seed_value as v, generate_mock
    # no Demo/Sample/val placeholders on known domains
    assert "Demo" not in v({"name": "name", "type": "text"}, 0, "employees")
    assert "@" in v({"name": "email", "type": "text"}, 1, "x")
    assert v({"name": "start", "type": "timestamp"}, 0, "x").startswith("2026-10-")
    # unknown tables keep the old generic fallback (documented floor)
    assert v({"name": "zzz", "type": "text"}, 0, "qqq") == "Sample 0"
    # end-to-end: generated seed has no placeholder text on known tables
    prd = {"appName": "T", "tables": [{"name": "employees", "fields": [
        {"name": "name", "type": "text"}, {"name": "email", "type": "text"}]}],
        "pages": [], "apis": []}
    files = generate_mock(prd)
    seed_ts = files["src/mock/seed.ts"]
    assert "Demo name" not in seed_ts and "demo1@" not in seed_ts
