"""
Intara — Wishes Router
POST /api/wish {prompt} -> wish with prd + artifacts
GET /api/wish/:id
GET /api/wishes
POST /api/wish/:id/regenerate
"""
import os, uuid, time, json, asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# in-memory store for demo/free-tier without supabase, fallback
MEM = {}

# simple IP rate limit: 10 per day in-memory (reset on restart — ok for demo)
RATE = {}

def check_rate(ip: str):
    now = time.time()
    # clean old (>24h)
    for k, lst in list(RATE.items()):
        RATE[k] = [t for t in lst if now - t < 86400]
    lst = RATE.get(ip, [])
    if len(lst) >= 10:
        raise HTTPException(429, "Intara is crowded — 10 wishes per day per IP. Try tomorrow or upgrade.")
    lst.append(now)
    RATE[ip] = lst

# chat rate limit: 20 per day per IP in-memory (shares the free LLM pool with builds)
CHAT_RATE = {}

def check_chat_rate(ip: str):
    now = time.time()
    for k, lst in list(CHAT_RATE.items()):
        CHAT_RATE[k] = [t for t in lst if now - t < 86400]
    lst = CHAT_RATE.get(ip, [])
    if len(lst) >= 20:
        raise HTTPException(429, "Chat stardust spent — 20 chats per day per IP (builds share the same free pool). Back tomorrow.")
    lst.append(now)
    CHAT_RATE[ip] = lst

class ChatIn(BaseModel):
    message: str

def _chat_store(wid: str, role: str, content: str):
    """Persist one chat turn; fail-open (table missing → session-only)."""
    try:
        from db.wishes import _client
        _client().table("wish_messages").insert({"wish_id": wid, "role": role, "content": content}).execute()
    except Exception as e:
        print(f"chat persist skipped: {e}")

def _chat_history(wid: str, limit: int = 20) -> list[dict]:
    try:
        from db.wishes import _client
        res = _client().table("wish_messages").select("role,content,created_at").eq("wish_id", wid).order("created_at").limit(limit).execute()
        return res.data or []
    except Exception as e:
        print(f"chat history skipped: {e}")
        return []

class WishIn(BaseModel):
    prompt: str

def get_supabase():
    url = os.getenv("SUPABASE_URL","")
    key = os.getenv("SUPABASE_KEY","")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except: return None

def make_wish(prompt: str, owner=None):
    from services.planner import plan_wish
    from services.assembler import assemble
    prd = plan_wish(prompt)
    artifacts = assemble(prd, prompt)
    wid = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    wish = {"id": wid, "prompt": prompt, "prd": prd, "artifacts": artifacts, "status": "ready", "created_at": now, "owner": owner}
    # always keep in MEM for fast retrieval (handles wishes table missing)
    MEM[wid] = wish
    # also persist to supabase if available
    supa = get_supabase()
    if supa:
        try:
            # try wishes table, fallback to schemas for backward compat
            try:
                supa.table("wishes").insert({"id": wid, "prompt": prompt, "prd": prd, "artifacts": artifacts, "status": "ready"}).execute()
            except Exception as e:
                print(f"wishes insert failed, trying schemas: {e}")
                supa.table("schemas").insert({"prompt": prompt, "tables": prd.get("tables", [])}).execute()
        except Exception as e:
            print(f"supabase persist failed: {e}")
    return wish

# --- Staged sequential build helpers ---
class PlanIn(BaseModel):
    prompt: str
    answers: dict | None = None
    skip_clarify: bool = False

class PatchPlanIn(BaseModel):
    prd: dict

class AnswerIn(BaseModel):
    answers: dict

