"""
Intara — Wishes Router
POST /api/wish {prompt} -> wish with prd + artifacts
GET /api/wish/:id
GET /api/wishes
POST /api/wish/:id/regenerate
"""
import os, uuid, time, json, asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from auth import require_user, uid, assert_owner
from quotas import consume_build

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
    key = os.getenv("SUPABASE_SERVICE_KEY","") or os.getenv("SUPABASE_KEY","")
    if not url or not key:
        return None
    try:
        from db.wishes import _client
        return _client()
    except Exception:
        return None

def _load_owned(wid: str, user: dict) -> dict:
    """Load a wish from DB (MEM fallback) and enforce owner-only access."""
    try:
        from db.wishes import get_wish_with_steps
        wish = get_wish_with_steps(wid)
        MEM[wid] = wish
    except Exception as e:
        if wid in MEM:
            wish = MEM[wid]
        else:
            raise HTTPException(404 if "not found" in str(e).lower() else 500, str(e))
    assert_owner(wish, user)
    return wish

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
                supa.table("wishes").insert({"id": wid, "prompt": prompt, "prd": prd, "artifacts": artifacts, "status": "ready", "owner": owner}).execute()
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

def _plan_progress(wid: str, phase: str | None, label: str = ""):
    """Publish planning progress to DB (polling) + SSE (live). Best-effort, never raises."""
    try:
        from db.wishes import get_wish_with_steps, set_wish_status
        wish = get_wish_with_steps(wid)
        artifacts = wish.get("artifacts") or {}
        artifacts["plan_phase"] = {"phase": phase, "label": label} if phase else None
        set_wish_status(wid, wish.get("status", "planning"), artifacts=artifacts)
    except Exception as e:
        print(f"plan progress DB snapshot failed for {wid}: {e}")
    try:
        from services.orchestrator import emit
        emit(wid, "plan_phase", {"phase": phase, "label": label})
    except Exception:
        pass
    try:
        if wid in MEM:
            arts = MEM[wid].get("artifacts") or {}
            arts["plan_phase"] = {"phase": phase, "label": label} if phase else None
            MEM[wid]["artifacts"] = arts
    except Exception:
        pass


def _planning_shell(prompt: str, clarify: dict | None = None):
    """Empty PRD shell shown instantly while the background plan task works."""
    clarify = clarify or {}
    return {
        "appName": "Draft", "tagline": prompt[:120],
        "tables": [], "pages": [], "apis": [], "auth": False,
        "requirements": {"functional": [], "nonFunctional": []},
        "ia": {"entities": [], "relations": [], "nav": []},
        "buildGraph": [],
        "clarify": {k: v for k, v in clarify.items() if not k.startswith("_")} if clarify else {"pending": True},
        "_meta": {"source": (clarify.get("_meta", {}) or {}).get("source", "clarify") if clarify else "shell", "analyzer": False},
    }


def make_plan_shell(prompt: str, owner=None):
    """Fast sync half of POST /wish/plan: insert shell row, return it. No LLM."""
    from db.wishes import create_wish_tx
    wish = create_wish_tx(prompt, _planning_shell(prompt), status="planning", owner=owner)
    MEM[wish["id"]] = wish
    return wish


async def _run_plan_task(wid: str, prompt: str, answers: dict | None = None, skip_clarify: bool = False):
    """Background half of POST /wish/plan: clarify → plan → promote shell. Fail-closed.

    Blocking LLM work runs in worker threads with a hard timeout so the event
    loop stays responsive (page loads, polls, chat) while planning.
    """
    def _plan_timeout() -> float:
        try:
            return float(os.getenv("STEP_TIMEOUT_SECONDS", "600"))
        except Exception:
            return 600.0

    async def _blocking(label: str, fn, *args):
        try:
            return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=_plan_timeout())
        except asyncio.TimeoutError:
            raise RuntimeError(f"{label} timed out after {int(_plan_timeout())}s")

    try:
        from services.planner_v2 import plan_build
        from services.prompt_enhance import clarify_prompt, redraft_prompt, READY_THRESHOLD
        from db.wishes import get_wish_with_steps, set_wish_status, promote_shell_to_plan
        _plan_progress(wid, "clarifying", "Asking two quick questions…")
        clarify = None
        effective = prompt
        if answers:
            # User already answered clarifying questions: fold in, then plan
            effective = redraft_prompt(prompt, answers)
            clarify = {"answers": answers, "redrafted": effective}
        elif not skip_clarify:
            # Clarify-first: one advisory call (never 429s — degrades to templates)
            clarify = await _blocking("clarify", clarify_prompt, prompt)
            if clarify.get("score", 0) < READY_THRESHOLD:
                shell = _planning_shell(prompt, clarify)
                set_wish_status(wid, "planning", prd=shell)
                try:
                    MEM[wid] = get_wish_with_steps(wid)
                except Exception:
                    pass
                _plan_progress(wid, None)
                try:
                    from services.orchestrator import emit
                    emit(wid, "plan_ready", {"wid": wid, "status": "planning"})
                except Exception:
                    pass
                return
        _plan_progress(wid, "drafting_tables", "Drafting tables…")
        build_plan = await _blocking("plan", plan_build, effective)
        _plan_progress(wid, "drafting_pages", "Drafting pages…")
        if clarify:
            build_plan.setdefault("_meta", {})["clarify"] = clarify if answers else {k: v for k, v in clarify.items() if not k.startswith("_")}
        # Background path always lands on approval (questions, if any, come from the
        # clarify shell branch above which returns early).
        status = "awaiting_approval"
        wish = promote_shell_to_plan(wid, build_plan, status=status)
        MEM[wid] = wish
        try:
            from components.store import record_wish_composition
            record_wish_composition(wid, build_plan)
        except Exception as e:
            print(f"composition record skipped: {e}")
        _plan_progress(wid, None)
        try:
            from services.orchestrator import emit
            emit(wid, "plan_ready", {"wid": wid, "status": status})
        except Exception:
            pass
    except HTTPException:
        raise
    except Exception as e:
        print(f"background plan failed for {wid}: {e}")
        try:
            from db.wishes import set_wish_status, get_wish_with_steps
            err = str(e)[:500]
            set_wish_status(wid, "failed")
            try:
                MEM[wid] = get_wish_with_steps(wid)
            except Exception:
                if wid in MEM:
                    MEM[wid]["status"] = "failed"
            try:
                from services.orchestrator import emit
                emit(wid, "plan_failed", {"wid": wid, "error": err})
            except Exception:
                pass
        except Exception:
            pass


