"""
Rich per-page frontend prompt — includes design system, entity context, UI pattern
"""

def build_frontend_page_prompt(page: dict, app_spec: dict) -> str:
    """Builds the LLM prompt for one frontend page."""
    # Extract entity for this page
    table_name = page.get("table", "items")
    entity = next((e for e in app_spec.get("entities", []) if e["name"] == table_name), None)
    # Fallback to table
    if not entity:
        entity = next(({"name": t["name"], "fields": t["fields"], "relationships": [], "businessRules": []} for t in app_spec.get("tables", []) if t["name"] == table_name), {"name": table_name, "fields": [{"name": "title", "type": "text"}]})

    ui = app_spec.get("uiPatterns", {})
    layout = page.get("layout", ui.get("layout", "top-nav-grid"))
    list_style = ui.get("listStyle", "card-grid")

    # Design system reference
    design_ref = """
Design System (Intara — Dark Nebula Glass):
- Colors: bg #07070B, glass rgba(255,255,255,0.035) blur 24px, border rgba(255,255,255,0.06), nebula #8B5CF6, text #F8FAFC muted #CBD5E1
- Typography: Space Grotesk (headings), Inter (body), JetBrains Mono (code)
- Components: glass cards (border-radius 20px, backdrop-blur 24px), pill buttons, mono code blocks #08080C
- Layout: maxWidth 820, sticky nav with blur 16px
"""

    # Available imports
    imports_ref = """
Allowed imports: react, react-router-dom (BrowserRouter, Routes, Route, Link, useParams, useState, useEffect, useMemo).
No external UI libs. Use Tailwind classes via style prop or className="glass".
"""

    # API contract — canonical matrix from the shared contract (never :id, never stubs)
    try:
        from services.contract import table_routes, client_fns, canon_path
        matrix = table_routes(table_name)
        fns = client_fns(table_name)
        api_contract = "\n".join(
            f"{r['method']} {canon_path(r['path'])}  →  {fns['list'] if r['method']=='GET' and '{id}' not in r['path'] else fns['create'] if r['method']=='POST' else fns['get'] if r['method']=='GET_ID' else fns['put'] if r['method']=='PUT' else fns['patch'] if r['method']=='PATCH' else fns['delete']}()"
        )
        client_block = ("Import from '../api' and call ONLY these (never raw fetch('/api/...')): "
                        + ", ".join(f"{v}()" for v in fns.values()))
    except Exception:
        api_contract = (f"GET /api/{table_name} (list), POST /api/{table_name} (create), "
                        f"GET /api/{table_name}/{{id}}, PUT/PATCH/DELETE /api/{table_name}/{{id}}")
        client_block = "Use the src/api.ts client; never raw-fetch /api paths."

    # Business rules
    rules = entity.get("businessRules", [])
    rules_str = "; ".join(rules) if rules else "No special rules"

    # Few-shot example (compact) — uses the canonical client, typed callbacks
    example = """
Example (Task Dashboard — card-grid):
import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { listTasks, createTasks, patchTasksById } from '../api'
export default function Dashboard() {
  const [items, setItems] = useState<any[]>([])
  useEffect(()=>{listTasks().then((d:any)=>setItems(Array.isArray(d)?d:[]))},[])
  return <div><h2>Dashboard — TaskOrb</h2><div className="glass">{items.map((x:any)=> <div key={x.id}>{x.title}</div>)}</div></div>
}
"""

    prompt = """You are Intara frontend weaver — build ONE page for Vite React 18 + TS + Tailwind, Sandpack safe (no import.meta).

__DESIGN_REF__

App: __APP_NAME__ — __TAGLINE__
Entity for this page: __ENTITY__ fields: __FIELDS__ relationships: __RELS__ businessRules: __RULES__
Page: __PAGE_NAME__ route: __ROUTE__ table: __TABLE__ layout: __LAYOUT__ listStyle: __LIST_STYLE__
UI Patterns for this page: layout=__LAYOUT__, listStyle=__LIST_STYLE__, features=__FEATURES__
__IMPORTS_REF__
API contract for this table: __API_CONTRACT__
Available entity context: __ENTITIES__
All pages in app: __ALL_PAGES__

__EXAMPLE__

Return ONLY JSON with path and content for src/pages/__PAGE_NAME__.tsx
__CLIENT_BLOCK__
Rules:
- Use React hooks; data ONLY via the imported client fns (list/create/get/put/patch/delete)
- Strict TS: annotate every callback param (e.g. (x:any), (s:any), (e:any)); Dexie-free page code
- Single braces in JSX (style={{...}} is an object; never {{! or {{f[); no __TOKENS__ leftovers
- Tailwind glass, Space Grotesk headings, Inter body, no import.meta
- Include search, filter, and proper empty states
- No stubs: no `return []` placeholders, no TODO, no bare `...` lines
- No markdown, JSON only
"""
    prompt = prompt.replace("__DESIGN_REF__", design_ref).replace("__APP_NAME__", str(app_spec.get('appName'))).replace("__TAGLINE__", str(app_spec.get('tagline')))
    prompt = prompt.replace("__ENTITY__", str(entity['name'])).replace("__FIELDS__", str(entity.get('fields'))).replace("__RELS__", str(entity.get('relationships'))).replace("__RULES__", rules_str)
    prompt = prompt.replace("__PAGE_NAME__", page['name']).replace("__ROUTE__", page['route']).replace("__TABLE__", table_name).replace("__LAYOUT__", layout).replace("__LIST_STYLE__", list_style)
    prompt = prompt.replace("__FEATURES__", str(ui.get('features', []))).replace("__IMPORTS_REF__", imports_ref).replace("__API_CONTRACT__", api_contract).replace("__ENTITIES__", str(app_spec.get('entities'))).replace("__ALL_PAGES__", str(app_spec.get('pages'))).replace("__EXAMPLE__", example).replace("__CLIENT_BLOCK__", client_block)
    return prompt