def make_plan(prompt: str, owner=None, answers: dict | None = None, skip_clarify: bool = False):
    from services.planner_v2 import plan_build
    from services.prompt_enhance import clarify_prompt, redraft_prompt, READY_THRESHOLD
    # Fail-fast: Supabase is required for staged builds (normalized steps)
    try:
        from db.wishes import create_wish_tx
        clarify = None
        effective = prompt
        if answers:
            # User already answered clarifying questions: fold in, then plan
            effective = redraft_prompt(prompt, answers)
            clarify = {"answers": answers, "redrafted": effective}
        elif not skip_clarify:
            # Clarify-first: one advisory call (never 429s — degrades to templates)
            clarify = clarify_prompt(prompt)
            if clarify.get("score", 0) < READY_THRESHOLD:
                # Persist a clarifying shell (empty buildGraph) so answers can resume it
                shell = {
                    "appName": "Draft", "tagline": prompt[:120],
                    "tables": [], "pages": [], "apis": [], "auth": False,
                    "requirements": {"functional": [], "nonFunctional": []},
                    "ia": {"entities": [], "relations": [], "nav": []},
                    "buildGraph": [],
                    "clarify": {k: v for k, v in clarify.items() if not k.startswith("_")},
                    "_meta": {"source": clarify.get("_meta", {}).get("source", "clarify"), "analyzer": False},
                }
                wish = create_wish_tx(prompt, shell, status="planning")
                MEM[wish["id"]] = wish
                return wish
        build_plan = plan_build(effective)
        if clarify:
            build_plan.setdefault("_meta", {})["clarify"] = clarify if answers else {k: v for k, v in clarify.items() if not k.startswith("_")}
        wish = create_wish_tx(prompt, build_plan, status="awaiting_approval")
        # also cache in MEM for fast read-through (but source of truth is DB)
        MEM[wish["id"]] = wish
        return wish
    except HTTPException:
        raise
    except Exception as e:
        # Surface DB error to caller (fail-fast, no silent MEM)
        print(f"make_plan DB fail-fast: {e}")
        raise HTTPException(500, f"Supabase required for staged builds: {e}. Run supabase/migrations/002_staged_builds.sql in SQL editor. Status: {e}")

async def _run_staged_build(wid: str):
    # background task: run orchestrator sequential — DB is source of truth, fail-fast
    try:
        from services.orchestrator import run_build_sequential
        from db.wishes import get_wish_with_steps, set_wish_status
        # load from DB (fail-fast if not found or DB down)
        wish = get_wish_with_steps(wid)
        # update DB status to building (fail-fast)
        set_wish_status(wid, "building", current_step_id=wish.get("prd",{}).get("buildGraph",[{}])[0].get("id") if wish.get("prd",{}).get("buildGraph") else None)
        # also update MEM cache
        MEM[wid] = wish
        MEM[wid]["status"] = "building"
        ok = await run_build_sequential(wid, wish["prd"], wish["prompt"])
        # run_build_sequential now persists final status itself via DB layer; just ensure MEM reflects
        try:
            final = get_wish_with_steps(wid)
            MEM[wid] = final
        except: pass
        if not ok:
            # orchestrator already set failed, ensure MEM
            try:
                MEM[wid]["status"] = "failed"
            except: pass
    except Exception as e:
        print(f"staged build failed for {wid}: {e}")
        try:
            from db.wishes import set_wish_status
            set_wish_status(wid, "failed")
            if wid in MEM:
                MEM[wid]["status"] = "failed"
        except: pass
        # surface via orchestrator emit already

@router.post("/wish/plan")
def create_plan(body: PlanIn):
    if not body.prompt or len(body.prompt.strip()) < 4:
        raise HTTPException(400, "prompt too short")
    if len(body.prompt) > 500:
        raise HTTPException(400, "prompt too long (max 500)")
    try:
        return make_plan(body.prompt.strip(), answers=body.answers, skip_clarify=body.skip_clarify)
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)
        if "429" in msg or "quota" in msg.lower():
            raise HTTPException(429, f"Gemini quota hit (20/day free). Retry in ~30s or try a smaller prompt. Details: {msg[:300]}")
        print(f"create_plan error: {e}")
        raise HTTPException(500, str(e))