@router.post("/wish/plan", status_code=202)
def create_plan(body: PlanIn, background_tasks: BackgroundTasks,
                user: dict = Depends(require_user)):
    """Fast shell + background plan: returns the wish instantly so the client can
    navigate to the chat page immediately; clarify/plan land via polling/SSE."""
    if not body.prompt or len(body.prompt.strip()) < 4:
        raise HTTPException(400, "prompt too short")
    if len(body.prompt) > 500:
        raise HTTPException(400, "prompt too long (max 500)")
    prompt = body.prompt.strip()
    try:
        wish = make_plan_shell(prompt, owner=uid(user))
    except HTTPException:
        raise
    except Exception as e:
        print(f"create_plan shell DB fail-fast: {e}")
        raise HTTPException(500, f"Supabase required for staged builds: {e}. Run supabase/migrations/002_staged_builds.sql in SQL editor. Status: {e}")
    background_tasks.add_task(_run_plan_task, wish["id"], prompt, body.answers, body.skip_clarify)
    return wish


async def _run_staged_build(wid: str):
    # background task: run orchestrator sequential — DB is source of truth, fail-fast.
    # Single-flight: concurrent tasks for one wish corrupt step state, so bail if taken.
    try:
        from services.orchestrator import BUILD_RUNNING
        if wid in BUILD_RUNNING:
            print(f"staged build already running for {wid}, skipping duplicate task")
            return
        BUILD_RUNNING.add(wid)
    except Exception:
        pass
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
            # orchestrator already flipped DB to failed via _mark_build_failed; ensure MEM
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
    finally:
        try:
            from services.orchestrator import BUILD_RUNNING as _BR
            _BR.discard(wid)
        except Exception:
            pass

@router.patch("/wish/{wid}/plan")
def patch_plan(wid: str, body: PatchPlanIn, user: dict = Depends(require_user)):
    # Fail-fast: must exist in DB and belong to the caller
    wish = _load_owned(wid, user)
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
def answer_clarify(wid: str, body: AnswerIn, user: dict = Depends(require_user)):
    """User answered clarifying questions: redraft the wish, build the plan, move to awaiting_approval."""
    wish = _load_owned(wid, user)
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
        try:
            from components.store import record_wish_composition
            record_wish_composition(wid, build_plan)
        except Exception as e:
            print(f"composition record skipped: {e}")
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
def suggest_next_steps(wid: str, user: dict = Depends(require_user)):
    """Deterministic next-step suggestions from the AppSpec (no LLM cost)."""
    wish = _load_owned(wid, user)
    from services.suggest import suggest_next
    return {"suggestions": suggest_next(wish.get("prd") or {})}

@router.get("/wish/{wid}/chat")
def get_chat(wid: str, user: dict = Depends(require_user)):
    _load_owned(wid, user)
    return {"messages": _chat_history(wid)}

@router.post("/wish/{wid}/chat")
def post_chat(wid: str, body: ChatIn, request: Request,
              user: dict = Depends(require_user)):
    msg = (body.message or "").strip()
    if len(msg) < 1:
        raise HTTPException(400, "message too short")
    if len(msg) > 1000:
        raise HTTPException(400, "message too long (max 1000)")
    ip = request.client.host if request.client else "unknown"
    check_chat_rate(ip)
    wish = _load_owned(wid, user)
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

def _load_wish_for_iterate(wid: str, user: dict):
    return _load_owned(wid, user)

