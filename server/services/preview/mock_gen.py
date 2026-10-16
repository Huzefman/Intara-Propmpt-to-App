"""
Preview mock — Dexie IndexedDB relational mock + seed + fetch interceptor
Generates src/mock/* for Sandpack trial (no server, no Supabase)
"""

def _field_to_dexie_type(ft):
    return {"text": "string", "integer": "number", "timestamp": "string", "boolean": "boolean"}.get(ft, "string")

def _seed_value(field, idx, table=""):
    name = field["name"]
    ft = field["type"]
    tnames = (table or "").lower()
    if ft == "text":
        if "email" in name:
            who = _pick_person(idx)
            return f"{who.lower().replace(' ', '.')}{idx}@intara.test"
        if "phone" in name:
            return f"+91 98250 1000{idx}"
        if any(k in name for k in ("title", "name", "subject")):
            titled = _pick_title(tnames, idx)
            if titled:
                return titled
            return f"Demo {name} {idx}"
        if "status" in name:
            return ["active", "pending", "done"][idx % 3]
        if "description" in name or "notes" in name or "reason" in name:
            return _pick_note(tnames, idx)
        if "address" in name or "city" in name:
            return ["Jaipur", "Pune", "Indore"][idx % 3]
        return f"Sample {idx}"
    if ft == "integer":
        if any(k in name for k in ("qty", "count", "stock", "hours", "days", "age")):
            return [3, 12, 7][idx % 3]
        if "price" in name or "cost" in name or "total" in name or "amount" in name:
            return [499, 1299, 2499][idx % 3]
        return idx * 10
    if ft == "boolean":
        return idx % 2 == 0
    if ft == "timestamp":
        # recent deterministic dates (mid-Oct 2026) so "today" views are non-empty
        return f"2026-10-{10 + (idx % 6):02d}T09:00:00.000Z"
    return f"val{idx}"


def _pick_person(idx):
    return ["Aarav Mehta", "Priya Nair", "Rohan Patel", "Anita Shah", "Imran Khan"][idx % 5]


def _pick_title(tnames, idx):
    pools = {
        "task": ["Prepare monthly report", "Fix login bug", "Review pull requests", "Plan sprint retro"],
        "project": ["Website revamp", "Mobile app", "API migration"],
        "product": ["Clay mug", "Dinner plate", "Serving bowl"],
        "employee": ["Aarav Mehta", "Priya Nair", "Rohan Patel"],
        "user": ["Aarav Mehta", "Priya Nair", "Rohan Patel"],
        "customer": ["Acme Traders", "Sharma General Store", "Novelty Corner"],
        "job": ["Screen replacement", "Battery service", "Full diagnostic"],
        "leave": ["Diwali break", "Family function", "Medical appointment"],
        "booking": ["Haircut", "Spa session", "Consultation"],
        "appointment": ["Haircut", "Spa session", "Consultation"],
        "order": ["Order #1042", "Order #1043", "Order #1044"],
        "invoice": ["INV-2026-101", "INV-2026-102", "INV-2026-103"],
        "event": ["Team offsite", "Product launch", "Training day"],
        "meeting": ["Sprint planning", "Design review", "Retro"],
    }
    for key, pool in pools.items():
        if key in tnames:
            return pool[idx % len(pool)]
    return ""


def _pick_note(tnames, idx):
    notes = {
        "leave": ["Family function at hometown", "Fever, resting at home", "Wedding in the family"],
        "task": ["Blocked on API keys", "Needs design review first", "Carried from last sprint"],
        "job": ["Cracked screen, needs parts", "Battery drains overnight", "Customer waiting on estimate"],
    }
    for key, pool in notes.items():
        if key in tnames:
            return pool[idx % len(pool)]
    return f"Note {idx}"

