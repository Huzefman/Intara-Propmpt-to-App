"""
BackendGen — PRD -> {files, requirements, openapi} with LLM-first + template fallback.

Canonical layout (see services/contract.py — single source of truth):
- ALL routes live inline in server/main.py (no server/routers/ stubs)
- Full CRUD per table: GET list, GET {id}, POST, PUT, PATCH, DELETE
- {id} path params (never :id), string UUID ids, real CREATE TABLE in init_db
- Run from backend/ as: uvicorn server.main:app
"""
from utils.json_parse import parse_json as _parse_json, is_quota_error


def generate_backend_table_llm(table: dict, app_spec: dict, notes: list | None = None) -> dict | None:
    def _note(msg: str):
        try:
            if notes is not None:
                notes.append(msg[:200])
        except Exception:
            pass

    try:
        from services.llm import call_llm
        from services.validator import validate_python

        if str(app_spec.get("appKind") or "").lower() in ("interactive", "game"):
            from prompts.backend_table_v2 import build_backend_scores_prompt
            prompt = build_backend_scores_prompt(table, app_spec)
        else:
            from prompts.backend_table_v2 import build_backend_table_prompt
            prompt = build_backend_table_prompt(table, app_spec)
        raw = call_llm(prompt, temperature=0.3, json_mode=True)
        data = _parse_json(raw)
        files = data.get("files", [])
        if not files:
            _note("empty files in LLM response")
            return None
        # Validate each file
        for f in files:
            if f["path"].endswith(".py"):
                errs = validate_python(f["content"])
                if errs:
                    # repair
                    repair = f"Fix these Python errors:\n{errs}\n\nCode:\n{f['content']}"
                    try:
                        raw2 = call_llm(repair, temperature=0.1, json_mode=True)
                        data2 = _parse_json(raw2)
                        for ff in data2.get("files", []):
                            if ff["path"] == f["path"]:
                                if not validate_python(ff["content"]):
                                    f["content"] = ff["content"]
                    except Exception as e:
                        _note(f"repair failed: {e}"[:200])
                        return None
        return data
    except Exception as e:
        print(f"LLM backend table {table.get('name')} failed: {e}")
        _note(str(e))
        return None


