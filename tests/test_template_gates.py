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
