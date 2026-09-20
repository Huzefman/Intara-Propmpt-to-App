"""
FrontendGen v2 — distinct functional pages with LLM-first + template fallback
"""
from utils.json_parse import parse_json as _parse_json, is_quota_error


def generate_frontend_page_llm(page: dict, app_spec: dict) -> dict | None:
    """Try LLM generation for one page. Returns {path, content} or None on failure."""
    try:
        from prompts.frontend_page_v2 import build_frontend_page_prompt
        from services.llm import call_llm
        from services.validator import validate_tsx

        prompt = build_frontend_page_prompt(page, app_spec)
        raw = call_llm(prompt, temperature=0.3)
        data = _parse_json(raw)
        content = data.get("content", "")
        if not content:
            return None
        errors = validate_tsx(content)
        if errors:
            repair_prompt = f"Fix these TypeScript errors in the component:\n{errors}\n\nOriginal code:\n{content}"
            try:
                raw2 = call_llm(repair_prompt, temperature=0.1)
                data2 = _parse_json(raw2)
                content2 = data2.get("content", content)
                if not validate_tsx(content2):
                    content = content2
                else:
                    return None
            except:
                return None
        return {"path": data.get("path", f"src/pages/{page['name']}.tsx"), "content": content}
    except Exception as e:
        print(f"LLM frontend page {page.get('name')} failed: {e}")
        return None


