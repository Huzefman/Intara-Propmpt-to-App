"""
Contract — single machine-readable source of truth for one app build.

Derived once from the schema step (tables + entities). Every downstream
generator (backend, frontend, mock, openapi, scaffold) and every gate
consumes this object, so the pieces cannot drift:
- routes: full CRUD matrix per table, {id} canonical (never :id)
- ids: string UUIDs everywhere (SQLite TEXT PK, Dexie string keys, FREE of Number() casts)
- layout: backend/ root, module server.main:app, cwd backend/
- deps: closed dependency sets per side (tailwind ⇒ pkg + postcss config)
"""
import re
import uuid

METHODS = ["GET", "POST", "GET_ID", "PUT", "PATCH", "DELETE"]

PY_TYPES = {"text": "str", "integer": "int", "timestamp": "datetime", "boolean": "bool", "uuid": "str"}
TS_TYPES = {"text": "string", "integer": "number", "timestamp": "string", "boolean": "boolean", "uuid": "string"}
SQL_TYPES = {"text": "TEXT", "integer": "INTEGER", "timestamp": "TEXT", "boolean": "INTEGER", "uuid": "TEXT"}

LAYOUT = {"be_dir": "backend", "be_module": "server.main:app", "be_cwd": "backend", "fe_dir": "frontend"}

FE_DEPS = ["react", "react-dom", "react-router-dom", "@supabase/supabase-js", "dexie"]
FE_TAILWIND_DEPS = ["tailwindcss", "postcss", "autoprefixer"]
BE_DEPS = ["fastapi", "uvicorn", "pydantic", "supabase", "python-dotenv", "sqlalchemy"]


def canon_path(path: str) -> str:
    """:id → {id} everywhere."""
    return re.sub(r":(\w+)", r"{\1}", path or "")


def base_name(table: str) -> str:
    t = (table or "items").strip() or "items"
    return t[0].upper() + t[1:]


def client_fns(table: str) -> dict:
    b = base_name(table)
    return {
        "list": f"list{b}", "create": f"create{b}",
        "get": f"get{b}ById", "put": f"put{b}ById",
        "patch": f"patch{b}ById", "delete": f"delete{b}ById",
    }


def table_routes(table: str) -> list[dict]:
    base = f"/api/{table}"
    item = f"/api/{table}/{{id}}"
    return [
        {"method": "GET", "path": base, "table": table},
        {"method": "POST", "path": base, "table": table},
        {"method": "GET", "path": item, "table": table},
        {"method": "PUT", "path": item, "table": table},
        {"method": "PATCH", "path": item, "table": table},
        {"method": "DELETE", "path": item, "table": table},
    ]


def table_fks(table: str, entities: list | None) -> list[dict]:
    """FK columns for a table from entities belongs_to (case-insensitive table match)."""
    out = []
    for ent in entities or []:
        if str(ent.get("name", "")).lower() != str(table).lower():
            continue
        for rel in ent.get("relationships", []) or []:
            if rel.get("type") == "belongs_to" and rel.get("target"):
                out.append({"col": rel.get("fk") or f"{rel['target']}_id",
                            "ref_table": rel["target"]})
    seen, uniq = set(), []
    for fk in out:
        if fk["col"] not in seen:
            seen.add(fk["col"])
            uniq.append(fk)
    return uniq


def build_contract(prd: dict, schema_tables: list | None = None) -> dict:
    tables_in = schema_tables if schema_tables is not None else (prd.get("tables") or [])
    entities = prd.get("entities") or []
    tables = []
    for t in tables_in[:5]:
        fields = [{**f} for f in (t.get("fields") or [])][:8]
        # FK columns are real columns (SQLite + Dexie + models all agree)
        existing = {f["name"] for f in fields}
        for fk in table_fks(t["name"], entities):
            if fk["col"] not in existing:
                fields.append({"name": fk["col"], "type": "uuid"})
                existing.add(fk["col"])
        tables.append({"name": t["name"], "fields": fields,
                       "fks": table_fks(t["name"], entities)})
    routes = []
    for t in tables:
        routes.extend(table_routes(t["name"]))
    return {"appName": prd.get("appName", "IntaraApp"),
            "tables": tables, "routes": routes, "layout": dict(LAYOUT)}


def ddl_for(contract: dict) -> str:
    """Real CREATE TABLE statements (init_db executes these — no SELECT 1 stubs)."""
    stmts = []
    for t in contract["tables"]:
        cols = ["id TEXT PRIMARY KEY"]
        for fk in t["fks"]:
            cols.append(f"{fk['col']} TEXT REFERENCES {fk['ref_table']}(id)")
        for f in t["fields"]:
            if f["name"] == "id" or any(f["name"] == fk["col"] for fk in t["fks"]):
                continue
            typ = SQL_TYPES.get(f["type"], "TEXT")
            default = ""
            if f["type"] == "boolean":
                default = " DEFAULT 0"
            elif f["type"] == "integer":
                default = " DEFAULT 0"
            cols.append(f"{f['name']} {typ}{default}")
        stmts.append(f"CREATE TABLE IF NOT EXISTS {t['name']} (\n  " + ",\n  ".join(cols) + "\n);")
    return "\n\n".join(stmts)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# --- conformance checks (gates + tests share these) ---