@router.patch("/wish/{wid}/plan")
def patch_plan(wid: str, body: PatchPlanIn):
    # Fail-fast: must exist in DB
    try:
        from db.wishes import get_wish_with_steps, set_wish_status
        wish = get_wish_with_steps(wid)
    except Exception as e:
        raise HTTPException(404 if "not found" in str(e).lower() else 500, str(e))
    prd = body.prd
    if "appName" not in prd or "tables" not in prd:
        raise HTTPException(400, "prd must have appName and tables")
    if "buildGraph" not in prd:
        from services.planner_v2 import mock_build_plan
        tmp = mock_build_plan(wish["prompt"])
        prd["buildGraph"] = tmp["buildGraph"]
        prd["requirements"] = prd.get("requirements", tmp["requirements"])
        prd["ia"] = prd.get("ia", tmp["ia"])
    # Update DB: new prd + reset steps to pending, status awaiting_approval
    try:
        from db.wishes import set_wish_status, _client
        # Update wishes row
        supa = _client()
        # reset steps: delete old, insert new pending
        supa.table("wish_steps").delete().eq("wish_id", wid).execute()
        # insert new steps with prompt from buildGraph
        steps = []
        for n in prd.get("buildGraph", []):
            steps.append({"wish_id": wid, "step_id": n["id"], "kind": n["kind"], "ref": n.get("ref"), "status": "pending", "prompt": n.get("promptHint",""), "depends_on": n.get("dependsOn",[])})
        if steps:
            supa.table("wish_steps").insert(steps).execute()
        supa.table("wishes").update({"prd": prd, "status": "awaiting_approval", "artifacts": {"steps": {n["id"]: {"status":"pending"} for n in prd.get("buildGraph",[])}, "buildGraph": prd.get("buildGraph",[])}, "build_graph": prd.get("buildGraph",[])}).eq("id", wid).execute()
        # refresh cache
        MEM[wid] = get_wish_with_steps(wid)
        return MEM[wid]
    except Exception as e:
        raise HTTPException(500, f"patch plan DB failed: {e}")

@router.post("/wish/{wid}/answer")
def answer_clarify(wid: str, body: AnswerIn):
    """User answered clarifying questions: redraft the wish, build the plan, move to awaiting_approval."""
    try:
        from db.wishes import get_wish_with_steps
        wish = get_wish_with_steps(wid)
    except Exception as e:
        raise HTTPException(404 if "not found" in str(e).lower() else 500, str(e))
    if wish.get("status") != "planning":
        raise HTTPException(400, f"cannot answer in status {wish.get('status')}")
    try:
        from services.prompt_enhance import redraft_prompt
        from services.planner_v2 import plan_build
        prior = (wish.get("prd") or {}).get("clarify", {})
        questions = prior.get("questions", [])
        effective = redraft_prompt(wish["prompt"], body.answers, questions)
        build_plan = plan_build(effective)
        build_plan.setdefault("_meta", {})["clarify"] = {
            "score": prior.get("score"), "questions": questions,
            "answers": body.answers, "redrafted": effective,
        }
        from db.wishes import _client
        supa = _client()
        supa.table("wish_steps").delete().eq("wish_id", wid).execute()
        steps = []
        for n in build_plan.get("buildGraph", []):
            steps.append({"wish_id": wid, "step_id": n["id"], "kind": n["kind"], "ref": n.get("ref"), "status": "pending", "prompt": n.get("promptHint", ""), "depends_on": n.get("dependsOn", [])})
        if steps:
            supa.table("wish_steps").insert(steps).execute()
        supa.table("wishes").update({"prd": build_plan, "status": "awaiting_approval", "artifacts": {"steps": {n["id"]: {"status": "pending"} for n in build_plan.get("buildGraph", [])}, "buildGraph": build_plan.get("buildGraph", [])}, "build_graph": build_plan.get("buildGraph", [])}).eq("id", wid).execute()
        from db.wishes import get_wish_with_steps as _reload
        MEM[wid] = _reload(wid)
        return MEM[wid]
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)
        if "429" in msg or "quota" in msg.lower():
            raise HTTPException(429, f"LLM quota hit — answers saved, retry shortly. Details: {msg[:300]}")
        raise HTTPException(500, f"answer failed: {e}")

@router.get("/wish/{wid}/suggest")
def suggest_next_steps(wid: str):
    """Deterministic next-step suggestions from the AppSpec (no LLM cost)."""
    try:
        from db.wishes import get_wish_with_steps
        wish = get_wish_with_steps(wid)
    except Exception as e:
        raise HTTPException(404 if "not found" in str(e).lower() else 500, str(e))
    from services.suggest import suggest_next
    return {"suggestions": suggest_next(wish.get("prd") or {})}

@router.get("/wish/{wid}/chat")
def get_chat(wid: str):
    try:
        from db.wishes import get_wish_with_steps
        get_wish_with_steps(wid)
    except Exception as e:
        # MEM fallback for legacy one-shot wishes (same as get_wish); truly unknown ids still 404
        if wid not in MEM:
            raise HTTPException(404 if "not found" in str(e).lower() else 500, str(e))
    return {"messages": _chat_history(wid)}

