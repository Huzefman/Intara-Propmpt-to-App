"""
v2 runs API (Phase 7, P7.1/P7.4): start/status/SSE/approve/chat-patch.

Build runs execute in background tasks (in-process worker v1); iterate
(chat-patch) runs inline — one LLM call, bounded. Projects + runs +
versions live in the 006 control-plane tables (service key); events stream
as SSE v2 (history first, then live tail until the run is terminal).
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import require_user, is_dev, uid
from quotas import consume_build

router = APIRouter()


def _engine():
    from services.run_engine import get_engine
    return get_engine()


def _assert_project_owner(store, project_id: str | None, user: dict) -> None:
    """404 for outsiders — never reveal that another account's project exists."""
    if is_dev(user):
        return
    if not project_id:
        raise HTTPException(404, "not found")
    try:
        if hasattr(store, "supa"):
            rows = (store.supa.table("projects").select("owner_id")
                    .eq("id", project_id).limit(1).execute().data or [])
            owner = rows[0].get("owner_id") if rows else None
        else:
            owner = None  # MemoryRunStore is test/dev only
    except Exception:
        raise HTTPException(404, "not found")
    if str(owner or "") != str(uid(user) or ""):
        raise HTTPException(404, "not found")


def _assert_run_owner(store, run: dict, user: dict) -> None:
    if is_dev(user):
        return
    _assert_project_owner(store, (run or {}).get("project_id"), user)


def _project_id_for_run(store, run_id: str) -> str:
    return store.get_run(run_id).get("project_id")


def _current_version(store, run_id: str) -> str | None:
    """Latest version id for a run (from run_done/approved events)."""
    vid = None
    for ev in store.get_events(run_id):
        v = (ev.get("payload") or {}).get("version")
        if ev.get("type") in ("run_done", "approved") and v:
            vid = v
    return vid


class StartIn(BaseModel):
    wish: str = ""
    kind: str = "build"
    app_name: str = "App"
    project_id: str | None = None
    requirements: list = []
    wish_id: str | None = None  # when set, run id + finished spec write back to the wish (Studio tabs)


@router.post("/runs")
@router.post("/api/runs")
async def start_run(body: StartIn, user: dict = Depends(require_user)):
    if body.kind not in ("build", "iterate", "eval"):
        raise HTTPException(400, f"bad kind {body.kind!r}")
    if body.kind == "build" and (not body.wish or len(body.wish.strip()) < 4):
        raise HTTPException(400, "wish too short")
    try:
        eng = _engine()
        store = eng.store
        project_id = body.project_id
        if project_id:
            _assert_project_owner(store, project_id, user)
        if body.wish_id:
            # A run may write artifacts back into its wish: never let an account
            # point that at someone else's wish id.
            if not hasattr(store, "supa"):
                raise HTTPException(400, "wish_id requires Supabase-backed runs")
            rows = (store.supa.table("wishes").select("owner")
                    .eq("id", body.wish_id).limit(1).execute().data or [])
            if not rows or (not is_dev(user) and
                            str(rows[0].get("owner") or "") != str(uid(user) or "")):
                raise HTTPException(404, "wish not found")
        # Every run start spends the shared LLM pool, whatever its kind.
        consume_build(user, wish_id=body.wish_id, kind=body.kind)
        if not project_id:
            res = store.supa.table("projects").insert(
                {"name": (body.wish.strip()[:80] or body.app_name),
                 "track": "business", "owner_id": uid(user)}).execute()
            if not res.data:
                raise RuntimeError("projects insert failed")
            project_id = res.data[0]["id"]
        inputs: dict = {"wish": body.wish.strip(), "app_name": body.app_name,
                        "requirements": body.requirements,
                        "wish_id": body.wish_id, "budgets": {},
                        "owner_id": uid(user)}
        if body.kind == "build":
            run_id = store.create_run(project_id, "build", inputs)
            store.set_status(run_id, "running")
            _writeback_wish(body.wish_id, {"v2": {"run_id": run_id}})
            asyncio.create_task(_background_run(run_id, project_id, inputs, owner=uid(user)))
            return {"ok": True, "run_id": run_id, "project_id": project_id,
                    "status": "running"}
        # iterate/eval without a base need a full build first
        raise HTTPException(400, f"start with kind=build; {body.kind} runs from a version (chat endpoint)")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"run start failed: {e}")


