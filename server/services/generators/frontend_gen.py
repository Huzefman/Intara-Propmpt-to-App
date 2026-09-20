"""
FrontendGen — PRD -> {files: [{path, content}]}
Vite React + TS + Tailwind, deterministic templates, LLM-optional.
"""

def _component_for(table, field_names):
    return f"""export function {table.capitalize()}Card({{ item }}: {{ item: any }}) {{
  return (
    <div className="glass" style={{{{ padding: 12 }}}}>
      <div style={{{{ fontWeight: 600 }}}}>{{item.title || item.name || item.email || 'Item'}}</div>
      <div style={{{{ color: 'var(--intara-muted)', fontSize: 12, marginTop: 4 }}}}>{{{field_names}}}</div>
    </div>
  )
}}
"""

def generate_frontend(prd: dict):
    tables = prd.get("tables", [])
    pages = prd.get("pages", [])
    app_name = prd.get("appName", "IntaraApp")
    files = []

    # api.ts — Sandpack-safe: no import.meta at parse time
    # Preview defaults to mock (IndexedDB). To connect real backend, set MODE='supabase' and API_URL.
    api_lines = [
        "// Intara Frontend — API client (mock vs real) — Sandpack safe",
        "const MODE = 'mock'",
        "const API_URL = ''",
        "// To use real backend, change to: const MODE = 'supabase'; const API_URL = 'http://localhost:8000';",
        "function baseFetch(path: string, init?: RequestInit) {",
        "  const url = MODE === 'mock' ? path : `${API_URL}${path}`",
        "  return fetch(url, init)",
        "}",
    ]
    for api in prd.get("apis", []):
        path = api["path"]
        method = api["method"]
        fn = path.replace("/api/","").replace(":id","ById").replace("/","_").replace("-","_") or "root"
        fn = "".join(p.capitalize() for p in fn.split("_"))
        fn = fn[0].lower() + fn[1:]
        if method == "GET":
            api_lines.append(f"export const {fn} = () => baseFetch('{path}').then(r => r.json())")
        elif method == "POST":
            api_lines.append(f"export const create{fn.capitalize()} = (body:any) => baseFetch('{path}', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(body)}}).then(r => r.json())")
        else:
            api_lines.append(f"export const {method.lower()}{fn.capitalize()} = (id:string, body:any) => baseFetch('{path}'.replace(':id', id), {{method:'{method}', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(body)}}).then(r => r.json())")
    # add hint for preview
    api_lines.append("// Preview mock auto-installed via src/mock/server.ts when VITE_API_MODE=mock")
    files.append({"path": "src/api.ts", "content": "\n".join(api_lines)})

    # types.ts
    types = ["// Intara — Types"]
    for t in tables:
        fname = t["name"].capitalize().replace("_","")
        if fname.endswith("s"): fname = fname[:-1]
        types.append(f"export type {fname} = {{ id: string; " + "; ".join(f"{f['name']}: { {'text':'string','integer':'number','timestamp':'string','boolean':'boolean'}[f['type']]}" for f in t["fields"]) + " }")
    files.append({"path": "src/types.ts", "content": "\n".join(types)})

    # pages — with create form for trial (use plain strings to avoid f-string brace issues)
    if not pages:
        pages = [{"name":"Dashboard","route":"/","components":["ItemList"]}]
    for p in pages[:4]:
        comp_imports = ", ".join(p.get("components", [])[:2])
        table_guess = tables[0]["name"] if tables else "items"
        tfields = next((t["fields"] for t in tables if t["name"] == table_guess), tables[0]["fields"] if tables else [{"name":"title","type":"text"}])
        # build inputs via plain concatenation
        inputs = []
        for f in tfields[:3]:
            fname = f["name"]
            inputs.append('        <input placeholder="' + fname + '" value={form.' + fname + ' || ""} onChange={e=>setForm(s=>({...s, ' + fname + ': e.target.value}))} style={{ flex:1, padding:8, borderRadius:8, border:"1px solid #e5e7eb" }} />')
        form_inputs = "\n".join(inputs)
        page_content = """import { useState, useEffect } from 'react'

export default function __NAME__() {
  const [items, setItems] = useState<any[]>([])
  const [form, setForm] = useState<any>({})
  const load = () => fetch('/api/__TABLE__').then(r => r.json()).then(setItems).catch(()=>{})
  useEffect(() => { load() }, [])
  const create = async () => {
    await fetch('/api/__TABLE__', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(form)})
    setForm({}); load()
  }
  return (
    <div>
      <h2 style={{ fontFamily: 'Space Grotesk', fontSize: 20, fontWeight: 700 }}>__NAME__ — __APP__</h2>
      <p style={{ color: 'var(--intara-muted)', fontSize: 13 }}>Route: __ROUTE__ • Components: __COMPS__</p>
      <div style={{ display:'flex', gap:8, marginTop:12, flexWrap:'wrap' }}>
__INPUTS__
        <button onClick={create} style={{ padding:'8px 14px', borderRadius:999, background:'#111', color:'white' }}>Create</button>
      </div>
      <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
        {items.length ? items.map((it:any, i:number) => <div key={i} className="glass" style={{ padding: 12 }}> {JSON.stringify(it).slice(0,160)} </div>) : <div className="glass" style={{ padding: 20, textAlign: 'center', color: 'var(--intara-muted)' }}>No __TABLE__ yet. Create one above — trial DB (IndexedDB) autosaves</div>}
      </div>
    </div>
  )
}
"""
        page_content = page_content.replace("__NAME__", p["name"]).replace("__TABLE__", table_guess).replace("__APP__", app_name).replace("__ROUTE__", p["route"]).replace("__COMPS__", comp_imports).replace("__INPUTS__", form_inputs)
        files.append({"path": f"src/pages/{p['name']}.tsx", "content": page_content})

    # components for each table
    for t in tables[:3]:
        cname = t["name"].capitalize().replace("_","")
        if cname.endswith("s"): cname = cname[:-1]
        cname = cname + "Card"
        field_names = ", ".join(f"{{\"{f['name']}\"}}" for f in t["fields"][:3])
        files.append({"path": f"src/components/{cname}.tsx", "content": f"""export function {cname}({{ item }}: {{ item: any }}) {{
  return (
    <div className="glass" style={{{{ padding: 12 }}}}>
      <div style={{{{ fontWeight: 600 }}}}>{{item.title || item.name || item.email || '{t['name']}'}} </div>
      <div style={{{{ color: 'var(--intara-muted)', fontSize: 12, marginTop: 4 }}}}> {", ".join(f['name'] for f in t['fields'][:3])} </div>
    </div>
  )
}}
""" })

    # App.tsx starter — Sandpack safe: always install mock for trial (no import.meta)
    routes_str = "\n".join(f'        <Route path="{p["route"]}" element={{<{p["name"]} />}} />' for p in pages[:4])
    imports_str = ", ".join(p["name"] for p in pages[:4])
    files.append({"path": "src/App.tsx", "content": f"""import {{ BrowserRouter, Routes, Route }} from 'react-router-dom'
import {{ useEffect }} from 'react'
import {{ {imports_str} }} from './pages'

export default function App() {{
  useEffect(() => {{
    // Trial: always install IndexedDB mock (no backend/Supabase needed)
    // For real backend, remove these two lines and set MODE='supabase' in src/api.ts
    import('./mock/server').then(m => m.installMockServer())
    import('./mock/seed').then(m => m.seedPreview())
  }}, [])
  return (
    <BrowserRouter>
      <Routes>
{routes_str}
      </Routes>
    </BrowserRouter>
  )
}}
""" })
    # src/pages/index.ts barrel
    files.append({"path": "src/pages/index.ts", "content": "\n".join([f"export {{ default as {p['name']} }} from './{p['name']}'" for p in pages[:4]])})

    # ensure at least 3 files
    return {"files": files}