@router.post("/wish/{wid}/chat")
def post_chat(wid: str, body: ChatIn, request: Request):
    msg = (body.message or "").strip()
    if len(msg) < 1:
        raise HTTPException(400, "message too short")
    if len(msg) > 1000:
        raise HTTPException(400, "message too long (max 1000)")
    ip = request.client.host if request.client else "unknown"
    check_chat_rate(ip)
    try:
        from db.wishes import get_wish_with_steps
        wish = get_wish_with_steps(wid)
    except Exception as e:
        # MEM fallback for legacy one-shot wishes (same as get_wish); truly unknown ids still 404
        if wid in MEM:
            wish = MEM[wid]
        else:
            raise HTTPException(404 if "not found" in str(e).lower() else 500, str(e))
    history = _chat_history(wid)
    _chat_store(wid, "user", msg)
    from services.chat import answer_chat
    try:
        result = answer_chat(wish, history + [{"role": "user", "content": msg}], msg)
    except Exception as e:
        print(f"chat failed: {e}")
        result = {"reply": "I stumbled reading the stars just now — try asking again in a few seconds.", "actions": []}
    _chat_store(wid, "agent", result.get("reply", ""))
    return {"reply": result.get("reply", ""), "actions": result.get("actions", []), "degraded": bool(result.get("degraded"))}

class IterateIn(BaseModel):
    instruction: str
    stepId: str | None = None

def _load_wish_for_iterate(wid: str):
    try:
        from db.wishes import get_wish_with_steps
        return get_wish_with_steps(wid)
    except Exception as e:
        if wid in MEM:
            return MEM[wid]
        raise HTTPException(404 if "not found" in str(e).lower() else 500, str(e))

@router.post("/wish/{wid}/iterate")
def preview_iterate(wid: str, body: IterateIn, request: Request):
    """Diff-first rewrite preview: costs 1 shared-cap unit + 1-4 LLM calls. Persists nothing."""
    ins = (body.instruction or "").strip()
    if len(ins) < 1:
        raise HTTPException(400, "instruction too short")
    if len(ins) > 500:
        raise HTTPException(400, "instruction too long (max 500)")
    ip = request.client.host if request.client else "unknown"
    check_chat_rate(ip)  # shared 20/day cap with chat
    wish = _load_wish_for_iterate(wid)
    from services.iterate import resolve_step, preview_iteration, store_preview, _is_quota_msg
    try:
        node = resolve_step(wish, (body.stepId or "").strip() or None, ins)
    except RuntimeError as e:
        if _is_quota_msg(str(e)):
            raise HTTPException(429, str(e))
        raise HTTPException(500, str(e)[:500])
    if not node:
        if body.stepId:
            raise HTTPException(404, f"step {body.stepId} not found")
        raise HTTPException(400, "could not map that to a build step — name a page or table (e.g. 'fix the Tasks page')")
    try:
        prev = preview_iteration(wish, wid, node, ins)
    except RuntimeError as e:
        msg = str(e)
        if msg.startswith("429"):
            raise HTTPException(429, msg[3:].strip())
        raise HTTPException(500, msg[:500])
    iid = store_preview(wid, prev["step_id"], ins, prev["files"])
    _chat_store(wid, "user", f"[iterate] {ins}")
    _chat_store(wid, "agent", f"Previewed change — {prev['summary']}. Accept to apply.")
    return {"iteration_id": iid, "step_id": prev["step_id"], "files": prev["files"], "summary": prev["summary"]}

@router.post("/wish/{wid}/iterate/{iid}/apply")
def apply_iterate(wid: str, iid: str):
    """Accept a preview: snapshot, patch artifacts, bump step. No LLM cost."""
    from services.iterate import get_iteration, apply_iteration
    it = get_iteration(iid)
    if not it or it.get("wish_id") != wid:
        raise HTTPException(404, "iteration not found")
    if it.get("status") == "applied":
        return _load_wish_for_iterate(wid)
    wish = _load_wish_for_iterate(wid)
    try:
        fresh = apply_iteration(wish, wid, it)
    except RuntimeError as e:
        raise HTTPException(400, str(e)[:500])
    except Exception as e:
        raise HTTPException(500, f"apply failed: {e}")
    MEM[wid] = fresh
    _chat_store(wid, "agent", f"Applied change to {it.get('step_id')} — {len(it.get('files_changed') or [])} file(s). Revert available.")
    return fresh

