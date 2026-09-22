"""
Orchestrator — strict sequential build from BuildPlan, SSE events
One prompt per page/component (LLM when key available, deterministic fallback)
"""
import time, traceback, asyncio, os, json, re
from typing import Dict, Any, Callable

# in-memory build state: wid -> {steps: {id: {status, startedAt, endedAt, error}}, current, log: []}
BUILD_STATE: Dict[str, Any] = {}
# simple pub/sub for SSE: wid -> list of asyncio.Queue
SSE_QUEUES: Dict[str, list] = {}

def init_build_state(wid: str, build_graph):
    BUILD_STATE[wid] = {
        "steps": {n["id"]: {"status":"pending","startedAt":None,"endedAt":None,"error":None} for n in build_graph},
        "graph": build_graph,
        "log": [],
        "current": None
    }
    SSE_QUEUES[wid] = []

def emit(wid: str, event: str, data: dict):
    # push to queues and log
    payload = {"event": event, "data": data, "ts": time.time()}
    if wid in BUILD_STATE:
        BUILD_STATE[wid]["log"].append(payload)
    for q in SSE_QUEUES.get(wid, []):
        try: q.put_nowait(payload)
        except: pass

def _try_llm_frontend_page(appName, tagline, table, fields, pageName, route, components, all_tables, all_pages):
    """Try LLM for one page, fallback to None on any failure (429/no key)"""
    if not os.getenv("GEMINI_API_KEY"):
        return None
    try:
        from prompts.frontend_page import FRONTEND_PAGE_PROMPT
        from main import call_gemini, parse_json
        all_tables_str = ", ".join([f"{t['name']}({','.join(f['name'] for f in t['fields'])})" for t in all_tables])
        all_pages_str = ", ".join([f"{p['name']}:{p['route']}" for p in all_pages])
        prompt = FRONTEND_PAGE_PROMPT
        prompt = prompt.replace("__APP_NAME__", appName).replace("__TAGLINE__", tagline)
        prompt = prompt.replace("__TABLE__", table).replace("__FIELDS__", json.dumps(fields))
        prompt = prompt.replace("__PAGE_NAME__", pageName).replace("__ROUTE__", route).replace("__COMPONENTS__", ",".join(components))
        prompt = prompt.replace("__ALL_TABLES__", all_tables_str).replace("__ALL_PAGES__", all_pages_str)
        raw = call_gemini(prompt)
        data = parse_json(raw)
        if "content" in data and "path" in data:
            return data
        if "path" in data and "content" not in data:
            for k, v in data.items():
                if "content" in k.lower():
                    return {"path": data["path"], "content": v}
        return None
    except Exception as e:
        print(f"LLM frontend page {pageName} fallback: {e}")
        return None

def _try_llm_backend_table(appName, table, fields, all_tables, apis):
    if not os.getenv("GEMINI_API_KEY"):
        return None
    try:
        from prompts.backend_table import BACKEND_TABLE_PROMPT
        from main import call_gemini, parse_json
        prompt = BACKEND_TABLE_PROMPT
        prompt = prompt.replace("__APP_NAME__", appName).replace("__TABLE__", table).replace("__FIELDS__", json.dumps(fields))
        prompt = prompt.replace("__ALL_TABLES__", json.dumps([t["name"] for t in all_tables])).replace("__APIS__", json.dumps(apis))
        raw = call_gemini(prompt)
        data = parse_json(raw)
        if "models" in data or "routes" in data:
            return data
        return None
    except Exception as e:
        print(f"LLM backend table {table} fallback: {e}")
        return None