async def _background_run(run_id: str, project_id: str, inputs: dict, owner: str | None = None):
    try:
        from userkeys import set_current_user, snapshot_for
        set_current_user(owner)
        if owner:
            snapshot_for(owner)
    except Exception:
        pass
    try:
        eng = _engine()
        report = await eng.run(project_id=project_id, kind="build",
                               inputs=inputs, run_id=run_id)
        # Studio loop: finished spec + run link land on the wish (best-effort)
        if inputs.get("wish_id") and report.get("spec"):
            _writeback_wish(inputs["wish_id"],
                             {"v2": {"run_id": run_id,
                                     "version_id": report.get("version_id")},
                              "spec_v1": report["spec"]})
    except Exception as e:
        print(f"v2 background run {run_id} failed: {e}")
        try:
            _engine().store.set_status(run_id, "failed", str(e)[:500])
        except Exception:
            pass


def _writeback_wish(wish_id: str | None, extra_artifacts: dict) -> None:
    """Merge keys into wish artifacts without touching status (best-effort)."""
    if not wish_id:
        return
    try:
        from db.wishes import get_wish_with_steps, set_wish_status
        wish = get_wish_with_steps(wish_id)
        artifacts = dict(wish.get("artifacts") or {})
        artifacts.update(extra_artifacts)
        set_wish_status(wish_id, wish.get("status", "planning"), artifacts=artifacts)
    except Exception as e:
        print(f"v2 wish writeback failed for {wish_id}: {e}")


@router.get("/runs/{run_id}")
@router.get("/api/runs/{run_id}")
async def run_status(run_id: str, user: dict = Depends(require_user)):
    try:
        eng = _engine()
        run = eng.store.get_run(run_id)
        _assert_run_owner(eng.store, run, user)
        steps = eng.store.get_steps(run_id)
        out: dict = {"run": run, "steps": steps, "version_id": None, "spec": None,
                     "llm_calls": 0, "degraded_steps": []}
        vid = _current_version(eng.store, run_id)
        if vid:
            try:
                ver = eng.store.get_version(vid)
                out["version_id"] = vid
                out["spec"] = ver.get("spec")
            except Exception:
                pass
        try:
            for ev in eng.store.get_events(run_id):
                p = ev.get("payload") or {}
                out["llm_calls"] += int(p.get("llm_calls") or 0)
                if ev.get("type") == "step_degraded" and p.get("step"):
                    out["degraded_steps"].append(p["step"])
                if ev.get("type") == "run_done":
                    out["llm_calls"] = int(p.get("llm_calls") or out["llm_calls"])
        except Exception:
            pass
        return out
    except Exception as e:
        raise HTTPException(404 if "not found" in str(e).lower() else 500, str(e))


@router.get("/runs/{run_id}/events")
@router.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, user: dict = Depends(require_user)):
    try:
        eng = _engine()
        run = eng.store.get_run(run_id)  # 404 fast
        _assert_run_owner(eng.store, run, user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(404 if "not found" in str(e).lower() else 500, str(e))

    async def event_gen():
        eng2 = _engine()
        for ev in eng2.replay(run_id):
            yield f"data: {json.dumps(ev)}\n\n"
        q: asyncio.Queue = asyncio.Queue()
        eng2.queues.setdefault(run_id, []).append(q)
        try:
            for _ in range(600):  # ~10 min live tail
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield f"data: {json.dumps(ev)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                try:
                    if eng2.store.get_run(run_id).get("status") in (
                            "done", "degraded", "failed", "cancelled"):
                        break
                except Exception:
                    break
        finally:
            try:
                eng2.queues[run_id].remove(q)
            except Exception:
                pass

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


class ApproveIn(BaseModel):
    by: str = "owner"


@router.post("/runs/{run_id}/approve")
@router.post("/api/runs/{run_id}/approve")
async def approve_run(run_id: str, body: ApproveIn, user: dict = Depends(require_user)):
    try:
        eng = _engine()
        _assert_run_owner(eng.store, eng.store.get_run(run_id), user)
        vid = _current_version(eng.store, run_id)
        if not vid:
            raise HTTPException(409, "nothing to approve yet — run has no version")
        eng.emit(run_id, "approved", {"version": vid, "by": body.by})
        return {"ok": True, "version_id": vid}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"approve failed: {e}")


class ChatIn(BaseModel):
    instruction: str = ""
    base_version: str | None = None

