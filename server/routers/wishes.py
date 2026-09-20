"""
Intara — Wishes Router
POST /api/wish {prompt} -> wish with prd + artifacts
GET /api/wish/:id
GET /api/wishes
POST /api/wish/:id/regenerate
"""
import os, uuid, time, json
from fastapi import APIRouter, HTTPException
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

@router.post("/wish")
@router.post("/wishes")
def create_wish(body: WishIn):
    # in real, get IP from request; for now per-process
    # check_rate("demo-ip") # disabled for free demo — uncomment to enforce
    if not body.prompt or len(body.prompt.strip()) < 4:
        raise HTTPException(400, "prompt too short — wish for something, e.g. 'A task tracker with users and tasks'")
    if len(body.prompt) > 500:
        raise HTTPException(400, "prompt too long (max 500)")
    try:
        return make_wish(body.prompt.strip())
    except HTTPException:
        raise
    except Exception as e:
        print(f"create_wish error: {e}")
        raise HTTPException(500, str(e))

@router.get("/wish/{wid}")
@router.get("/wishes/{wid}")
def get_wish(wid: str):
    # check MEM first (handles wishes table missing case)
    if wid in MEM:
        return MEM[wid]
    supa = get_supabase()
    if supa:
        try:
            res = supa.table("wishes").select("*").eq("id", wid).single().execute()
            if res.data:
                d = res.data
                # cache in MEM
                MEM[wid] = {"id": d["id"], "prompt": d["prompt"], "prd": d["prd"], "artifacts": d["artifacts"], "status": d.get("status","ready"), "created_at": d.get("created_at")}
                return MEM[wid]
        except Exception as e:
            print(f"get wish supabase failed: {e}")
    raise HTTPException(404, "wish not found")

@router.get("/wishes")
def list_wishes():
    # merge MEM + supabase wishes (supabase may be missing)
    mem_vals = list(MEM.values())
    supa = get_supabase()
    if supa:
        try:
            res = supa.table("wishes").select("id,prompt,prd,created_at,status").order("created_at", desc=True).limit(50).execute()
            data = res.data or []
            # merge supa + mem, dedupe by id
            seen = set()
            merged = []
            for row in data + [{"id": v["id"], "prompt": v["prompt"], "prd": v["prd"], "created_at": v["created_at"], "status": v["status"]} for v in mem_vals]:
                if row["id"] not in seen:
                    seen.add(row["id"])
                    merged.append(row)
            merged.sort(key=lambda x: x.get("created_at",""), reverse=True)
            return merged[:50]
        except Exception as e:
            print(f"list wishes supabase failed (fallback to schemas + MEM): {e}")
            # fallback to schemas + MEM
            try:
                r2 = supa.table("schemas").select("id,prompt,tables,created_at").order("created_at", desc=True).limit(20).execute()
                schemas_rows = [{"id": row["id"], "prompt": row["prompt"], "prd": {"appName": "Legacy", "tables": row["tables"]}, "created_at": row["created_at"], "status":"ready"} for row in (r2.data or [])]
                # merge with mem
                seen = set()
                merged = []
                for row in schemas_rows + [{"id": v["id"], "prompt": v["prompt"], "prd": v["prd"], "created_at": v["created_at"], "status": v["status"]} for v in mem_vals]:
                    if row["id"] not in seen:
                        merged.append(row); seen.add(row["id"])
                merged.sort(key=lambda x: x.get("created_at",""), reverse=True)
                return merged[:50]
            except Exception as e2:
                print(f"schemas fallback failed: {e2}")
    # MEM only
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