def check_placeholders(files: list[dict]) -> list[str]:
    """Forbid stub/placeholder emissions."""
    errs = []
    pats = [("SELECT 1", "stub query"), ("return []", "stub return"),
            ("TODO", "TODO left in output")]
    # {{ }} doubles are LEGIT JSX (style={{...}}), so leakage detection is precise:
    leak_res = [(r"\{\{!", "doubled braces before expression (wanted single {)"),
                (r"\['[a-z_]+'\]", "python-subscript leakage (wanted .attr or {item.x})")]
    for f in files:
        content = f.get("content", "")
        for pat, label in pats:
            if pat in content:
                errs.append(f"{f.get('path')}: {label} ({pat!r})")
                break
        if f.get("path", "").endswith((".tsx", ".ts")):
            for rx, label in leak_res:
                if re.search(rx, content):
                    errs.append(f"{f.get('path')}: {label}")
                    break
        # standalone `...` stub line (spread `{...s}` is legit — only bare lines count)
        if re.search(r"(?m)^\s*\.\.\.\s*$", content):
            errs.append(f"{f.get('path')}: ellipsis stub (bare `...` line)")
    return errs


def check_no_template_tokens(files: list[dict]) -> list[str]:
    toks = ["__NAME__", "__TABLE__", "__APP__", "__ROUTE__", "__COMPS__", "__INPUTS__",
            "{f['name']}", "{f["]
    errs = []
    for f in files:
        for tok in toks:
            if tok in f.get("content", ""):
                errs.append(f"{f.get('path')}: unrendered template token {tok!r}")
                break
    return errs


def check_backend_routes(files: list[dict], contract: dict) -> list[str]:
    """main.py must serve the full route matrix; routers/ must not exist."""
    errs = []
    paths = [f.get("path") for f in files]
    if any(p.startswith("server/routers/") for p in paths):
        errs.append("server/routers/ stubs present — all routes live in server/main.py")
    main = next((f.get("content", "") for f in files if f.get("path") == "server/main.py"), "")
    if not main:
        return errs + ["server/main.py missing"]
    for r in contract["routes"]:
        method = r["method"]
        # GET_ID shares the item path with distinct handler; check path presence per method family
        if method == "GET_ID":
            continue
        needle = f'@app.{method.lower()}("{r["path"]}")'
        if needle not in main:
            errs.append(f"server/main.py: missing route {method} {r['path']}")
    # item routes (GET/PUT/PATCH/DELETE on {id}) share one path shape — require each decorator
    item_paths = {r["path"] for r in contract["routes"] if "{id}" in r["path"]}
    for p in item_paths:
        for m in ("get", "put", "patch", "delete"):
            if f'@app.{m}("{p}")' not in main:
                errs.append(f"server/main.py: missing route {m.upper()} {p}")
    if "include_router" in main:
        errs.append("server/main.py: include_router present — routers deleted, keep routes inline")
    if "from db import" in main:
        errs.append("server/main.py: cwd-fragile 'from db import' — use 'from server.db import'")
    return errs


def check_frontend_client(files: list[dict], contract: dict) -> list[str]:
    errs = []
    by_path = {f.get("path"): f.get("content", "") for f in files}
    api = by_path.get("src/api.ts", "")
    if not api:
        return errs + ["src/api.ts missing"]
    if ":id" in api:
        errs.append("src/api.ts: Express-style :id — use ${id} interpolation")
    for t in contract["tables"]:
        for fname in client_fns(t["name"]).values():
            if fname not in api:
                errs.append(f"src/api.ts: missing client fn {fname} for table {t['name']}")
    # pages must use the client, not raw fetch to /api
    for path, content in by_path.items():
        if path.startswith("src/pages/") and "fetch('/api/" in content.replace('"', "'"):
            errs.append(f"{path}: raw fetch to /api — use the src/api.ts client")
    return errs


def check_openapi(openapi: dict, contract: dict) -> list[str]:
    errs = []
    paths = openapi.get("paths", {}) if isinstance(openapi, dict) else {}
    for r in contract["routes"]:
        key = "GET_ID" if r["method"] == "GET_ID" else r["method"]
        want = "get" if key == "GET_ID" else key.lower()
        if r["path"] not in paths or want not in paths[r["path"]]:
            errs.append(f"openapi: missing {want.upper()} {r['path']}")
    for p in paths:
        if ":id" in p:
            errs.append(f"openapi: Express-style path {p} — canonical is {{id}}")
    return errs


def check_deps(package_json: str, postcss_config: str | None) -> list[str]:
    # index.css always ships @tailwind directives → closure must exist
    errs = []
    for dep in FE_TAILWIND_DEPS:
        if dep not in package_json:
            errs.append(f"package.json: missing {dep} (index.css uses @tailwind)")
    if postcss_config is None:
        errs.append("postcss.config.js missing (index.css uses @tailwind)")
    return errs