@router.post("/runs/{run_id}/chat")
@router.post("/api/runs/{run_id}/chat")
async def chat_patch(run_id: str, body: ChatIn, user: dict = Depends(require_user)):
    if not body.instruction or len(body.instruction.strip()) < 4:
        raise HTTPException(400, "instruction too short")
    try:
        eng = _engine()
        _assert_run_owner(eng.store, eng.store.get_run(run_id), user)
        base_vid = body.base_version or _current_version(eng.store, run_id)
        if not base_vid:
            raise HTTPException(409, "no base version to patch yet")
        project_id = _project_id_for_run(eng.store, run_id)
        report = await eng.run(
            project_id=project_id, kind="iterate",
            inputs={"base_version": base_vid,
                    "instruction": body.instruction.strip()})
        if report.get("status") != "done":
            raise HTTPException(500, f"chat patch failed: {report.get('error')}")
        return {"ok": True, "version_id": report["version_id"],
                "summary": report.get("summary", ""),
                "patch": report.get("patch"), "spec": report.get("spec")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"chat patch failed: {e}")


class PatchIn(BaseModel):
    ops: list = []
    summary: str = ""
    base_version: str | None = None


@router.post("/runs/{run_id}/patch")
@router.post("/api/runs/{run_id}/patch")
async def apply_patch(run_id: str, body: PatchIn, user: dict = Depends(require_user)):
    """Deterministic patch (no LLM): UI-built ops validated by G0/G1.

    Same versioning path as chat edits — the two iteration modes converge.
    """
    if not isinstance(body.ops, list) or not body.ops:
        raise HTTPException(400, "ops must be a non-empty list")
    if not body.summary or len(body.summary.strip()) < 4:
        raise HTTPException(400, "summary required (chat shows human diffs)")
    try:
        from engine.patch import apply as _apply, PatchError
        from gates.g0_validate import validate as g0
        from gates.g1_lint import lint as g1
        eng = _engine()
        _assert_run_owner(eng.store, eng.store.get_run(run_id), user)
        base_vid = body.base_version or _current_version(eng.store, run_id)
        if not base_vid:
            raise HTTPException(409, "no base version to patch yet")
        base = eng.store.get_version(base_vid)
        spec = dict(base.get("spec") or {})
        try:
            patched = _apply(spec, body.ops)
        except PatchError as e:
            raise HTTPException(400, f"patch rejected: {e}")
        problems = g0(patched) + [e["message"] for e in g1(patched)["errors"]]
        if problems:
            raise HTTPException(422, f"patched spec failed G0/G1: {'; '.join(problems)[:500]}")
        project_id = (base.get("project_id")
                      or _project_id_for_run(eng.store, run_id))
        vid = eng.store.create_version(project_id, base_vid, patched, "manual",
                                           summary=body.summary.strip()[:500])
        eng.emit(run_id, "patched",
                 {"version": vid, "summary": body.summary.strip(),
                  "ops": len(body.ops)})
        return {"ok": True, "version_id": vid, "spec": patched,
                "summary": body.summary.strip()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"apply patch failed: {e}")


@router.get("/projects/{project_id}/versions")
@router.get("/api/projects/{project_id}/versions")
async def list_versions(project_id: str, user: dict = Depends(require_user)):
    """Version timeline data: id/parent/source/time/summary + full specs."""
    try:
        eng = _engine()
        store = eng.store
        _assert_project_owner(store, project_id, user)
        if hasattr(store, "supa"):
            rows = (store.supa.table("project_versions")
                    .select("id,project_id,parent_id,spec,spec_hash,source,summary,created_at")
                    .eq("project_id", project_id).order("created_at").execute().data or [])
            versions = [{
                "id": r["id"], "parent": r.get("parent_id"), "spec": r.get("spec"),
                "hash": (r.get("spec_hash") or "")[:12],
                "source": r.get("source"), "summary": r.get("summary"),
                "created_at": r.get("created_at"),
            } for r in rows]
        else:
            versions = [{
                "id": v["id"], "parent": v.get("parent"), "spec": v.get("spec"),
                "hash": (v.get("hash") or "")[:12],
                "source": v.get("source"), "summary": v.get("summary"),
                "created_at": None,
            } for v in store.versions.values() if v.get("project_id") == project_id]
        return {"ok": True, "versions": versions}
    except Exception as e:
        raise HTTPException(500, f"versions failed: {e}")


class RevertIn(BaseModel):
    summary: str | None = None


@router.post("/versions/{version_id}/revert")
@router.post("/api/versions/{version_id}/revert")
async def revert_version(version_id: str, body: RevertIn, user: dict = Depends(require_user)):
    """Undo one step: new child version restoring the parent's spec."""
    try:
        eng = _engine()
        ver = eng.store.get_version(version_id)
        parent_id = ver.get("parent") or ver.get("parent_id")
        if not parent_id:
            raise HTTPException(409, "root version has nothing to undo")
        parent = eng.store.get_version(parent_id)
        project_id = ver.get("project_id") or parent.get("project_id")
        _assert_project_owner(eng.store, project_id, user)
        summary = (body.summary or f"Reverted to {str(parent_id)[:8]}").strip()[:500]
        vid = eng.store.create_version(
            project_id, version_id, parent.get("spec") or {}, "manual",
            summary=summary)
        return {"ok": True, "version_id": vid, "summary": summary,
                "spec": parent.get("spec") or {}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"revert failed: {e}")