@router.post("/wish/{wid}/iterate/{iid}/revert")
def revert_iterate(wid: str, iid: str):
    """One-click undo of an applied iteration. No LLM cost."""
    from services.iterate import get_iteration, revert_iteration
    it = get_iteration(iid)
    if not it or it.get("wish_id") != wid:
        raise HTTPException(404, "iteration not found")
    wish = _load_wish_for_iterate(wid)
    try:
        fresh = revert_iteration(wish, wid, it)
    except RuntimeError as e:
        raise HTTPException(400, str(e)[:500])
    except Exception as e:
        raise HTTPException(500, f"revert failed: {e}")
    MEM[wid] = fresh
    _chat_store(wid, "agent", f"Reverted change to {it.get('step_id')}.")
    return fresh

@router.post("/wish/{wid}/approve")
async def approve_plan(wid: str, background_tasks: BackgroundTasks):
    # Fail-fast: load from DB, check status, set to building in DB before background task
    try:
        from db.wishes import get_wish_with_steps, set_wish_status
        wish = get_wish_with_steps(wid)
        if wish.get("status") not in ("awaiting_approval", "approved", "failed"):
            raise HTTPException(400, f"cannot approve in status {wish.get('status')}")
        set_wish_status(wid, "building", current_step_id=wish.get("prd",{}).get("buildGraph",[{}])[0].get("id") if wish.get("prd",{}).get("buildGraph") else None)
        # update MEM cache
        MEM[wid] = wish
        MEM[wid]["status"] = "building"
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"approve DB failed: {e}")
    background_tasks.add_task(_run_staged_build, wid)
    return {"ok": True, "status": "building", "wid": wid}

@router.get("/wish/{wid}/stream")
async def stream_build(wid: str):
    from services.orchestrator import SSE_QUEUES, BUILD_STATE
    # DB is source of truth; SSE is live, but snapshot comes from DB
    async def event_gen():
        # snapshot from DB (fail-fast: if wish not found, error)
        try:
            from db.wishes import get_wish_with_steps
            wish = get_wish_with_steps(wid)
            steps = wish.get("artifacts",{}).get("steps",{})
            # fallback to BUILD_STATE if DB steps empty but in-memory has more
            if not steps and wid in BUILD_STATE:
                steps = BUILD_STATE[wid]["steps"]
            yield f"data: {json.dumps({'event':'snapshot','steps': steps, 'status': wish.get('status')})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event':'error','error': str(e)})}\n\n"
            return
        q: asyncio.Queue = asyncio.Queue()
        if wid not in SSE_QUEUES:
            SSE_QUEUES[wid] = []
        SSE_QUEUES[wid].append(q)
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=2.0)
                    yield f"data: {json.dumps(payload)}\n\n"
                    if payload.get("event") in ("build_done","build_failed"):
                        break
                except asyncio.TimeoutError:
                    # poll DB for status (fail-fast, but don't crash stream)
                    try:
                        from db.wishes import get_wish_with_steps
                        wish = get_wish_with_steps(wid)
                        if wish.get("status") in ("ready","failed"):
                            yield f"data: {json.dumps({'event':'heartbeat','status': wish.get('status')})}\n\n"
                            # check if all steps done in DB
                            steps = wish.get("artifacts",{}).get("steps",{})
                            if steps and all(v.get("status") in ("done","failed") for v in steps.values()):
                                break
                            if wid in BUILD_STATE and BUILD_STATE[wid]["steps"]:
                                if all(v["status"] in ("done","failed") for v in BUILD_STATE[wid]["steps"].values()):
                                    break
                        else:
                            yield f": heartbeat\n\n"
                    except:
                        yield f": heartbeat\n\n"
        finally:
            try: SSE_QUEUES[wid].remove(q)
            except: pass

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={"Cache-Control":"no-cache","Connection":"keep-alive"})

@router.post("/wish/{wid}/retry")
async def retry_step(wid: str, body: dict):
    step_id = body.get("stepId")
    if not step_id:
        raise HTTPException(400, "stepId required")
    # Fail-fast: must exist in DB
    try:
        from db.wishes import get_wish_with_steps, update_step, set_wish_status
        wish = get_wish_with_steps(wid)
        steps = wish.get("artifacts",{}).get("steps",{})
        if step_id not in steps and step_id not in [n["id"] for n in wish.get("prd",{}).get("buildGraph",[])]:
            raise HTTPException(404, f"step {step_id} not found")
        # reset step in DB
        update_step(wid, step_id, status="pending", error=None, attempt=(steps.get(step_id,{}).get("attempt",1)+1 if isinstance(steps.get(step_id),dict) else 1))
        set_wish_status(wid, "building", current_step_id=step_id)
        # also update MEM cache
        if wid in MEM:
            MEM[wid]["status"] = "building"
        # trigger rebuild (will resume from pending steps)
        asyncio.create_task(_run_staged_build(wid))
        return {"ok": True, "retrying": step_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"retry DB failed: {e}")