def generate_mock(prd: dict):
    # Canonical contract: string UUID ids everywhere (SQLite TEXT PK agrees).
    # Dexie stores use string `id` keys — no Number() casts anywhere.
    from services.contract import build_contract
    contract = build_contract(prd)
    tables = contract["tables"]
    if not tables:
        tables = [{"name": "items", "fields": [{"name": "title", "type": "text"}], "fks": []}]

    dexie_stores = {}
    for t in tables:
        fields = [f["name"] for f in t.get("fields", []) if f["name"] != "id"]
        dexie_stores[t["name"]] = "id," + ",".join(fields[:7])

    # db.ts
    stores_str = ",\n    ".join([f"'{k}': '{v}'" for k, v in dexie_stores.items()])
    table_props = "\n".join([f"  {t['name']}!: Dexie.Table<any, string>" for t in tables])

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

    # seed.ts — FK-aware, string ids ("<table>-1..3", FKs reference parent ids)
    seed_entries = []
    for t in tables:
        fks = t.get("fks", []) or []
        for i in range(1, 4):
            obj_fields = [f'"id": "{t["name"]}-{i}"']
            for f in t.get("fields", [])[:7]:
                if f["name"] == "id":
                    continue
                fk_target = next((fk["ref_table"] for fk in fks if fk["col"] == f["name"]), None)
                if fk_target:
                    obj_fields.append(f'"{f["name"]}": "{fk_target}-{(i % 3) + 1}"')
                else:
                    val = _seed_value(f, i, t["name"])
                    if isinstance(val, str):
                        obj_fields.append(f'"{f["name"]}": "{val}"')
                    elif isinstance(val, bool):
                        obj_fields.append(f'"{f["name"]}": {str(val).lower()}')
                    else:
                        obj_fields.append(f'"{f["name"]}": {val}')
            seed_entries.append(f"  await db.{t['name']}.put({{{', '.join(obj_fields)}}})")

    seed_ts = f'''import {{ db }} from './db'

export async function seedPreview() {{
  const counts = await Promise.all([{", ".join([f"db.{t['name']}.count()" for t in tables])}])
  if (counts.some((c: number) => c > 0)) return
{chr(10).join(seed_entries)}
  console.log('intara: seeded', counts)
}}
'''

    # server.ts — fetch interceptor serving the contract's declared routes (string ids).
    # Minimal game contracts only declare GET/POST, so only those are intercepted.
    route_cases = []
    for r in contract.get("routes", []):
        method = r.get("method", "")
        path = r.get("path", "")
        tbl = r.get("table", "")
        if not tbl or tbl not in dexie_stores:
            continue
        if method == "GET" and "{id}" not in path:
            route_cases.append(f'  if (pathname === "{path}" && method === "GET") {{ return Response.json(await db.{tbl}.toArray()) }}')
        elif method == "POST":
            route_cases.append(f'  if (pathname === "{path}" && method === "POST") {{ const b = await req.json().catch(()=>({{}})); if (!b.id) b.id = "{tbl}-" + Math.random().toString(36).slice(2, 10); await db.{tbl}.put(b); return Response.json(await db.{tbl}.get(b.id)) }}')
        elif method == "GET_ID":
            base = path.replace("/{id}", "")
            route_cases.append(f'  if (pathname.startsWith("{base}/") && method === "GET") {{ const id = String(pathname.split("/").pop()); const row = await db.{tbl}.get(id); return row ? Response.json(row) : Response.json({{error:"not found"}}, {{status:404}}) }}')
        elif method == "PUT":
            base = path.replace("/{id}", "")
            route_cases.append(f'  if (pathname.startsWith("{base}/") && method === "PUT") {{ const id = String(pathname.split("/").pop()); const b = await req.json().catch(()=>({{}})); b.id = id; await db.{tbl}.put(b); return Response.json(await db.{tbl}.get(id)) }}')
        elif method == "PATCH":
            base = path.replace("/{id}", "")
            route_cases.append(f'  if (pathname.startsWith("{base}/") && method === "PATCH") {{ const id = String(pathname.split("/").pop()); const b = await req.json().catch(()=>({{}})); await db.{tbl}.update(id, b); return Response.json(await db.{tbl}.get(id)) }}')
        elif method == "DELETE":
            base = path.replace("/{id}", "")
            route_cases.append(f'  if (pathname.startsWith("{base}/") && method === "DELETE") {{ const id = String(pathname.split("/").pop()); await db.{tbl}.delete(id); return Response.json({{ok:true}}) }}')

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
