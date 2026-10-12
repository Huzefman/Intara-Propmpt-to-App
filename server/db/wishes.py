"""
Supabase source of truth — fail-fast, no silent MEM fallback.
All writes must succeed or raise; reads are from DB first.
"""
import os, json, time
from typing import Any, Dict, List, Optional

def _client():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL/SUPABASE_KEY — staged builds require Supabase (fail-fast)")
    from supabase import create_client
    return create_client(url, key)

def create_wish_tx(prompt: str, prd: dict, status: str = "awaiting_approval") -> dict:
    """Insert wishes + wish_steps in one logical transaction. Fail-fast."""
    wid = __import__("uuid").uuid4().__str__()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # include build_graph for quick status
    build_graph = prd.get("buildGraph", [])
    supa = _client()
    # wishes
    res = supa.table("wishes").insert({
        "id": wid,
        "prompt": prompt,
        "prd": prd,
        "artifacts": {"steps": {n["id"]: {"status": "pending"} for n in build_graph}, "buildGraph": build_graph},
        "status": status,
        "build_graph": build_graph,
        "current_step_id": None,
    }).execute()
    if not res.data:
        raise RuntimeError(f"wishes insert returned no data: {res}")
    # wish_steps — one row per DAG node with full prompt history placeholder
    steps = []
    for n in build_graph:
        # Use BUILD_PLAN_PROMPT rendered per step? For plan step, store the full BuildPlan prompt
        # For now, store promptHint as prompt; orchestrator will overwrite with full rendered prompt per step
        steps.append({
            "wish_id": wid,
            "step_id": n["id"],
            "kind": n["kind"],
            "ref": n.get("ref"),
            "status": "pending",
            "attempt": 1,
            "prompt": n.get("promptHint", ""),
            "depends_on": n.get("dependsOn", []),
        })
    if steps:
        r2 = supa.table("wish_steps").insert(steps).execute()
        if not r2.data and len(steps) > 0:
            # fail-fast: rollback wishes?
            raise RuntimeError(f"wish_steps insert failed: {r2}")
    # return canonical wish
    row = res.data[0] if isinstance(res.data, list) else res.data
    return {"id": row["id"], "prompt": row["prompt"], "prd": row["prd"], "artifacts": row["artifacts"], "status": row["status"], "created_at": row.get("created_at", now), "build_graph": build_graph}

def get_wish_with_steps(wid: str) -> Dict[str, Any]:
    supa = _client()
    try:
        w = supa.table("wishes").select("*").eq("id", wid).single().execute()
    except Exception as e:
        # PostgREST .single() on 0 rows raises PGRST116 — that's "not found", not a 500
        if "PGRST116" in str(e) or "0 rows" in str(e):
            raise RuntimeError(f"wish {wid} not found")
        raise
    if not w.data:
        raise RuntimeError(f"wish {wid} not found")
    wish = w.data
    # steps
    s = supa.table("wish_steps").select("*").eq("wish_id", wid).order("created_at").execute()
    steps = {row["step_id"]: row for row in (s.data or [])}
    # normalize artifacts.steps from DB for FE compat
    artifacts = wish.get("artifacts") or {}
    artifacts["steps"] = {sid: {"status": row["status"], "startedAt": row.get("started_at"), "endedAt": row.get("ended_at"), "error": row.get("error"), "fallback_reason": (row.get("output") or {}).get("fallback_reason")} for sid, row in steps.items()}
    artifacts["buildGraph"] = wish.get("build_graph") or wish.get("prd", {}).get("buildGraph", [])
    wish["artifacts"] = artifacts
    wish["_steps_rows"] = steps  # internal full rows
    return wish

def update_step(wid: str, step_id: str, status: Optional[str] = None, prompt: Optional[str] = None, raw_response: Optional[str] = None, output: Optional[dict] = None, error: Optional[str] = None, started_at: Optional[str] = None, ended_at: Optional[str] = None, attempt: Optional[int] = None):
    supa = _client()
    payload: Dict[str, Any] = {}
    if status is not None: payload["status"] = status
    if prompt is not None: payload["prompt"] = prompt[:20000]  # cap
    if raw_response is not None: payload["raw_response"] = raw_response[:20000]
    if output is not None: payload["output"] = output
    if error is not None: payload["error"] = error[:2000]
    if started_at is not None: payload["started_at"] = started_at
    if ended_at is not None: payload["ended_at"] = ended_at
    if attempt is not None: payload["attempt"] = attempt
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    res = supa.table("wish_steps").update(payload).eq("wish_id", wid).eq("step_id", step_id).execute()
    if not res.data:
        raise RuntimeError(f"update_step {step_id} failed: no data")
    return res.data

def set_wish_status(wid: str, status: str, current_step_id: Optional[str] = None, prd: Optional[dict] = None, artifacts: Optional[dict] = None):
    supa = _client()
    payload: Dict[str, Any] = {"status": status}
    if current_step_id is not None: payload["current_step_id"] = current_step_id
    if prd is not None: payload["prd"] = prd
    if artifacts is not None: payload["artifacts"] = artifacts
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    res = supa.table("wishes").update(payload).eq("id", wid).execute()
    if not res.data:
        raise RuntimeError(f"set_wish_status {wid}->{status} failed")
    return res.data

def list_wishes_with_steps(limit: int = 50):
    supa = _client()
    res = supa.table("wishes").select("id,prompt,prd,created_at,status,build_graph,current_step_id").order("created_at", desc=True).limit(limit).execute()
    return res.data or []

def get_steps(wid: str):
    supa = _client()
    res = supa.table("wish_steps").select("*").eq("wish_id", wid).order("created_at").execute()
    return res.data or []

def promote_shell_to_plan(wid: str, prd: dict, status: str) -> Dict[str, Any]:
    """Replace a planning shell's PRD with a finished BuildPlan + reset steps.

    Used by the background plan task (POST /wish/plan returns the shell fast).
    Mirrors PATCH /wish/{wid}/plan reset logic. Fail-fast: raises on DB error.
    """
    supa = _client()
    build_graph = prd.get("buildGraph", [])
    supa.table("wish_steps").delete().eq("wish_id", wid).execute()
    steps = []
    for n in build_graph:
        steps.append({
            "wish_id": wid,
            "step_id": n["id"],
            "kind": n["kind"],
            "ref": n.get("ref"),
            "status": "pending",
            "attempt": 1,
            "prompt": n.get("promptHint", ""),
            "depends_on": n.get("dependsOn", []),
        })
    if steps:
        r2 = supa.table("wish_steps").insert(steps).execute()
        if not r2.data:
            raise RuntimeError(f"promote_shell_to_plan steps insert failed for {wid}")
    artifacts = {
        "steps": {n["id"]: {"status": "pending"} for n in build_graph},
        "buildGraph": build_graph,
        "plan_phase": None,
    }
    res = supa.table("wishes").update({
        "prd": prd,
        "status": status,
        "artifacts": artifacts,
        "build_graph": build_graph,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }).eq("id", wid).execute()
    if not res.data:
        raise RuntimeError(f"promote_shell_to_plan wishes update failed for {wid}")
    return get_wish_with_steps(wid)