def generate_frontend(prd: dict):
    tables = prd.get("tables", [])
    pages = prd.get("pages", [])
    app_name = prd.get("appName", "IntaraApp")
    files = []
    # api.ts same
    api_lines = [
        "// Intara Frontend — API client (mock vs real) — Sandpack safe",
        "const MODE = 'mock'",
        "const API_URL = ''",
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
    api_lines.append("// Preview mock auto-installed via src/mock/server.ts when VITE_API_MODE=mock")
    files.append({"path": "src/api.ts", "content": "\n".join(api_lines)})

    types = ["// Intara — Types"]
    for t in tables:
        fname = t["name"].capitalize().replace("_","")
        if fname.endswith("s"): fname = fname[:-1]
        types.append(f"export type {fname} = {{ id: string; " + "; ".join(f"{f['name']}: { {'text':'string','integer':'number','timestamp':'string','boolean':'boolean','uuid':'string'}[f['type']]}" for f in t["fields"]) + " }")
    files.append({"path": "src/types.ts", "content": "\n".join(types)})

    # helper to guess table
    used_tables = set()
    def guess_table(page, idx):
        candidates = [page["name"].lower()] + [c.lower() for c in page.get("components", [])]
        for t in tables:
            if t["name"] in used_tables: continue
            tname = t["name"].lower()
            t_sing = tname[:-1] if tname.endswith("s") else tname
            for cand in candidates:
                if tname in cand or t_sing in cand or cand in tname:
                    used_tables.add(t["name"])
                    return t["name"]
        for t in tables:
            tname = t["name"].lower()
            t_sing = tname[:-1] if tname.endswith("s") else tname
            for cand in candidates:
                if tname in cand or t_sing in cand or cand in tname:
                    return t["name"]
        for t in tables:
            if t["name"] not in used_tables:
                used_tables.add(t["name"])
                return t["name"]
        return tables[idx % len(tables)]["name"] if tables else "items"

    if not pages:
        pages = [{"name":"Dashboard","route":"/","components":["ItemList"]}]

    for idx, p in enumerate(pages[:6]):
        # LLM-first: try one LLM call per page
        llm_result = generate_frontend_page_llm(p, prd)
        if llm_result:
            files.append(llm_result)
            # still need to mark table as used for guessing
            guess_table(p, idx)
            continue
        # Template fallback (extracted)
        comp_imports = ", ".join(p.get("components", [])[:2])
        table_guess = guess_table(p, idx)
        tfields = next((t["fields"] for t in tables if t["name"] == table_guess), tables[0]["fields"] if tables else [{"name":"title","type":"text"}])
        # Determine page type by route and name
        is_detail = ":id" in p["route"]
        is_dashboard = p["route"] == "/" or "dashboard" in p["name"].lower()

        # Build inputs with proper types
        inputs = []
        for f in tfields[:4]:
            fname = f["name"]
            ftype = f["type"]
            if ftype == "boolean":
                inputs.append(f'        <label style={{{{ display:"flex", alignItems:"center", gap:6, fontSize:12 }}}}><input type="checkbox" checked={{{{!!form.{fname}}}}} onChange={{e=>setForm(s=>({{...s, {fname}: e.target.checked}}))}} /> {fname}</label>')
            elif ftype == "integer":
                inputs.append(f'        <input type="number" placeholder="{fname}" value={{form.{fname} || ""}} onChange={{e=>setForm(s=>({{...s, {fname}: Number(e.target.value)}}))}} style={{{{ flex:1, minWidth:120, padding:"10px 12px", borderRadius:10, border:"1px solid rgba(255,255,255,0.06)", background:"rgba(255,255,255,0.03)", color:"var(--intara-text)" }}}} />')
            elif ftype == "timestamp":
                inputs.append(f'        <input type="date" value={{form.{fname} ? String(form.{fname}).slice(0,10) : ""}} onChange={{e=>setForm(s=>({{...s, {fname}: e.target.value}}))}} style={{{{ flex:1, minWidth:120, padding:"10px 12px", borderRadius:10, border:"1px solid rgba(255,255,255,0.06)", background:"rgba(255,255,255,0.03)", color:"var(--intara-text)" }}}} />')
            else:
                inputs.append(f'        <input placeholder="{fname}" value={{form.{fname} || ""}} onChange={{e=>setForm(s=>({{...s, {fname}: e.target.value}}))}} style={{{{ flex:1, minWidth:120, padding:"10px 12px", borderRadius:10, border:"1px solid rgba(255,255,255,0.06)", background:"rgba(255,255,255,0.03)", color:"var(--intara-text)" }}}} />')
        form_inputs = "\n".join(inputs)

        # Determine page template
        if is_detail:
            # Detail page: fetch single item by ID from URL, show edit / delete
            page_content = f"""import {{ useState, useEffect }} from 'react'
import {{ useParams, Link }} from 'react-router-dom'

export default function {p["name"]}() {{
  const {{ id }} = useParams()
  const [item, setItem] = useState<any>(null)
  const [form, setForm] = useState<any>({{}})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const load = async () => {{
    setLoading(true)
    try {{
      const res = await fetch(`/api/{table_guess}/${{id}}`)
      if (res.ok) {{
        const data = await res.json()
        setItem(data)
        setForm(data)
      }} else {{
        // fallback to list and find
        const list = await fetch('/api/{table_guess}').then(r=>r.json())
        const found = Array.isArray(list) ? list.find((x:any)=>String(x.id)===String(id)) : null
        if (found) {{ setItem(found); setForm(found) }}
      }}
    }} catch {{}}
    setLoading(false)
  }}
  useEffect(() => {{ if(id) load() }}, [id])

  const save = async () => {{
    setSaving(true)
    await fetch(`/api/{table_guess}/${{id}}`, {{method:'PATCH', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(form)}})
    setSaving(false)
    load()
  }}
  const remove = async () => {{
    if (!confirm('Delete this {table_guess}?')) return
    await fetch(`/api/{table_guess}/${{id}}`, {{method:'DELETE'}})
    window.location.href = '/'
  }}

  if (loading) return <div className="glass" style={{{{ padding: 24, textAlign: 'center' }}}}>Loading {table_guess}…</div>
  if (!item) return <div className="glass" style={{{{ padding: 24, textAlign: 'center' }}}}>Not found <Link to="/">Back to {p["name"]}</Link></div>

  return (
    <div style={{{{ maxWidth: 640, margin: '0 auto' }}}}>
      <Link to="/" style={{{{ fontSize: 12, color: 'var(--intara-faint)', textDecoration: 'none' }}}}>← Back</Link>
      <h2 style={{{{ fontFamily: 'Space Grotesk', fontSize: 22, fontWeight: 600, marginTop: 8 }}}}>{p["name"]} — {app_name}</h2>
      <p style={{{{ color: 'var(--intara-faint)', fontSize: 12, marginTop: 4 }}}}>Editing {table_guess} #{{id}} • {", ".join([f['name'] for f in tfields[:3]])}</p>
      
      <div className="glass" style={{{{ padding: 16, marginTop: 16, display: 'grid', gap: 12 }}}}>
{form_inputs}
        <div style={{{{ display: 'flex', gap: 8, marginTop: 8 }}}}>
          <button onClick={{save}} disabled={{saving}} className="btn-primary" style={{{{ flex: 1 }}}}>{{saving ? 'Saving…' : 'Save changes'}}</button>
          <button onClick={{remove}} className="btn-ghost" style={{{{ color: '#F87171', borderColor: 'rgba(248,113,113,0.2)' }}}}>Delete</button>
        </div>
      </div>

      <div className="glass" style={{{{ padding: 14, marginTop: 16 }}}}>
        <div style={{{{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 8 }}}}>Current data</div>
        <pre className="code-block" style={{{{ background: 'transparent', border: 'none', padding: 0 }}}}>{{JSON.stringify(item, null, 2)}}</pre>
      </div>
    </div>
  )
}}
"""
        else:
            # List/Dashboard page with search, stats, and cards
            # Build field displays based on types
            field_displays = []
            for f in tfields[:4]:
                fname = f["name"]
                if f["type"] == "boolean":
                    field_displays.append(f'<span style={{{{ padding:"3px 8px", borderRadius:999, fontSize:11, background: item.{fname} ? "rgba(16,185,129,0.12)" : "rgba(255,255,255,0.04)", border:"1px solid rgba(255,255,255,0.06)", color: item.{fname} ? "#10B981" : "var(--intara-faint)"}}}}>{{item.{fname} ? "✓ " : ""}}{fname}</span>')
                elif f["type"] == "timestamp":
                    field_displays.append(f'<span style={{{{ fontSize:11, color:"var(--intara-faint)" }}}}>{{item.{fname} ? new Date(item.{fname}).toLocaleDateString() : ""}}</span>')
                elif f["type"] == "integer":
                    field_displays.append(f'<span style={{{{ fontSize:11, fontWeight:600, color:"var(--intara-nebula-light)"}}}}>{{item.{fname} ?? 0}}</span>')
                else:
                    # for title/name/email fields, show prominently
                    if fname in ["title","name","email"]:
                        continue
                    field_displays.append(f'<span style={{{{ fontSize:11, color:"var(--intara-faint)"}}}}>{{item.{fname} || ""}}</span>')
            # title field display
            title_field = next((f["name"] for f in tfields if f["name"] in ["title","name","email"]), tfields[0]["name"])
            field_displays_str = " ".join(field_displays)

            # Stats for dashboard
            stats_section = ""
            if is_dashboard:
                stats_section = f"""
      <div style={{{{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 }}}}>
        <div className="glass" style={{{{ padding: 14, textAlign: 'center' }}}}>
          <div style={{{{ fontSize: 20, fontWeight: 600 }}}}>{{items.length}}</div>
          <div style={{{{ fontSize: 11, color: 'var(--intara-faint)', textTransform: 'uppercase', letterSpacing: '0.06em' }}}}>Total {table_guess}</div>
        </div>
        <div className="glass" style={{{{ padding: 14, textAlign: 'center' }}}}>
          <div style={{{{ fontSize: 20, fontWeight: 600, color: 'var(--intara-nebula-light)' }}}}>{{items.filter((x:any)=>x.completed || x.published || x.status==='active').length}}</div>
          <div style={{{{ fontSize: 11, color: 'var(--intara-faint)', textTransform: 'uppercase', letterSpacing: '0.06em' }}}}>Active</div>
        </div>
        <div className="glass" style={{{{ padding: 14, textAlign: 'center' }}}}>
          <div style={{{{ fontSize: 20, fontWeight: 600 }}}}>{{new Set(items.map((x:any)=>x.title||x.name)).size}}</div>
          <div style={{{{ fontSize: 11, color: 'var(--intara-faint)', textTransform: 'uppercase', letterSpacing: '0.06em' }}}}>Unique</div>
        </div>
      </div>"""

            page_content = f"""import {{ useState, useEffect, useMemo }} from 'react'
import {{ Link }} from 'react-router-dom'

export default function {p["name"]}() {{
  const [items, setItems] = useState<any[]>([])
  const [form, setForm] = useState<any>({{}})
  const [q, setQ] = useState("")
  const [filter, setFilter] = useState("all")

  const load = () => fetch('/api/{table_guess}').then(r => r.json()).then(d => setItems(Array.isArray(d) ? d : [])).catch(()=>{{}})
  useEffect(() => {{ load() }}, [])

  const create = async () => {{
    if (!form.{tfields[0]["name"]}?.trim()) return
    await fetch('/api/{table_guess}', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(form)}})
    setForm({{}}); load()
  }}

  const toggle = async (id:any, field:string, value:any) => {{
    await fetch(`/api/{table_guess}/${{id}}`, {{method:'PATCH', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{ [field]: value }})}})
    load()
  }}

  const filtered = useMemo(() => {{
    let out = items
    if (q) out = out.filter(x => Object.values(x).join(' ').toLowerCase().includes(q.toLowerCase()))
    if (filter === 'active') out = out.filter(x => x.completed || x.published === true || x.status === 'active')
    if (filter === 'done') out = out.filter(x => x.completed === true)
    return out
  }}, [items, q, filter])

  return (
    <div>
      <div style={{{{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}}}>
        <div>
          <h2 style={{{{ fontFamily: 'Space Grotesk', fontSize: 22, fontWeight: 600, letterSpacing: '-0.02em' }}}}>{p["name"]} — {app_name}</h2>
          <p style={{{{ color: 'var(--intara-faint)', fontSize: 12, marginTop: 4 }}}}>Manage {table_guess} • {", ".join([f['name'] for f in tfields[:4]])}</p>
        </div>
        <Link to="{p["route"]}" style={{{{ fontSize: 11, padding: '6px 10px', borderRadius: 999, border: '1px solid rgba(255,255,255,0.06)', textDecoration: 'none', color: 'var(--intara-faint)' }}}}>{p["route"]}</Link>
      </div>
{stats_section}
      <div className="glass" style={{{{ padding: 14, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}}}>
        <input placeholder="Search {table_guess}…" value={{q}} onChange={{e=>setQ(e.target.value)}} style={{{{ flex: 1, minWidth: 160, padding: '10px 12px', borderRadius: 10, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.03)', color: 'var(--intara-text)' }}}} />
        <select value={{filter}} onChange={{e=>setFilter(e.target.value)}} style={{{{ padding: '10px 12px', borderRadius: 10, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.03)', color: 'var(--intara-text)', fontSize: 12 }}}}>
          <option value="all">All</option>
          <option value="active">Active</option>
          <option value="done">Done</option>
        </select>
      </div>

      <div className="glass" style={{{{ padding: 14, marginTop: 12, display: 'grid', gap: 10 }}}}>
        <div style={{{{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 2 }}}}>Create new {table_guess[:-1] if table_guess.endswith('s') else table_guess}</div>
        <div style={{{{ display:'flex', gap:8, flexWrap:'wrap' }}}}>
{form_inputs}
          <button onClick={{create}} className="btn-primary" style={{{{ whiteSpace: 'nowrap' }}}} >Add {table_guess[:-1] if table_guess.endswith('s') else table_guess}</button>
        </div>
      </div>

      <div style={{{{ display: 'grid', gap: 10, marginTop: 16 }}}}>
        {{filtered.length ? filtered.map((item:any) => (
          <div key={{item.id}} className="glass" style={{{{ padding: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}}}>
            <div style={{{{ flex: 1, minWidth: 0 }}}}>
              <div style={{{{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}}}>
                <Link to={{`/{table_guess}/${{item.id}}`}} style={{{{ fontWeight: 600, fontSize: 13, color: 'var(--intara-text)', textDecoration: 'none' }}}}>{{item.{title_field} || item.name || item.email || 'Untitled'}}</Link>
                {field_displays_str}
              </div>
              <div style={{{{ fontSize: 11, color: 'var(--intara-dim)', marginTop: 4 }}}}>{{item.id ? `#${{String(item.id).slice(0,8)}}` : ''}} { ' · '.join([f"{{f['name']}}: {{item.{f['name']}}}" for f in tfields[1:2]]) if len(tfields)>1 else ''}</div>
            </div>
            <div style={{{{ display: 'flex', gap: 6, alignItems: 'center' }}}}>
              {{item.completed !== undefined && (
                <button onClick={{()=>toggle(item.id, 'completed', !item.completed)}} style={{{{ padding: '6px 10px', borderRadius: 999, fontSize: 11, border: '1px solid rgba(255,255,255,0.06)', background: item.completed ? 'rgba(16,185,129,0.12)' : 'transparent', color: item.completed ? '#10B981' : 'var(--intara-faint)'}}}}>{{item.completed ? 'Done' : 'Todo'}}</button>
              )}}
              <Link to={{`/{table_guess}/${{item.id}}`}} className="btn-ghost" style={{{{ padding: '6px 10px', fontSize: 11, textDecoration: 'none' }}}}>View</Link>
            </div>
          </div>
        )) : (
          <div className="glass" style={{{{ padding: 32, textAlign: 'center', color: 'var(--intara-faint)' }}}}>
            <div style={{{{ fontSize: 13, fontWeight: 500 }}}}>No {table_guess} yet</div>
            <div style={{{{ fontSize: 11, marginTop: 4 }}}}>Create your first {table_guess[:-1] if table_guess.endswith('s') else table_guess} above — it saves instantly to IndexedDB</div>
          </div>
        )}}
      </div>
    </div>
  )
}}
"""
        page_content = page_content.replace("__NAME__", p["name"]).replace("__TABLE__", table_guess).replace("__APP__", app_name).replace("__ROUTE__", p["route"]).replace("__COMPS__", comp_imports).replace("__INPUTS__", form_inputs)
        files.append({"path": f"src/pages/{p['name']}.tsx", "content": page_content})

    # components for each table - more functional
    for t in tables[:3]:
        cname = t["name"].capitalize().replace("_","")
        if cname.endswith("s"): cname = cname[:-1]
        cname = cname + "Card"
        # Build a proper card that shows all fields nicely, not just JSON
        field_rows = "\n".join([f'      <div style={{{{ fontSize: 11 }}}}><span style={{{{ color: "var(--intara-faint)" }}}}>{f["name"]}:</span> <span style={{{{ color: "var(--intara-text)", fontWeight: 500 }}}}>{{String(item.{f["name"]} ?? "")}}</span></div>' for f in t["fields"][:4]])
        files.append({"path": f"src/components/{cname}.tsx", "content": f"""export function {cname}({{ item, onSelect }}: {{ item: any, onSelect?: (id:any)=>void }}) {{
  return (
    <div className="glass" style={{{{ padding: 14, cursor: onSelect ? 'pointer' : 'default' }}}} onClick={{()=> onSelect?.(item.id)}}>
      <div style={{{{ fontWeight: 600, fontSize: 13 }}}}>{{item.title || item.name || item.email || '{t['name']}'}} </div>
      <div style={{{{ display: 'grid', gap: 4, marginTop: 8 }}}}>
{field_rows}
      </div>
    </div>
  )
}}
""" })

    # App.tsx starter — premium minimal with nav, Sandpack safe
    routes_str = "\n".join(f'        <Route path="{p["route"]}" element={{<{p["name"]} />}} />' for p in pages[:4])
    imports_str = ", ".join(p["name"] for p in pages[:4])
    nav_links = "\n".join(f'          <Link to="{p["route"]}" style={{{{ padding:"8px 14px", borderRadius:999, textDecoration:"none", fontSize:12, fontWeight:500, color:"var(--intara-muted)", border:"1px solid transparent" }}}}>{p["name"]}</Link>' for p in pages[:4])
    files.append({"path": "src/App.tsx", "content": f"""import {{ BrowserRouter, Routes, Route, Link }} from 'react-router-dom'
import {{ useEffect }} from 'react'
import {{ {imports_str} }} from './pages'

export default function App() {{
  useEffect(() => {{
    // Trial: IndexedDB mock — no backend needed
    import('./mock/server').then(m => m.installMockServer())
    import('./mock/seed').then(m => m.seedPreview())
  }}, [])
  return (
    <BrowserRouter>
      <div style={{{{ minHeight:"100vh", background:"#07070B", color:"#F8FAFC", fontFamily:"Inter, system-ui, sans-serif" }}}}>
        <nav style={{{{ display:"flex", gap:8, padding:"16px 20px", borderBottom:"1px solid rgba(255,255,255,0.06)", position:"sticky", top:0, background:"rgba(7,7,11,0.8)", backdropFilter:"blur(16px)", zIndex:10 }}}}>
          <span style={{{{ fontFamily:"Space Grotesk", fontWeight:500, letterSpacing:"-0.02em", marginRight:12 }}}}>{app_name}</span>
{nav_links}
        </nav>
        <main style={{{{ maxWidth:820, margin:"0 auto", padding:"24px 20px" }}}}>
          <Routes>
{routes_str}
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}}
""" })
    # src/pages/index.ts barrel
    files.append({"path": "src/pages/index.ts", "content": "\n".join([f"export {{ default as {p['name']} }} from './{p['name']}'" for p in pages[:4]])})

    # ensure at least 3 files
    return {"files": files}