def _template_backend(contract: dict) -> dict:
    from services.contract import PY_TYPES, ddl_for  # noqa (contract is source of truth)
    app_name = contract["appName"]
    tables = contract["tables"]

    # models.py — includes FK columns so SQLite/Dexie/PRD agree
    models = ["from pydantic import BaseModel", "from typing import Optional", "from datetime import datetime", ""]
    for t in tables:
        cname = t["name"].capitalize().replace("_", "")
        if cname.endswith("s"):
            cname = cname[:-1]
        models.append(f"class {cname}(BaseModel):")
        models.append("    id: Optional[str] = None")
        for fk in t.get("fks", []):
            models.append(f"    {fk['col']}: Optional[str] = None")
        for f in t["fields"]:
            if f["name"] == "id" or any(f["name"] == fk["col"] for fk in t.get("fks", [])):
                continue
            typ = PY_TYPES.get(f["type"], "str")
            if f["type"] in ("timestamp", "integer") and "created" not in f["name"]:
                models.append(f"    {f['name']}: Optional[{typ}] = None")
            else:
                models.append(f"    {f['name']}: {typ}")
        models.append("")
    models.append(f"# App: {app_name}")

    # main.py — full CRUD per table, Supabase-first with SQLite fallthrough
    main = [
        f'""" {app_name} — FastAPI — Intara forged """',
        "import uuid",
        "from fastapi import FastAPI, HTTPException",
        "from fastapi.middleware.cors import CORSMiddleware",
        "from server.db import get_engine, init_db, supabase",
        "from sqlalchemy import text",
        "",
        f'app = FastAPI(title="{app_name}")',
        'app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])',
        "init_db()  # ensure SQLite tables exist",
        "",
        "def _new_id() -> str:",
        "    return uuid.uuid4().hex[:12]",
        "",
        "def _row_or_404(table: str, rid: str) -> dict:",
        "    if supabase:",
        "        try:",
        '            r = supabase.table(table).select(\"*\").eq(\"id\", rid).single().execute()',
        "            if r.data: return r.data",
        "        except Exception: pass",
        "    try:",
        "        with get_engine().connect() as conn:",
        '            r = conn.execute(text(\"select * from \" + table + \" where id = :id\"), {\"id\": rid}).mappings().first()',
        "            if r: return dict(r)",
        "    except Exception: pass",
        '    raise HTTPException(404, f\"{table} {rid} not found\")',
        "",
    ]
    for t in tables:
        name = t["name"]
        if contract.get("appKind") in ("interactive", "game"):
            # Minimal mode: emit ONLY declared contract routes (e.g. scores GET+POST).
            declared = {(r.get("table"), r.get("method")) for r in contract.get("routes", [])}
            main.append("")
            main.append(f"# {name} — minimal routes (Supabase when env set, else SQLite)")
            if (name, "GET") in declared:
                main.append(f'@app.get("/api/{name}")')
                main.append(f"def list_{name}():")
                main.append("    if supabase:")
                main.append("        try:")
                main.append(f'            return supabase.table("{name}").select("*").execute().data or []')
                main.append("        except Exception as e: print(e)")
                main.append("    try:")
                main.append("        with get_engine().connect() as conn:")
                main.append(f'            rows = conn.execute(text("select * from {name}")).mappings().all()')
                main.append("            return [dict(r) for r in rows]")
                main.append("    except Exception as e: raise HTTPException(500, str(e))")
            if (name, "POST") in declared:
                main.append(f'@app.post("/api/{name}")')
                main.append(f"def create_{name}(body: dict):")
                main.append('    body = dict(body or {})')
                main.append('    body.setdefault("id", _new_id())')
                main.append("    if supabase:")
                main.append("        try:")
                main.append(f'            return supabase.table("{name}").insert(body).execute().data[0]')
                main.append("        except Exception as e: print(e)")
                main.append("    try:")
                main.append("        with get_engine().begin() as conn:")
                main.append('            cols = ", ".join(body.keys())')
                main.append('            vals = ", ".join([f":{k}" for k in body.keys()])')
                main.append(f'            conn.execute(text(f"insert into {name} ({{cols}}) values ({{vals}})"), body)')
                main.append("    except HTTPException: raise")
                main.append("    except Exception as e: raise HTTPException(500, str(e))")
                main.append(f'    return _row_or_404("{name}", body["id"])')
            for method, fname in (("get", f"get_{name}_by_id"), ("put", f"put_{name}"),
                                  ("patch", f"patch_{name}"), ("delete", f"delete_{name}")):
                want = "GET_ID" if method == "get" else method.upper()
                if (name, want) not in declared:
                    continue
                main.append(f'@app.{method}("/api/{name}/{{id}}")')
                if method == "get":
                    main.append(f"def {fname}(id: str):")
                    main.append(f'    return _row_or_404("{name}", id)')
                elif method == "delete":
                    main.append(f"def {fname}(id: str):")
                    main.append(f'    _row_or_404("{name}", id)')
                    main.append("    if supabase:")
                    main.append("        try:")
                    main.append(f'            supabase.table("{name}").delete().eq("id", id).execute()')
                    main.append(f'            return {{"ok": True}}')
                    main.append("        except Exception as e: print(e)")
                    main.append("    try:")
                    main.append("        with get_engine().begin() as conn:")
                    main.append(f'            conn.execute(text("delete from {name} where id = :id"), {{"id": id}})')
                    main.append('        return {"ok": True}')
                    main.append("    except HTTPException: raise")
                    main.append("    except Exception as e: raise HTTPException(500, str(e))")
                else:
                    main.append(f"def {fname}(id: str, body: dict):")
                    main.append(f'    _row_or_404("{name}", id)')
                    main.append('    body = {k: v for k, v in dict(body or {}).items() if k != "id"}')
                    main.append('    if not body: raise HTTPException(400, "empty update")')
                    main.append("    if supabase:")
                    main.append("        try:")
                    main.append(f'            return supabase.table("{name}").update(body).eq("id", id).execute().data[0]')
                    main.append("        except Exception as e: print(e)")
                    main.append("    try:")
                    main.append("        with get_engine().begin() as conn:")
                    main.append('            sets = ", ".join([f"{k} = :{k}" for k in body.keys()])')
                    main.append(f'            conn.execute(text(f"update {name} set {{sets}} where id = :id"), {{**body, "id": id}})')
                    main.append("    except HTTPException: raise")
                    main.append("    except Exception as e: raise HTTPException(500, str(e))")
                    main.append(f'    return _row_or_404("{name}", id)')
            continue
        main.append("")
        main.append(f"# {name} — full CRUD (Supabase when env set, else SQLite)")
        main.append(f'@app.get("/api/{name}")')
        main.append(f"def list_{name}():")
        main.append("    if supabase:")
        main.append("        try:")
        main.append(f'            return supabase.table("{name}").select("*").execute().data or []')
        main.append("        except Exception as e: print(e)")
        main.append("    try:")
        main.append("        with get_engine().connect() as conn:")
        main.append(f'            rows = conn.execute(text("select * from {name}")).mappings().all()')
        main.append("            return [dict(r) for r in rows]")
        main.append("    except Exception as e: raise HTTPException(500, str(e))")
        main.append(f'@app.post("/api/{name}")')
        main.append(f"def create_{name}(body: dict):")
        main.append('    body = dict(body or {})')
        main.append('    body.setdefault("id", _new_id())')
        main.append("    if supabase:")
        main.append("        try:")
        main.append(f'            return supabase.table("{name}").insert(body).execute().data[0]')
        main.append("        except Exception as e: print(e)")
        main.append("    try:")
        main.append("        with get_engine().begin() as conn:")
        main.append('            cols = ", ".join(body.keys())')
        main.append('            vals = ", ".join([f":{k}" for k in body.keys()])')
        main.append(f'            conn.execute(text(f"insert into {name} ({{cols}}) values ({{vals}})"), body)')
        main.append("    except HTTPException: raise")
        main.append("    except Exception as e: raise HTTPException(500, str(e))")
        # read AFTER commit (SQLite has no dirty reads across connections)
        main.append(f'    return _row_or_404("{name}", body["id"])')
        for method, fname in (("get", f"get_{name}_by_id"), ("put", f"put_{name}"),
                              ("patch", f"patch_{name}"), ("delete", f"delete_{name}")):
            main.append(f'@app.{method}("/api/{name}/{{id}}")')
            if method == "get":
                main.append(f"def {fname}(id: str):")
                main.append(f'    return _row_or_404("{name}", id)')
            elif method == "delete":
                main.append(f"def {fname}(id: str):")
                main.append(f'    _row_or_404("{name}", id)')
                main.append("    if supabase:")
                main.append("        try:")
                main.append(f'            supabase.table("{name}").delete().eq("id", id).execute()')
                main.append(f'            return {{"ok": True}}')
                main.append("        except Exception as e: print(e)")
                main.append("    try:")
                main.append("        with get_engine().begin() as conn:")
                main.append(f'            conn.execute(text("delete from {name} where id = :id"), {{"id": id}})')
                main.append('        return {"ok": True}')
                main.append("    except HTTPException: raise")
                main.append("    except Exception as e: raise HTTPException(500, str(e))")
            else:
                main.append(f"def {fname}(id: str, body: dict):")
                main.append(f'    _row_or_404("{name}", id)')
                main.append('    body = {k: v for k, v in dict(body or {}).items() if k != "id"}')
                main.append('    if not body: raise HTTPException(400, "empty update")')
                main.append("    if supabase:")
                main.append("        try:")
                main.append(f'            return supabase.table("{name}").update(body).eq("id", id).execute().data[0]')
                main.append("        except Exception as e: print(e)")
                main.append("    try:")
                main.append("        with get_engine().begin() as conn:")
                main.append('            sets = ", ".join([f"{k} = :{k}" for k in body.keys()])')
                main.append(f'            conn.execute(text(f"update {name} set {{sets}} where id = :id"), {{**body, "id": id}})')
                main.append("    except HTTPException: raise")
                main.append("    except Exception as e: raise HTTPException(500, str(e))")
                # read AFTER commit (SQLite has no dirty reads across connections)
                main.append(f'    return _row_or_404("{name}", id)')
    main.append("")
    main.append('@app.get("/health")')
    main.append(f'def health(): return {{"ok": True, "app": "{app_name}", "db": "supabase" if supabase else "sqlite"}}')

    files = [
        {"path": "server/__init__.py", "content": ""},
        {"path": "server/models.py", "content": "\n".join(models)},
        {"path": "server/main.py", "content": "\n".join(main)},
    ]

    requirements = "fastapi==0.110.1\nuvicorn==0.29.0\npydantic>=2.9.0\nsupabase==2.31.0\npython-dotenv==1.0.1\nsqlalchemy==2.0.23\nhttpx>=0.27.0\n"

    paths = {}
    for r in contract["routes"]:
        method = r["method"]
        want = "get" if method == "GET_ID" else method.lower()
        paths.setdefault(r["path"], {})[want] = {"responses": {"200": {"description": "ok"}}}
    openapi = {"openapi": "3.0.0", "info": {"title": app_name, "version": "1.0.0"}, "paths": paths}

    return {"files": files, "requirements": requirements, "openapi": openapi,
            "ddl": ddl_for(contract)}