@router.get("/runs/{run_id}/eventlog")
@router.get("/api/runs/{run_id}/eventlog")
async def run_eventlog(run_id: str, user: dict = Depends(require_user)):
    """Run events as JSON (developer toggle, reports) — same source as SSE."""
    try:
        eng = _engine()
        run = eng.store.get_run(run_id)
        _assert_run_owner(eng.store, run, user)
        return {"ok": True, "events": eng.replay(run_id)}
    except KeyError:
        raise HTTPException(404, f"run {run_id} not found")
    except Exception as e:
        raise HTTPException(404 if "not found" in str(e).lower() else 500, str(e))


def _exemplars():
    from services.run_engine import SupabaseRunStore
    return SupabaseRunStore().supa


@router.get("/exemplars")
@router.get("/api/exemplars")
async def list_exemplars():
    """Template gallery data: name/domain/stats (specs fetched per item)."""
    try:
        rows = (_exemplars().table("exemplars")
                .select("name,domain,source,spec").order("name").execute().data or [])
        out = []
        for r in rows:
            spec = r.get("spec") or {}
            out.append({
                "name": r["name"], "domain": r.get("domain"),
                "source": r.get("source"),
                "app": (spec.get("app") or {}).get("name"),
                "tagline": (spec.get("app") or {}).get("tagline", ""),
                "entities": len((spec.get("model") or {}).get("entities", [])),
                "pages": len((spec.get("ui") or {}).get("pages", [])),
                "starter": (spec.get("app") or {}).get("tagline", "")
                or f"A {r.get('domain', 'business')} app",
            })
        return {"ok": True, "exemplars": out}
    except Exception as e:
        raise HTTPException(500, f"exemplars failed: {e}")


@router.get("/exemplars/{name}")
@router.get("/api/exemplars/{name}")
async def get_exemplar(name: str):
    try:
        rows = (_exemplars().table("exemplars").select("name,domain,spec")
                .eq("name", name).limit(1).execute().data or [])
        if not rows:
            raise HTTPException(404, f"exemplar {name} not found")
        return {"ok": True, "exemplar": rows[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"exemplar failed: {e}")


class FeedbackIn(BaseModel):
    kind: str = "comment"
    project_id: str | None = None
    version_id: str | None = None
    payload: dict | None = None


@router.post("/feedback")
@router.post("/api/feedback")
async def post_feedback(body: FeedbackIn, user: dict = Depends(require_user)):
    if body.kind not in ("rating", "comment", "correction"):
        raise HTTPException(400, f"bad kind {body.kind!r}")
    try:
        res = (_exemplars().table("feedback").insert({
            "project_id": body.project_id, "version_id": body.version_id,
            "kind": body.kind, "payload": body.payload or {},
            "user_id": uid(user)}).execute())
        if not res.data:
            raise RuntimeError("feedback insert failed")
        return {"ok": True, "id": res.data[0]["id"]}
    except Exception as e:
        raise HTTPException(500, f"feedback failed: {e}")


@router.get("/feedback/export")
@router.get("/api/feedback/export")
async def export_feedback(format: str = "json", user: dict = Depends(require_user)):
    """Learning-loop dataset export (JSON default, CSV on ?format=csv)."""
    try:
        q = (_exemplars().table("feedback")
             .select("id,project_id,version_id,kind,payload,created_at")
             .order("created_at"))
        if not is_dev(user):
            q = q.eq("user_id", uid(user))
        rows = q.execute().data or []
        if format == "csv":
            import csv as _csv
            import io as _io
            buf = _io.StringIO()
            w = _csv.writer(buf)
            w.writerow(["id", "project_id", "version_id", "kind", "payload", "created_at"])
            for r in rows:
                w.writerow([r.get("id"), r.get("project_id"), r.get("version_id"),
                            r.get("kind"), json.dumps(r.get("payload") or {}),
                            r.get("created_at")])
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                                     headers={"Content-Disposition":
                                              "attachment; filename=feedback.csv"})
        return {"ok": True, "feedback": rows}
    except Exception as e:
        raise HTTPException(500, f"feedback export failed: {e}")
