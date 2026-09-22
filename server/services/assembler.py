"""
Assembler — PRD -> full artifacts {schema, frontend, backend, spec}
Orchestrates deterministic generators + optional RAG cites
"""
import os
from services.generators.schema_gen import generate_schema
from services.generators.frontend_gen import generate_frontend
from services.generators.backend_gen import generate_backend
from services.generators.scaffold_gen import frontend_scaffold, backend_scaffold
from services.preview.mock_gen import generate_mock

def assemble(prd: dict, prompt: str = ""):
    schema = generate_schema(prd)
    frontend = generate_frontend(prd)
    backend = generate_backend(prd)
    # scaffolds make zip runnable
    app_name = prd.get("appName", "IntaraApp")
    fe_scaffold = frontend_scaffold(app_name)
    from services.contract import build_contract, ddl_for
    be_scaffold = backend_scaffold(app_name, schema["tables"],
                                   ddl_for(build_contract(prd, schema["tables"])))
    # preview mock (IndexedDB)
    preview = generate_mock(prd)

    # README — now split runnable
    app_name = prd.get("appName", "IntaraApp")
    tagline = prd.get("tagline", "")
    readme = f"""# {app_name} — Intara Wish

> {tagline}
> Wish: "{prompt}"
> Forged by Intara — Planet of Wishes — {app_name}

## Stack
- Frontend: Vite + React 18 + TypeScript + Tailwind
- Backend: FastAPI + Pydantic + Supabase
- Schema: Prisma + Supabase SQL

## Run Frontend
```bash
cd frontend
npm install
npm run dev
```

## Run Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Tables
{chr(10).join(f"- **{t['name']}**: " + ", ".join(f"{f['name']}:{f['type']}" for f in t['fields']) for t in schema['tables'])}

## Pages
{chr(10).join(f"- {p['name']} → {p['route']} ({', '.join(p.get('components',[]))})" for p in prd.get('pages',[]))}

## APIs
{chr(10).join(f"- {a['method']} {a['path']} — {a['desc']}" for a in prd.get('apis',[]))}

## Artifacts
- `schema.json` + `schema.prisma` + `supabase.sql`
- `frontend/src/pages/*`, `src/components/*`
- `backend/server/*` + `requirements.txt`
- `openapi.json`

Intara weaves stardust into code. Make another wish at intara.planet.wish
"""

    # cites — try RAG, fallback mock (handle dim mismatch)
    cites = []
    try:
        gemini_key = os.getenv("GEMINI_API_KEY","")
        supa_url = os.getenv("SUPABASE_URL","")
        if gemini_key and supa_url:
            try:
                from rag import answer
                rag_res = answer(f"What stack for {app_name}? {prompt[:100]}")
                cites = rag_res.get("cites", [])[:3]
            except Exception as e:
                print(f"assembler rag failed, fallback cites: {e}")
                cites = []
    except Exception as e:
        print(f"assembler cites outer failed: {e}")
    if not cites:
        cites = [
            f"DhiWise builds Rocket.new — prompt to app with DB/auth/API and deployment. Intara mirrors this for {app_name}.",
            f"Supabase pgvector enables vector search via match_docs RPC with cosine similarity for {app_name}.",
            f"Intara forged {app_name}: {tagline[:80]}"
        ]

    openapi = backend.get("openapi", {})

    # merge scaffold + mock into frontend/backed artifacts for runnable zip + trial
    fe_files = frontend["files"]
    for path, content in fe_scaffold.items():
        fe_files.append({"path": path, "content": content})
    for path, content in preview.items():
        fe_files.append({"path": path, "content": content})
    # backend files include scaffold
    be_files = backend["files"]
    for path, content in be_scaffold.items():
        be_files.append({"path": path, "content": content})

    # Deduplicate by path (last wins)
    seen = {}
    for f in fe_files:
        seen[f["path"]] = f
    fe_files = list(seen.values())
    seen = {}
    for f in be_files:
        seen[f["path"]] = f
    be_files = list(seen.values())

    artifacts = {
        "schema": schema,
        "frontend": {"files": fe_files},
        "backend": {"files": be_files, "requirements": backend["requirements"], "openapi": openapi},
        "preview": preview,
        "spec": {
            "readme": readme,
            "openapi": openapi,
            "cites": cites,
            "prd": prd
        }
    }
    return artifacts
