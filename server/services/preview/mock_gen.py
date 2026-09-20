"""
Preview mock — Dexie IndexedDB relational mock + seed + fetch interceptor
Generates src/mock/* for Sandpack trial (no server, no Supabase)
"""

def _field_to_dexie_type(ft):
    return {"text": "string", "integer": "number", "timestamp": "string", "boolean": "boolean"}.get(ft, "string")

def _seed_value(field, idx):
    name = field["name"]
    ft = field["type"]
    if ft == "text":
        if "email" in name: return f"demo{idx}@intara.test"
        if "title" in name or "name" in name: return f"Demo {name} {idx}"
        if "status" in name: return "active"
        return f"Sample {idx}"
    if ft == "integer":
        return idx * 10
    if ft == "boolean":
        return idx % 2 == 0
    if ft == "timestamp":
        return "2026-01-01T00:00:00.000Z"
    return f"val{idx}"

def generate_mock(prd: dict):
    tables = prd.get("tables", [])
    apis = prd.get("apis", [])
    if not tables:
        tables = [{"name": "items", "fields": [{"name": "title", "type": "text"}]}]

    # Build Dexie schema stores: include FKs from entities
    entities = prd.get("entities", [])
    fk_for_table = {}
    for ent in entities:
        for rel in ent.get("relationships", []):
            if rel.get("type") == "belongs_to":
                fk = rel.get("fk", f"{rel['target']}_id")
                fk_for_table.setdefault(ent["name"], []).append((fk, rel["target"]))
    dexie_stores = {}
    for t in tables:
        fields = [f["name"] for f in t.get("fields", [])]
        for fk, _ in fk_for_table.get(t["name"], []):
            if fk not in fields:
                fields.append(fk)
        dexie_stores[t["name"]] = "++id," + ",".join(fields[:6])

    # db.ts
    stores_str = ",\n    ".join([f"'{k}': '{v}'" for k, v in dexie_stores.items()])
    table_props = "\n".join([f"  {t['name']}: Dexie.Table<any, number>" for t in tables])

    db_ts = f'''import Dexie from 'dexie'

export class PreviewDB extends Dexie {{
{table_props}
  constructor() {{
    super('intara-preview')
    this.version(1).stores({{
    {stores_str}
    }})
  }}
}}

export const db = new PreviewDB()
'''

    # seed.ts — FK-aware
    seed_entries = []
    for t in tables:
        fks = fk_for_table.get(t["name"], [])
        for i in range(1, 4):
            obj_fields = []
            for f in t.get("fields", [])[:4]:
                # Check if this field is an FK
                is_fk = any(f["name"] == fk for fk, _ in fks)
                if is_fk:
                    # Reference seeded user IDs (1,2,3)
                    val = (i % 3) + 1
                    obj_fields.append(f'"{f["name"]}": {val}')
                else:
                    val = _seed_value(f, i)
                    if isinstance(val, str):
                        obj_fields.append(f'"{f["name"]}": "{val}"')
                    elif isinstance(val, bool):
                        obj_fields.append(f'"{f["name"]}": {str(val).lower()}')
                    else:
                        obj_fields.append(f'"{f["name"]}": {val}')
            # Also add FK fields that may not be in t["fields"] but in relationships (e.g. author_id not in fields but needed)
            for fk, target in fks:
                if not any(f["name"] == fk for f in t.get("fields", [])):
                    # FK not in fields list, add it
                    obj_fields.append(f'"{fk}": {(i % 3) + 1}')
            seed_entries.append(f"  await db.{t['name']}.put({{{', '.join(obj_fields)}}})")

    seed_ts = f'''import {{ db }} from './db'

export async function seedPreview() {{
  const counts = await Promise.all([{", ".join([f"db.{t['name']}.count()" for t in tables])}])
  if (counts.some((c: number) => c > 0)) return
{chr(10).join(seed_entries)}
  console.log('intara: seeded', counts)
}}
'''

    # server.ts — fetch interceptor that mimics OpenAPI
    # Build route handlers
    route_cases = []
    for api in apis[:6]:
        method = api["method"]
        path = api["path"]
        # infer table from path e.g. /api/tasks -> tasks
        tbl = path.replace("/api/", "").split("/")[0].replace(":id", "").strip() or (tables[0]["name"] if tables else "items")
        if method == "GET" and ":id" not in path:
            route_cases.append(f'  if (method === "GET" && pathname === "{path}") {{ const rows = await db.{tbl}.toArray(); return Response.json(rows) }}')
        elif method == "POST":
            route_cases.append(f'  if (method === "POST" && pathname === "{path}") {{ const body = await req.json().catch(()=>({{}})); const id = await db.{tbl}.put(body); const row = await db.{tbl}.get(id); return Response.json(row) }}')
        elif method == "PATCH" and ":id" in path:
            base = path.replace("/:id", "")
            route_cases.append(f'  if (method === "PATCH" && pathname.startsWith("{base}/")) {{ const id = Number(pathname.split("/").pop()); const body = await req.json().catch(()=>({{}})); await db.{tbl}.update(id, body); const row = await db.{tbl}.get(id); return Response.json(row) }}')
        elif method == "DELETE" and ":id" in path:
            base = path.replace("/:id", "")
            route_cases.append(f'  if (method === "DELETE" && pathname.startsWith("{base}/")) {{ const id = Number(pathname.split("/").pop()); await db.{tbl}.delete(id); return Response.json({{ ok: true }}) }}')

    # Generic CRUD for all tables (ensures detail/edit/delete work even if not in OpenAPI)
    for t in tables:
        tbl = t["name"]
        # Use unique markers to avoid duplicate check issues, always add full CRUD
        has_get = any(f'"/api/{tbl}"' in c and 'method === "GET"' in c for c in route_cases)
        has_post = any(f'"/api/{tbl}"' in c and 'POST' in c for c in route_cases)
        has_get_id = any(tbl in c and ':id' in c or f'"/api/{tbl}/"' in c for c in route_cases)
        if not has_get:
            route_cases.append(f'  if (pathname === "/api/{tbl}" && method === "GET") {{ return Response.json(await db.{tbl}.toArray()) }}')
        if not has_post:
            route_cases.append(f'  if (pathname === "/api/{tbl}" && method === "POST") {{ const b = await req.json().catch(()=>({{}})); const id = await db.{tbl}.put(b); return Response.json(await db.{tbl}.get(id)) }}')
        # Detail GET /:id, PATCH, DELETE for all tables
        route_cases.append(f'  if (pathname.startsWith("/api/{tbl}/") && method === "GET") {{ const id = Number(pathname.split("/").pop()); const row = await db.{tbl}.get(id); return row ? Response.json(row) : Response.json({{error:"not found"}}, {{status:404}}) }}')
        route_cases.append(f'  if (pathname.startsWith("/api/{tbl}/") && method === "PATCH") {{ const id = Number(pathname.split("/").pop()); const b = await req.json().catch(()=>({{}})); await db.{tbl}.update(id, b); return Response.json(await db.{tbl}.get(id)) }}')
        route_cases.append(f'  if (pathname.startsWith("/api/{tbl}/") && method === "DELETE") {{ const id = Number(pathname.split("/").pop()); await db.{tbl}.delete(id); return Response.json({{ok:true}}) }}')

    server_ts = f'''import {{ db }} from './db'

let patched = false

export function installMockServer() {{
  if (patched) return
  patched = true
  const origFetch = window.fetch.bind(window)
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {{
    const req = new Request(input, init)
    const url = new URL(req.url, window.location.origin)
    const pathname = url.pathname
    const method = req.method.toUpperCase()
    // only intercept /api/*
    if (!pathname.startsWith('/api/')) return origFetch(req)

    try {{
{chr(10).join(route_cases)}
    }} catch (e) {{
      console.error('mock server error', e)
      return Response.json({{ error: String(e) }}, {{ status: 500 }})
    }}
    // fallthrough to real fetch if no mock matched
    return origFetch(req)
  }}
  console.log('intara: mock server installed', {len(route_cases)} + ' routes')
}}
'''

    # preview helper re-export
    index_ts = '''export { db } from './db'
export { seedPreview } from './seed'
export { installMockServer } from './server'
'''

    return {
        "src/mock/db.ts": db_ts,
        "src/mock/seed.ts": seed_ts,
        "src/mock/server.ts": server_ts,
        "src/mock/index.ts": index_ts,
    }