@router.post("/wish")
@router.post("/wishes")
def create_wish(body: WishIn):
    if not body.prompt or len(body.prompt.strip()) < 4:
        raise HTTPException(400, "prompt too short — wish for something, e.g. 'A task tracker with users and tasks'")
    if len(body.prompt) > 500:
        raise HTTPException(400, "prompt too long (max 500)")
    try:
        return make_wish(body.prompt.strip())
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)
        if "429" in msg or "quota" in msg.lower():
            raise HTTPException(429, f"Gemini quota hit (20/day free). Retry in ~30s. Details: {msg[:300]}")
        print(f"create_wish error: {e}")
        raise HTTPException(500, str(e))

@router.get("/wish/{wid}")
@router.get("/wishes/{wid}")
def get_wish(wid: str):
    # DB is source of truth for staged (fail-fast), MEM is cache for one-shot legacy
    try:
        from db.wishes import get_wish_with_steps
        wish = get_wish_with_steps(wid)
        MEM[wid] = wish  # cache
        return wish
    except Exception as e:
        # Fallback to MEM for legacy one-shot wishes created before migration (no DB row)
        if wid in MEM:
            return MEM[wid]
        # Also try legacy supabase direct for backward compat if DB layer failed due to table missing
        # but staged should have failed earlier, so surface error for staged
        msg = str(e).lower()
        if "not found" in msg or "pgrst" in msg:
            if wid in MEM:
                return MEM[wid]
        print(f"get_wish DB fail-fast: {e}")
        raise HTTPException(404 if "not found" in msg else 500, str(e))

@router.get("/wishes")
def list_wishes():
    # DB source of truth for staged, MEM cache for one-shot legacy
    try:
        from db.wishes import list_wishes_with_steps
        data = list_wishes_with_steps(limit=50)
        # merge with MEM for legacy wishes not yet in DB (one-shot created before migration)
        mem_vals = list(MEM.values())
        # dedupe
        seen = set(row["id"] for row in data)
        for v in mem_vals:
            if v["id"] not in seen:
                data.append({"id": v["id"], "prompt": v["prompt"], "prd": v["prd"], "created_at": v["created_at"], "status": v["status"], "build_graph": v.get("prd",{}).get("buildGraph",[])})
        data.sort(key=lambda x: x.get("created_at",""), reverse=True)
        return data[:50]
    except Exception as e:
        print(f"list_wishes DB fail-fast (fallback to MEM+schemas for backward compat): {e}")
        # Fallback to MEM+schemas for backward compat when DB not migrated yet (staged will have failed earlier, but list should still work)
        mem_vals = list(MEM.values())
        supa = get_supabase()
        if supa:
            try:
                r2 = supa.table("schemas").select("id,prompt,tables,created_at").order("created_at", desc=True).limit(20).execute()
                schemas_rows = [{"id": row["id"], "prompt": row["prompt"], "prd": {"appName": "Legacy", "tables": row["tables"]}, "created_at": row["created_at"], "status":"ready"} for row in (r2.data or [])]
                seen = set()
                merged = []
                for row in schemas_rows + [{"id": v["id"], "prompt": v["prompt"], "prd": v["prd"], "created_at": v["created_at"], "status": v["status"]} for v in mem_vals]:
                    if row["id"] not in seen:
                        merged.append(row); seen.add(row["id"])
                merged.sort(key=lambda x: x.get("created_at",""), reverse=True)
                return merged[:50]
            except: pass
        mem_vals.sort(key=lambda x: x["created_at"], reverse=True)
        return [{"id": v["id"], "prompt": v["prompt"], "prd": v["prd"], "created_at": v["created_at"], "status": v["status"]} for v in mem_vals[:50]]

@router.post("/wish/{wid}/regenerate")
def regenerate(wid: str):
    # fetch existing prompt
    supa = get_supabase()
    prompt = None
    if supa:
        try:
            res = supa.table("wishes").select("prompt").eq("id", wid).single().execute()
            if res.data: prompt = res.data["prompt"]
        except: pass
    if not prompt and wid in MEM:
        prompt = MEM[wid]["prompt"]
    if not prompt:
        raise HTTPException(404, "wish not found")
    return make_wish(prompt)