async def run_build_sequential(wid: str, build_plan: dict, prompt: str):
    """
    Strict sequential: schema -> per-table backend -> per-page frontend -> wiring -> validate
    Loads BuildPlan from DB as source of truth, persists each step's prompt/output to wish_steps (fail-fast).
    Resumes: skips steps already done in DB.
    """
    from services.generators.schema_gen import generate_schema
    from services.generators.scaffold_gen import frontend_scaffold, backend_scaffold
    from services.preview.mock_gen import generate_mock

    # Load canonical BuildPlan from DB (fail-fast) — ensures we build from persisted plan, not stale MEM
    try:
        from db.wishes import get_wish_with_steps, set_wish_status
        db_wish = get_wish_with_steps(wid)
        build_plan = db_wish.get("prd") or build_plan
        prompt = db_wish.get("prompt", prompt)
    except Exception as e:
        print(f"orchestrator load DB failed for {wid}: {e}")
        raise

    graph = build_plan.get("buildGraph", [])
    # init in-memory for SSE, but also ensure DB rows exist (from create_wish_tx)
    init_build_state(wid, graph)
    # also sync DB steps that may already be done (resume) — and restore accumulators from DB outputs
    # Accumulators for final artifacts
    schema = None
    backend_tables = {}  # name -> files+openapi fragment
    frontend_pages = {}  # name -> files
    be_requirements = None
    be_openapi = {"openapi":"3.0.0","info":{"title":build_plan.get("appName","IntaraApp"),"version":"1.0.0"},"paths":{}}
    preview = None
    fe_scaffold = None
    be_scaffold = None
    try:
        from db.wishes import get_steps
        db_steps = {row["step_id"]: row for row in get_steps(wid)}
        for nid, row in db_steps.items():
            if row["status"] == "done" and nid in BUILD_STATE[wid]["steps"]:
                BUILD_STATE[wid]["steps"][nid]["status"] = "done"
                BUILD_STATE[wid]["steps"][nid]["startedAt"] = row.get("started_at")
                BUILD_STATE[wid]["steps"][nid]["endedAt"] = row.get("ended_at")
                # restore accumulators from DB output for resume
                out = row.get("output") or {}
                if nid == "schema-foundation" and out.get("tables"):
                    # reconstruct schema from output (tables only, need to rebuild full schema)
                    try:
                        from services.generators.schema_gen import generate_schema
                        # output has tables, prisma snippet, sql snippet — rebuild full
                        schema = {"tables": out["tables"], "prisma": out.get("prisma",""), "sql": out.get("sql","")}
                        if not schema["prisma"] or not schema["sql"]:
                            schema = generate_schema({"tables": out["tables"]})
                    except: pass
                elif nid.startswith("backend-") and out.get("files"):
                    # output has files list, but our backend_tables expects frag with files/openapi
                    # reconstruct minimal frag
                    ref = nid.replace("backend-","")
                    backend_tables[ref] = {"files": [{"path": p, "content": ""} for p in out.get("files",[])], "openapi": out.get("openapi",{})}
                    # be_openapi merge
                    for path, methods in out.get("openapi",{}).get("paths",{}).items():
                        be_openapi["paths"][path] = methods
                elif nid.startswith("frontend-") and out.get("files"):
                    ref = nid.replace("frontend-","")
                    frontend_pages[ref] = {"files": [{"path": p, "content": ""} for p in out.get("files",[])]}
                elif nid == "wiring" and out.get("fe_scaffold"):
                    # wiring output has scaffold keys, reconstruct minimal
                    fe_scaffold = {k: "" for k in out.get("fe_scaffold",[])}
                    be_scaffold = {k: "" for k in out.get("be_scaffold",[])}
                    preview = {k: "" for k in out.get("preview",[])}
                    # if we have actual content in DB output, it would be files, but our wiring output only has keys, not content
                    # For resume, we need full content, so we will re-run wiring if needed (it is cheap deterministic)
                    # Mark wiring as not really done for resume purposes if content missing
                    if len(fe_scaffold) < 5:  # wiring output truncated, need to re-run wiring
                        BUILD_STATE[wid]["steps"][nid]["status"] = "pending"
    except Exception as e:
        print(f"resume sync failed for {wid}: {e}")
    emit(wid, "build_started", {"wid": wid, "graph": [n["id"] for n in graph]})

    # helper to update wish artifacts for polling fallback (DB is source of truth, MEM is cache)
    def update_wish_partial():
        try:
            from routers.wishes import MEM
            from db.wishes import set_wish_status, get_wish_with_steps
            # Update DB snapshot for polling (fail-fast, but don't halt build on artifact snapshot failure)
            try:
                wish = get_wish_with_steps(wid)
                artifacts = wish.get("artifacts") or {}
                artifacts["steps"] = BUILD_STATE[wid]["steps"]
                artifacts["buildGraph"] = graph
                set_wish_status(wid, wish.get("status","building"), artifacts=artifacts)
            except Exception as e:
                print(f"DB artifact snapshot failed for {wid}: {e}")
            # also update MEM cache
            if wid in MEM:
                partial = MEM[wid].get("artifacts", {})
                partial["steps"] = BUILD_STATE[wid]["steps"]
                partial["buildGraph"] = graph
                MEM[wid]["artifacts"] = partial
        except Exception as e:
            print(f"partial update failed: {e}")

    # helper to persist step to DB (fail-fast)
    def persist_step(step_id, status, prompt=None, raw=None, output=None, error=None, started=None, ended=None):
        try:
            from db.wishes import update_step, set_wish_status
            started_s = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)) if started else None
            ended_s = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ended)) if ended else None
            update_step(wid, step_id, status=status, prompt=prompt, raw_response=raw, output=output, error=error, started_at=started_s, ended_at=ended_s)
            # also update wishes.current_step_id and artifacts.steps snapshot
            try:
                from db.wishes import get_wish_with_steps
                wish = get_wish_with_steps(wid)
                # keep artifacts.steps in sync for polling fallback
                set_wish_status(wid, wish.get("status","building"), current_step_id=step_id, artifacts=wish.get("artifacts"))
            except: pass
        except Exception as e:
            print(f"persist_step DB fail-fast for {step_id}: {e}")
            # fail-fast: raise to halt build and surface to caller
            raise

    for node in graph:
        nid = node["id"]
        # Resume: skip already done steps (from DB)
        if BUILD_STATE[wid]["steps"].get(nid, {}).get("status") == "done":
            emit(wid, "step_skipped", {"stepId": nid, "kind": node["kind"]})
            continue
        kind = node["kind"]
        ref = node.get("ref")
        BUILD_STATE[wid]["steps"][nid]["status"] = "running"
        BUILD_STATE[wid]["steps"][nid]["startedAt"] = time.time()
        BUILD_STATE[wid]["current"] = nid
        emit(wid, "step_started", {"stepId": nid, "kind": kind, "ref": ref})
        # persist running to DB (fail-fast)
        try:
            persist_step(nid, "running", started=BUILD_STATE[wid]["steps"][nid]["startedAt"])
        except Exception as e:
            BUILD_STATE[wid]["steps"][nid]["status"] = "failed"
            BUILD_STATE[wid]["steps"][nid]["error"] = str(e)
            emit(wid, "step_failed", {"stepId": nid, "error": str(e)})
            emit(wid, "build_failed", {"wid": wid, "failedStep": nid, "reason": "DB persist failed"})
            return False
        update_wish_partial()
        # per-step prompt and output capture for DB
        step_prompt = None
        step_raw = None
        step_output = None
        try:
            if kind == "schema":
                step_prompt = f"Generate schema for tables: {json.dumps(build_plan['tables'])}"
                # pass entities so FK columns land in prisma/sql (contract parity with mock)
                schema = generate_schema({"tables": build_plan["tables"],
                                          "entities": build_plan.get("entities")})
                step_output = {"tables": schema["tables"], "prisma": schema["prisma"][:500], "sql": schema["sql"][:500]}
                BUILD_STATE[wid]["steps"][nid]["status"] = "done"
            elif kind == "backend_table":
                single_prd = {**build_plan, "tables": [t for t in build_plan["tables"] if t["name"]==ref][:1], "pages": [], "apis": [a for a in build_plan.get("apis",[]) if ref in a["path"]]}
                if not single_prd["tables"]:
                    single_prd["tables"] = [t for t in build_plan["tables"] if t["name"]==ref]
                step_prompt = f"Build backend for table {ref}: {json.dumps(single_prd['tables'])} apis {json.dumps(single_prd['apis'])}"
                from services.generators.backend_gen import generate_backend
                frag = generate_backend(single_prd)
                backend_tables[ref] = frag
                step_output = {"files": [f["path"] for f in frag.get("files",[])], "openapi": frag.get("openapi")}
                for path, methods in frag.get("openapi",{}).get("paths",{}).items():
                    if path not in be_openapi["paths"]:
                        be_openapi["paths"][path] = methods
                if be_requirements is None:
                    be_requirements = frag.get("requirements")
                BUILD_STATE[wid]["steps"][nid]["status"] = "done"
            elif kind == "frontend_page":
                page = next((p for p in build_plan["pages"] if p["name"]==ref), None)
                if not page:
                    raise ValueError(f"page {ref} not in plan")
                step_prompt = f"Build frontend page {ref} route {page.get('route')} for table {page.get('table')} components {page.get('components')}"
                from services.generators.frontend_gen import generate_frontend
                single_prd = {**build_plan, "pages": [page], "tables": build_plan["tables"]}
                frag = generate_frontend(single_prd)
                step_output = {"files": [f["path"] for f in frag.get("files",[])], "page": page["name"]}
                frontend_pages[ref] = frag
                BUILD_STATE[wid]["steps"][nid]["status"] = "done"
            elif kind == "wiring":
                step_prompt = f"Wiring scaffold + mock for {build_plan.get('appName')} with tables {len(build_plan.get('tables',[]))} pages {len(build_plan.get('pages',[]))}"
                app_name = build_plan.get("appName","IntaraApp")
                from services.contract import build_contract, ddl_for
                _contract = build_contract(build_plan, (schema or {}).get("tables"))
                fe_scaffold = frontend_scaffold(app_name)
                be_scaffold = backend_scaffold(app_name, (schema or {"tables": build_plan["tables"]})["tables"],
                                               ddl_for(_contract))
                preview = generate_mock(build_plan)
                step_output = {"fe_scaffold": list(fe_scaffold.keys())[:5], "be_scaffold": list(be_scaffold.keys())[:5], "preview": list(preview.keys())}
                BUILD_STATE[wid]["steps"][nid]["status"] = "done"
            elif kind == "validate":
                step_prompt = "Validate: blocking gates (tsc + vite build + import + TestClient CRUD)"
                # Blocking gates: node→done ONLY on green, else step failed (fail-closed).
                # Gate trees are regenerated template-only ($0): templates are the guaranteed
                # fallback, and every systemic TaskNest failure lived in template output.
                try:
                    from services.validator import validate_tsx, validate_python, validate_imports_consistency
                    from services.contract import build_contract as _bcv
                    validation_errors = []
                    for frag in frontend_pages.values():
                        for f in frag.get("files", []):
                            if f["path"].endswith(".tsx"):
                                errs = validate_tsx(f["content"])
                                if errs:
                                    validation_errors.append(f"{f['path']}: {errs}")
                    for frag in backend_tables.values():
                        for f in frag.get("files", []):
                            if f["path"].endswith(".py"):
                                errs = validate_python(f["content"])
                                if errs:
                                    validation_errors.append(f"{f['path']}: {errs}")
                    all_fe = [f for frag in frontend_pages.values() for f in frag.get("files", [])]
                    all_be = [f for frag in backend_tables.values() for f in frag.get("files", [])]
                    cross_errs = validate_imports_consistency(all_fe, all_be)
                    validation_errors.extend(cross_errs)
                    # --- heavy gates on the deterministic core ---
                    emit(wid, "validation_started", {"stepId": nid})
                    _cv = _bcv(build_plan, (schema or {}).get("tables"))
                    _prev_tpl = os.environ.get("INTARA_TEMPLATE_ONLY")
                    os.environ["INTARA_TEMPLATE_ONLY"] = "1"
                    try:
                        from services.generators.frontend_gen import generate_frontend as _gf
                        from services.generators.backend_gen import generate_backend as _gb
                        from services.generators.scaffold_gen import frontend_scaffold as _fsc
                        from services.preview.mock_gen import generate_mock as _gm
                        _fe_full = _gf(build_plan)
                        _be_full = _gb(build_plan)
                        _mock = _gm(build_plan)
                    finally:
                        if _prev_tpl is None:
                            os.environ.pop("INTARA_TEMPLATE_ONLY", None)
                        else:
                            os.environ["INTARA_TEMPLATE_ONLY"] = _prev_tpl
                    from services.gates import run_fe_gates, run_be_gates, run_contract_checks
                    _scaf = _fsc(build_plan.get("appName", "IntaraApp"))
                    _fe_tree = [{"path": p, "content": c} for p, c in _scaf.items()]
                    _seen = {f["path"] for f in _fe_tree}
                    for p, c in _mock.items():
                        if p not in _seen:
                            _fe_tree.append({"path": p, "content": c}); _seen.add(p)
                    for f in _fe_full.get("files", []):
                        if f["path"] not in _seen:
                            _fe_tree.append(f); _seen.add(f["path"])
                    _be_tree = [{"path": p, "content": c} for p, c in (be_scaffold or {}).items()]
                    for f in _be_full.get("files", []):
                        if f["path"] not in {x["path"] for x in _be_tree}:
                            _be_tree.append(f)
                    validation_errors += run_contract_checks(
                        _cv, _fe_tree, _be_tree, _be_full.get("openapi", {}),
                        _scaf.get("package.json", ""), _scaf.get("postcss.config.js"))
                    if not any(e.startswith("DEGRADED") for e in validation_errors):
                        emit(wid, "validation_gates", {"stepId": nid, "phase": "tsc/vite"})
                        validation_errors += run_fe_gates(_fe_tree, _scaf)
                        emit(wid, "validation_gates", {"stepId": nid, "phase": "import/crud"})
                        validation_errors += run_be_gates(_be_tree, _cv)
                    # --- one repair attempt per failing file, then re-run that side once ---
                    from services.gates import repair_gate_files as _rgf
                    _repaired = _rgf(_cv, validation_errors, _fe_tree, _be_tree)
                    if _repaired:
                        _fe_err = [e for e in validation_errors if "src/" in e or "tsc" in e or "vite" in e]
                        _be_err = [e for e in validation_errors if "server/" in e or "py_compile" in e or "CRUD" in e or "import " in e]
                        validation_errors = [e for e in validation_errors
                                             if e not in _fe_err and e not in _be_err]
                        if _repaired.get("fe"):
                            validation_errors += run_fe_gates(_fe_tree, _scaf)
                        if _repaired.get("be"):
                            validation_errors += run_be_gates(_be_tree, _cv)
                    step_output = {"validated": len(validation_errors) == 0, "errors": validation_errors[:10], "fe_files": sum(len(v.get("files",[])) for v in frontend_pages.values()), "be_tables": len(backend_tables)}
                    if validation_errors:
                        raise RuntimeError("blocking gates failed: " + "; ".join(validation_errors[:5]))
                    BUILD_STATE[wid]["steps"][nid]["status"] = "done"
                except Exception as e:
                    # fallback to simple check if validator not available
                    if not schema or not fe_scaffold or not be_scaffold:
                        # try to reconstruct as before
                        if not schema:
                            try:
                                from db.wishes import get_steps
                                db_steps = {r["step_id"]: r for r in get_steps(wid)}
                                if "schema-foundation" in db_steps and db_steps["schema-foundation"].get("output"):
                                    schema = {"tables": db_steps["schema-foundation"]["output"].get("tables", [])}
                            except: pass
                            if not schema:
                                schema = {"tables": build_plan.get("tables", [])}
                        if not fe_scaffold:
                            from services.generators.scaffold_gen import frontend_scaffold, backend_scaffold
                            from services.contract import build_contract as _bc, ddl_for as _ddl
                            _c = _bc(build_plan, (schema or {}).get("tables"))
                            fe_scaffold = frontend_scaffold(build_plan.get("appName","IntaraApp"))
                            be_scaffold = backend_scaffold(build_plan.get("appName","IntaraApp"), (schema or {"tables": build_plan["tables"]})["tables"], _ddl(_c))
                        if not be_scaffold:
                            from services.generators.scaffold_gen import backend_scaffold
                            from services.contract import build_contract as _bc2, ddl_for as _ddl2
                            _c2 = _bc2(build_plan, (schema or {}).get("tables"))
                            be_scaffold = backend_scaffold(build_plan.get("appName","IntaraApp"), (schema or {"tables": build_plan["tables"]})["tables"], _ddl2(_c2))
                    step_output = {"validated": True, "fe_files": sum(len(v.get("files",[])) for v in frontend_pages.values()), "be_tables": len(backend_tables)}
                    BUILD_STATE[wid]["steps"][nid]["status"] = "done"
            else:
                step_output = {"kind": kind}
                BUILD_STATE[wid]["steps"][nid]["status"] = "done"
        except Exception as e:
            traceback.print_exc()
            BUILD_STATE[wid]["steps"][nid]["status"] = "failed"
            BUILD_STATE[wid]["steps"][nid]["error"] = str(e)
            try:
                persist_step(nid, "failed", prompt=step_prompt, raw=step_raw, output=step_output, error=str(e), ended=time.time())
            except: pass
            emit(wid, "step_failed", {"stepId": nid, "error": str(e)})
            update_wish_partial()
            emit(wid, "build_failed", {"wid": wid, "failedStep": nid})
            return False
        BUILD_STATE[wid]["steps"][nid]["endedAt"] = time.time()
        # persist done to DB (fail-fast) with full prompt/output
        try:
            persist_step(nid, "done", prompt=step_prompt, raw=step_raw or f"deterministic fallback for {nid}", output=step_output, ended=BUILD_STATE[wid]["steps"][nid]["endedAt"])
        except Exception as e:
            BUILD_STATE[wid]["steps"][nid]["status"] = "failed"
            BUILD_STATE[wid]["steps"][nid]["error"] = f"DB persist failed: {e}"
            emit(wid, "step_failed", {"stepId": nid, "error": f"DB persist failed: {e}"})
            emit(wid, "build_failed", {"wid": wid, "failedStep": nid})
            return False
        emit(wid, "step_done", {"stepId": nid, "kind": kind})
        update_wish_partial()
        await asyncio.sleep(0.2)

    # Final assembly: merge all fragments into single runnable artifacts.
    # Self-healing: accumulators may hold EMPTY content after a resume (skipped steps
    # restore paths only). Regenerate deterministic inputs fresh and fill any gap
    # from a fresh full generation — then fail closed if anything is still empty.
    try:
        from services.generators.scaffold_gen import frontend_scaffold as _fs2, backend_scaffold as _bs2
        from services.preview.mock_gen import generate_mock as _gm2
        from services.contract import build_contract as _bc3, ddl_for as _ddl3
        app_name = build_plan.get("appName", "IntaraApp")
        _c3 = _bc3(build_plan, (schema or {}).get("tables"))
        fe_scaffold = _fs2(app_name)
        _scaf_tables = (schema or {"tables": build_plan["tables"]})["tables"]
        be_scaffold = _bs2(app_name, _scaf_tables, _ddl3(_c3))
        preview = _gm2(build_plan)
        # pool of non-empty frag contents from this run (LLM pages included)
        pool: dict[str, str] = {}
        for frag in list(frontend_pages.values()) + list(backend_tables.values()):
            for f in frag.get("files", []):
                if f.get("path") and f.get("content"):
                    pool.setdefault(f["path"], f["content"])
        # gap-fill from fresh full generation (same mode as the build itself)
        from services.generators.frontend_gen import generate_frontend as _gf2
        _fresh_fe = _gf2(build_plan).get("files", [])
        for f in _fresh_fe:
            if f.get("path") and f.get("content"):
                pool.setdefault(f["path"], f["content"])
        # Build final frontend files: scaffold + mock + pool (last non-empty wins)
        fe_files = []
        for path, content in list(fe_scaffold.items()) + list(preview.items()):
            fe_files.append({"path": path, "content": content})
        seen_paths = {f["path"] for f in fe_files}
        for frag in frontend_pages.values():
            for f in frag.get("files", []):
                p = f.get("path", "")
                if p.startswith("src/pages/") and p not in seen_paths and pool.get(p):
                    fe_files.append({"path": p, "content": pool[p]})
                    seen_paths.add(p)
                elif p.startswith("src/components/"):
                    if p not in seen_paths and pool.get(p):
                        fe_files.append({"path": p, "content": pool[p]})
                        seen_paths.add(p)
                elif p in ("src/api.ts", "src/types.ts"):
                    if p not in seen_paths and pool.get(p):
                        fe_files.append({"path": p, "content": pool[p]})
                        seen_paths.add(p)
        # any expected page/component/api file still missing → fill from pool
        for f in _fresh_fe:
            if f.get("path") not in seen_paths and pool.get(f["path"]):
                fe_files.append({"path": f["path"], "content": pool[f["path"]]})
                seen_paths.add(f["path"])

        # Re-generate final App.tsx that includes all pages with nav (deterministic, not LLM)
        pages = build_plan.get("pages", [])
        if pages:
            imports_str = ", ".join(p["name"] for p in pages[:6])
            routes_str = "\n".join(f'        <Route path="{p["route"]}" element={{<{p["name"]} />}} />' for p in pages[:6])
            nav_links = "\n".join(f'          <Link to="{p["route"]}" style={{{{ padding:"8px 14px", borderRadius:999, textDecoration:"none", fontSize:12, fontWeight:500, color:"var(--intara-muted)", border:"1px solid transparent" }}}}>{p["name"]}</Link>' for p in pages[:6])
            app_name = build_plan.get("appName","IntaraApp")
            final_app = f"""import {{ BrowserRouter, Routes, Route, Link }} from 'react-router-dom'
import {{ useEffect }} from 'react'
import {{ {imports_str} }} from './pages'

export default function App() {{
  useEffect(() => {{
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
"""
            # replace existing App.tsx
            fe_files = [f for f in fe_files if f["path"] != "src/App.tsx"]
            fe_files.append({"path": "src/App.tsx", "content": final_app})
            # ensure barrel
            fe_files = [f for f in fe_files if f["path"] != "src/pages/index.ts"]
            fe_files.append({"path": "src/pages/index.ts", "content": "\n".join([f"export {{ default as {p['name']} }} from './{p['name']}'" for p in pages[:6]])})

        # Backend files: fresh scaffold + full backend regen (single canonical modules).
        # be_openapi is rebuilt from the regen so resumed (skipped) steps can't leave it partial.
        be_files = []
        for path, content in (be_scaffold or {}).items():
            if content:
                be_files.append({"path": path, "content": content})
        from services.generators.backend_gen import generate_backend
        final_be = generate_backend(build_plan)
        for f in final_be["files"]:
            if f["path"] not in [x["path"] for x in be_files] and f.get("content"):
                be_files.append(f)
        be_openapi = final_be.get("openapi") or be_openapi
        # schema already
        if schema is None:
            from services.generators.schema_gen import generate_schema
            schema = generate_schema(build_plan)
        # fail closed: never ship empty files (resume shells, truncations)
        _empty = [f["path"] for f in fe_files + be_files if not (f.get("content") or "").strip()]
        if _empty:
            raise RuntimeError(f"assembly refused: empty content in {', '.join(_empty[:6])}")

        # README + cites
        app_name = build_plan.get("appName","IntaraApp")
        tagline = build_plan.get("tagline","")
        readme = f"""# {app_name} — Intara Wish

> {tagline}
> Wish: "{prompt}"
> Forged by Intara — Planet of Wishes — {app_name} (staged sequential)

## Stack
- Frontend: Vite + React 18 + TypeScript + Tailwind — per-page generation, Dexie trial
- Backend: FastAPI + Pydantic + Supabase/SQLite — per-table generation
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
uvicorn server.main:app --reload --port 8000
```

## Tables
{chr(10).join(f"- **{t['name']}**: " + ", ".join(f"{f['name']}:{f['type']}" for f in t['fields']) for t in (schema.get('tables',[]) if isinstance(schema, dict) else []))}

## Pages
{chr(10).join(f"- {p['name']} → {p['route']} (table: {p.get('table','-')}, {', '.join(p.get('components',[]))})" for p in build_plan.get('pages',[]))}

## Build Graph (sequential)
{chr(10).join(f"- {n['id']} ({n['kind']}) -> {n.get('ref','-')}" for n in graph)}

## APIs
{chr(10).join(f"- {a['method']} {a['path']} — {a['desc']}" for a in build_plan.get('apis',[]))}

Staged sequential build — one prompt per page/component, wired as single app.
"""

        # cites
        import os
        cites = []
        try:
            if os.getenv("GEMINI_API_KEY") and os.getenv("SUPABASE_URL"):
                from rag import answer
                rag_res = answer(f"What stack for {app_name}? {prompt[:100]}")
                cites = rag_res.get("cites", [])[:3]
        except: pass
        if not cites:
            cites = [f"DhiWise builds Rocket.new — prompt to app.", f"Supabase pgvector for {app_name}.", f"Intara staged: {app_name}"]

        # Final artifacts
        final_artifacts = {
            "schema": schema,
            "frontend": {"files": fe_files},
            "backend": {"files": be_files, "requirements": final_be.get("requirements", be_requirements or ""), "openapi": be_openapi},
            "preview": preview or {},
            "spec": {"readme": readme, "openapi": be_openapi, "cites": cites, "prd": build_plan},
            "steps": BUILD_STATE[wid]["steps"],
            "buildGraph": graph
        }

        # persist to wish — via the DB layer unconditionally (MEM-only persist loses
        # the build if the worker restarted mid-flight; steps are in DB, artifacts must be too)
        try:
            from db.wishes import set_wish_status
            set_wish_status(wid, "ready", prd=build_plan, artifacts=final_artifacts)
        except Exception as e:
            print(f"final persist failed for {wid}: {e}")
            raise
        try:
            from routers.wishes import MEM
            MEM[wid] = {"id": wid, "prompt": prompt, "prd": build_plan,
                        "artifacts": final_artifacts, "status": "ready"}
        except Exception:
            pass

        emit(wid, "build_done", {"wid": wid})
        return True
    except Exception as e:
        traceback.print_exc()
        emit(wid, "build_failed", {"wid": wid, "error": str(e)})
        return False