@router.post("/wish/{wid}/iterate")
def preview_iterate(wid: str, body: IterateIn, request: Request,
                    user: dict = Depends(require_user)):
    """Diff-first rewrite preview: costs 1 shared-cap unit + 1-4 LLM calls. Persists nothing."""
    ins = (body.instruction or "").strip()
    if len(ins) < 1:
        raise HTTPException(400, "instruction too short")
    if len(ins) > 500:
        raise HTTPException(400, "instruction too long (max 500)")
    ip = request.client.host if request.client else "unknown"
    check_chat_rate(ip)  # shared 20/day cap with chat
    wish = _load_wish_for_iterate(wid, user)
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
def apply_iterate(wid: str, iid: str, user: dict = Depends(require_user)):
    """Accept a preview: snapshot, patch artifacts, bump step. No LLM cost."""
    from services.iterate import get_iteration, apply_iteration
    it = get_iteration(iid)
    if not it or it.get("wish_id") != wid:
        raise HTTPException(404, "iteration not found")
    wish = _load_wish_for_iterate(wid, user)
    if it.get("status") == "applied":
        return wish
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
def revert_iterate(wid: str, iid: str, user: dict = Depends(require_user)):
    """One-click undo of an applied iteration. No LLM cost."""
    from services.iterate import get_iteration, revert_iteration
    it = get_iteration(iid)
    if not it or it.get("wish_id") != wid:
        raise HTTPException(404, "iteration not found")
    wish = _load_wish_for_iterate(wid, user)
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
async def approve_plan(wid: str, background_tasks: BackgroundTasks,
                       user: dict = Depends(require_user)):
    # Fail-fast: load from DB, check status, spend one build credit, then start.
    wish = _load_owned(wid, user)
    try:
        from db.wishes import set_wish_status
        if wish.get("status") not in ("awaiting_approval", "approved", "failed"):
            raise HTTPException(400, f"cannot approve in status {wish.get('status')}")
        consume_build(user, wish_id=wid, kind="build")
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
async def stream_build(wid: str, user: dict = Depends(require_user)):
    _load_owned(wid, user)  # auth + ownership before opening the stream
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
            yield f"data: {json.dumps({'event':'snapshot','steps': steps, 'status': wish.get('status'), 'plan_phase': wish.get('artifacts',{}).get('plan_phase'), 'current_step': wish.get('current_step_id'), 'updated_at': wish.get('updated_at')})}\n\n"
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
                    if payload.get("event") in ("build_done","build_failed","plan_ready","plan_failed"):
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
async def retry_step(wid: str, body: dict, user: dict = Depends(require_user)):
    step_id = body.get("stepId")
    if not step_id:
        raise HTTPException(400, "stepId required")
    # Fail-fast: must exist in DB and belong to the caller
    wish = _load_owned(wid, user)
    try:
        from db.wishes import update_step, set_wish_status
        steps = wish.get("artifacts",{}).get("steps",{})
        if step_id not in steps and step_id not in [n["id"] for n in wish.get("prd",{}).get("buildGraph",[])]:
            raise HTTPException(404, f"step {step_id} not found")
        # Guard: refuse a second concurrent build for the same wish (two
        # run_build_sequential tasks would interleave DB writes and corrupt step state)
        try:
            from services.orchestrator import BUILD_RUNNING
            if wid in BUILD_RUNNING:
                raise HTTPException(409, "build already running for this wish — watch it land instead of double-retrying")
        except HTTPException:
            raise
        except Exception:
            pass
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
def create_wish(body: WishIn, user: dict = Depends(require_user)):
    if not body.prompt or len(body.prompt.strip()) < 4:
        raise HTTPException(400, "prompt too short — wish for something, e.g. 'A task tracker with users and tasks'")
    if len(body.prompt) > 500:
        raise HTTPException(400, "prompt too long (max 500)")
    consume_build(user, kind="one_shot")
    try:
        return make_wish(body.prompt.strip(), owner=uid(user))
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
def get_wish(wid: str, user: dict = Depends(require_user)):
    return _load_owned(wid, user)

@router.get("/wishes")
def list_wishes(user: dict = Depends(require_user)):
    owner = uid(user)
    data: list = []
    try:
        from db.wishes import list_wishes_with_steps
        data = list_wishes_with_steps(limit=50, owner=owner)
    except Exception as e:
        print(f"list_wishes DB read failed: {e}")
    # merge MEM (dev / just-created shells) — always owner-filtered
    seen = set(row["id"] for row in data)
    for v in MEM.values():
        if owner and v.get("owner") != owner:
            continue
        if v["id"] in seen:
            continue
        data.append({"id": v["id"], "prompt": v["prompt"], "prd": v["prd"], "created_at": v["created_at"], "status": v["status"], "build_graph": v.get("prd",{}).get("buildGraph",[])})
    data.sort(key=lambda x: x.get("created_at",""), reverse=True)
    return data[:50]

@router.post("/wish/{wid}/regenerate")
def regenerate(wid: str, user: dict = Depends(require_user)):
    # fetch existing prompt (ownership enforced)
    wish = _load_owned(wid, user)
    prompt = wish.get("prompt")
    if not prompt:
        raise HTTPException(404, "wish not found")
    consume_build(user, kind="regenerate")
    return make_wish(prompt, owner=uid(user))
