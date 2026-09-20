"""
BackendGen — PRD -> {files, requirements, openapi}
FastAPI + Pydantic, deterministic.
"""
import json

def generate_backend(prd: dict):
    tables = prd.get("tables", [])
    apis = prd.get("apis", [])
    app_name = prd.get("appName", "IntaraApp")

    files = []
    # models.py
    models = ["from pydantic import BaseModel", "from typing import Optional", "from datetime import datetime", ""]
    for t in tables[:3]:
        cname = t["name"].capitalize().replace("_","")
        if cname.endswith("s"): cname = cname[:-1]
        models.append(f"class {cname}(BaseModel):")
        models.append(f"    id: Optional[str] = None")
        for f in t["fields"]:
            typ = {"text":"str", "integer":"int", "timestamp":"datetime", "boolean":"bool"}[f["type"]]
            if f["type"] in ("timestamp","integer") and "created" not in f["name"]:
                models.append(f"    {f['name']}: Optional[{typ}] = None")
            else:
                models.append(f"    {f['name']}: {typ}")
        models.append("")
    models.append(f"# App: {app_name}")
    files.append({"path": "server/models.py", "content": "\n".join(models)})

    # main.py — SQLite default, Supabase swap via db.py
    main = [f'""" {app_name} — FastAPI — Intara forged — SQLite default, Supabase swap """', "from fastapi import FastAPI, HTTPException", "from fastapi.middleware.cors import CORSMiddleware", "from pydantic import BaseModel", "import os", "from db import get_engine, init_db, supabase", "from sqlalchemy import text", ""]
    main.append('app = FastAPI(title="' + app_name + '")')
    main.append('app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])')
    main.append('init_db()  # ensure SQLite tables')
    for t in tables[:3]:
        main.append("")
        main.append(f'# {t["name"]} routes — Supabase when env set, else SQLite + in-memory fallback')
        main.append(f'@app.get("/api/{t["name"]}")')
        main.append(f'def list_{t["name"]}():')
        main.append(f'    if supabase:')
        main.append(f'        try: return supabase.table("{t["name"]}").select("*").execute().data or []')
        main.append(f'        except Exception as e: print(e)')
        main.append(f'    try:')
        main.append(f'        with get_engine().connect() as conn:')
        main.append(f'            rows = conn.execute(text("select * from {t["name"]}")).mappings().all()')
        main.append(f'            return [dict(r) for r in rows]')
        main.append(f'    except: return []')
        main.append(f'@app.post("/api/{t["name"]}")')
        main.append(f'def create_{t["name"]}(body: dict):')
        main.append(f'    if supabase:')
        main.append(f'        try: return supabase.table("{t["name"]}").insert(body).execute().data[0]')
        main.append(f'        except Exception as e: print(e)')
        main.append(f'    try:')
        main.append(f'        with get_engine().begin() as conn:')
        main.append(f'            cols = ", ".join(body.keys())')
        # inner f-string must be escaped — use plain string with single quotes
        main.append(f'            vals = ", ".join([f":{{k}}" for k in body.keys()])')
        main.append(f'            conn.execute(text(f"insert into {t["name"]} ({{cols}}) values ({{vals}})"), body)')
        main.append(f'        return {{"ok": True, **body}}')
        main.append(f'    except Exception as e: raise HTTPException(500, str(e))')
    main.append("")
    main.append('@app.get("/health")')
    main.append('def health(): return {"ok": True, "app": "' + app_name + '", "db": "supabase" if supabase else "sqlite"}')
    files.append({"path": "server/main.py", "content": "\n".join(main)})

    # routers per table
    for t in tables[:2]:
        cname = t["name"].capitalize().replace("_","")
        files.append({"path": f"server/routers/{t['name']}.py", "content": f'""" {cname} router """\nfrom fastapi import APIRouter\nrouter = APIRouter(prefix="/api/{t["name"]}")\n\n@router.get("/")\ndef list_{t["name"]}(): return []\n'})

    # requirements — include sqlalchemy for SQLite trial
    requirements = "fastapi==0.110.1\nuvicorn==0.29.0\npydantic>=2.9.0\nsupabase==2.31.0\npython-dotenv==1.0.1\nsqlalchemy==2.0.23\n"

    # openapi
    paths = {}
    for api in apis:
        path = api["path"]
        method = api["method"].lower()
        if path not in paths: paths[path] = {}
        paths[path][method] = {"summary": api.get("desc",""), "responses": {"200": {"description": "ok"}}}
    openapi = {"openapi": "3.0.0", "info": {"title": app_name, "version": "1.0.0"}, "paths": paths}

    return {"files": files, "requirements": requirements, "openapi": openapi}