def generate_backend(prd: dict):
    from services.contract import build_contract, check_backend_routes, check_placeholders
    tables = prd.get("tables", [])
    apis = prd.get("apis", [])
    app_name = prd.get("appName", "IntaraApp")
    contract = build_contract(prd)

    # Try LLM per table if app_spec has entities (skipped under INTARA_TEMPLATE_ONLY)
    import os as _os
    _be_fallbacks: list = []
    if prd.get("entities") and not _os.getenv("INTARA_TEMPLATE_ONLY"):
        llm_files = []
        llm_openapi = {"openapi": "3.0.0", "info": {"title": app_name, "version": "1.0.0"}, "paths": {}}
        success = True
        for table in tables[:5]:
            _notes: list = []
            data = generate_backend_table_llm(table, prd, _notes)
            if data and data.get("files"):
                llm_files.extend(data["files"])
                for path, methods in data.get("openapi", {}).get("paths", {}).items():
                    llm_openapi["paths"][path] = methods
            else:
                if _notes:
                    _be_fallbacks.append({"table": table.get("name"), "reason": _notes[-1]})
                else:
                    _be_fallbacks.append({"table": table.get("name"), "reason": "llm_failed"})
                success = False
                break
        if success and llm_files:
            # Contract-conformance filter: LLM output must serve the route matrix
            # with no stubs/placeholders, else fall through to the template.
            probe = [{"path": f.get("path", ""), "content": f.get("content", "")} for f in llm_files]
            problems = check_backend_routes(probe, contract) + check_placeholders(probe)
            if not problems:
                from services.generators.scaffold_gen import backend_scaffold
                from services.contract import ddl_for
                scaffold = backend_scaffold(app_name, tables, ddl_for(contract))
                for path, content in scaffold.items():
                    if not any(f["path"] == path for f in llm_files):
                        llm_files.append({"path": path, "content": content})
                requirements = "fastapi==0.110.1\nuvicorn==0.29.0\npydantic>=2.9.0\nsupabase==2.31.0\npython-dotenv==1.0.1\nsqlalchemy==2.0.23\nhttpx>=0.27.0\n"
                # openapi follows the contract matrix ({id} canonical), not raw PRD paths
                from services.contract import canon_path as _canon
                for r in contract["routes"]:
                    want = "get" if r["method"] == "GET_ID" else r["method"].lower()
                    llm_openapi["paths"].setdefault(r["path"], {}).setdefault(
                        want, {"responses": {"200": {"description": "ok"}}})
                for api in apis:
                    path = _canon(api["path"])
                    method = api["method"].lower()
                    llm_openapi["paths"].setdefault(path, {}).setdefault(
                        method, {"summary": api.get("desc", ""), "responses": {"200": {"description": "ok"}}})
                return {"files": llm_files, "requirements": requirements, "openapi": llm_openapi,
                        "_meta": {"source": "llm", "fallback_reason": None, "fallbacks": []}}
            print(f"LLM backend failed contract conformance, template fallback: {problems[:4]}")
            _be_fallbacks.append({"table": "contract", "reason": f"conformance: {problems[0][:150]}" if problems else "conformance"})

    result = _template_backend(contract)
    if _be_fallbacks:
        result["_meta"] = {"source": "template",
                           "fallback_reason": "; ".join(f"{f['table']}: {f['reason']}" for f in _be_fallbacks)[:500],
                           "fallbacks": _be_fallbacks}
    else:
        result["_meta"] = {"source": "template", "fallback_reason": "template_only_mode" if _os.getenv("INTARA_TEMPLATE_ONLY") else None, "fallbacks": []}
    return result
