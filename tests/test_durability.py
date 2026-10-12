"""
Durable builds — Phase 3 tests. No network, no keys, no Supabase.
Covers AGENT.md P3.1–P3.4 acceptance:
- 006b migration is additive-only
- artifact store: sha stability/canonicalization, miss → None, oversize/failure → raise
- sweeper: orphan running → pending (+attempt), building wish → failed, clean tree → no-op, DB down → fail-soft
- legacy hollow rows (no content_sha) still requeue + regenerate (backward compat)
- kill-resume: fault mid-wiring → residue (building + running) → fresh process →
  sweeper → retry completes with ZERO repeated per-step LLM calls
- store failure fails the step (never persists hollow)
Run: pytest tests/test_durability.py -v
"""
import asyncio
import importlib
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)


def _scrub_env(monkeypatch, extra=None):
    for k in ["OPENROUTER_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY",
              "DEEPSEEK_API_KEY", "SUPABASE_URL", "SUPABASE_KEY",
              "LLM_COOLDOWN_SECONDS", "LLM_ONLY", "LLM_TELEMETRY", "LLM_CASSETTES",
              "LLM_CASSETTE_DIR", "INTARA_TEMPLATE_ONLY", "STEP_TIMEOUT_SECONDS"]:
        monkeypatch.delenv(k, raising=False)
    for k, v in (extra or {}).items():
        monkeypatch.setenv(k, v)


def _stub_mem(monkeypatch):
    """Isolate orchestrator's MEM cache import (routers.wishes is server runtime)."""
    stub = types.ModuleType("routers.wishes")
    stub.MEM = {}
    monkeypatch.setitem(sys.modules, "routers.wishes", stub)
    return stub.MEM


# ---------- in-memory fakes ----------

class FakeDB:
    """In-memory wishes / wish_steps / artifact_contents."""

    def __init__(self):
        self.wishes: dict = {}
        self.steps: dict = {}  # wid -> {step_id: row}
        self.blobs: dict = {}  # sha -> content
        self.status_log: list = []

    # -- db.wishes surface used by orchestrator/sweeper --
    def get_wish_with_steps(self, wid):
        w = self.wishes[wid]
        rows = self.steps.get(wid, {})
        steps = {sid: {"status": r["status"], "startedAt": r.get("started_at"),
                       "endedAt": r.get("ended_at"), "error": r.get("error"),
                       "fallback_reason": (r.get("output") or {}).get("fallback_reason")}
                 for sid, r in rows.items()}
        return {"id": wid, "prompt": w["prompt"], "prd": w["prd"],
                "artifacts": {"steps": steps, "buildGraph": w["prd"].get("buildGraph", [])},
                "status": w["status"], "build_graph": w["prd"].get("buildGraph", [])}

    def get_steps(self, wid):
        return [dict(row, sid=key)
                for key, row in self.steps.get(wid, {}).items()]

    def update_step(self, wid, step_id, **kw):
        row = self.steps[wid][step_id]
        for k, v in kw.items():
            if v is not None:
                row[k] = v
        return [row]

    def set_wish_status(self, wid, status, **kw):
        self.wishes[wid]["status"] = status
        for k, v in kw.items():
            if v is not None:
                self.wishes[wid][k] = v
        self.status_log.append((wid, status))
        return [self.wishes[wid]]

    def list_wishes_with_steps(self, limit=50):
        out = []
        for wid, w in self.wishes.items():
            out.append({"id": wid, "status": w["status"],
                        "build_graph": w["prd"].get("buildGraph", []),
                        "prd": w["prd"]})
        return out[:limit]

    # -- supabase-ish client for services.artifacts --
    def client(self):
        db = self

        class Q:
            def __init__(self):
                self._row = None
                self._sha = None

            def upsert(self, payload, **kw):
                self._row = payload
                return self

            def insert(self, payload):
                self._row = payload
                return self

            def select(self, *a):
                return self

            def eq(self, k, v):
                self._sha = v
                return self

            def limit(self, n):
                return self

            def execute(self):
                if self._row is not None:
                    db.blobs[self._row["sha256"]] = self._row["content"]
                    return types.SimpleNamespace(data=[self._row])
                content = db.blobs.get(self._sha)
                return types.SimpleNamespace(
                    data=[{"content": content}] if content is not None else [])

        class C:
            def table(self, name):
                assert name == "artifact_contents", name
                return Q()

        return C()


def _make_plan():
    tables = [{"name": "users", "fields": [
        {"name": "id", "type": "integer"}, {"name": "name", "type": "text"}]}]
    pages = [{"name": "Users", "route": "/users", "table": "users",
              "components": ["csv-export"]}]
    apis = [{"method": "GET", "path": "/api/users", "desc": "list users"}]
    return {
        "appName": "TestApp", "tagline": "t", "tables": tables, "pages": pages,
        "apis": apis, "entities": [],
        "buildGraph": [
            {"id": "schema-foundation", "kind": "schema"},
            {"id": "backend-users", "kind": "backend_table", "ref": "users"},
            {"id": "frontend-Users", "kind": "frontend_page", "ref": "Users"},
            {"id": "wiring", "kind": "wiring"},
            {"id": "validate", "kind": "validate"},
        ],
    }


FE_FILE = {"path": "src/pages/Users.tsx",
           "content": "export default function Users() { return <div>users</div> }"}
BE_FILE = {"path": "server/routers/users.py",
           "content": ("from fastapi import APIRouter\nrouter = APIRouter()\n\n"
                       "@router.get('/api/users')\ndef list_users():\n    return []\n")}
BE_OPENAPI = {"paths": {"/api/users": {"get": {"responses": {"200": {"description": "ok"}}}}}}


def _seed_db(plan, step_states=None):
    """step_states: step_id -> (status, output). Default all pending."""
    db = FakeDB()
    wid = "wish-test-1"
    db.wishes[wid] = {"prompt": "test app", "prd": plan, "status": "building"}
    db.steps[wid] = {}
    for n in plan["buildGraph"]:
        status, output = (step_states or {}).get(n["id"], ("pending", None))
        db.steps[wid][n["id"]] = {"step_id": n["id"], "kind": n["kind"],
                                  "status": status, "output": output,
                                  "attempt": 1, "started_at": None,
                                  "ended_at": None, "error": None}
    return db, wid


def _patch_db(monkeypatch, db):
    import db.wishes as wishes
    monkeypatch.setattr(wishes, "get_wish_with_steps", db.get_wish_with_steps)
    monkeypatch.setattr(wishes, "get_steps", db.get_steps)
    monkeypatch.setattr(wishes, "update_step", db.update_step)
    monkeypatch.setattr(wishes, "set_wish_status", db.set_wish_status)
    monkeypatch.setattr(wishes, "list_wishes_with_steps", db.list_wishes_with_steps)
    monkeypatch.setattr(wishes, "_client", db.client)


def _patch_generators(monkeypatch, calls, fail_at=None):
    """Mocked step generators; every step-level invocation counts as one LLM call."""
    import services.generators.schema_gen as sg
    import services.generators.backend_gen as bg
    import services.generators.frontend_gen as fg
    import services.gates as gates

    def gen_schema(prd):
        # assembly calls pass the full plan (has appName); step calls don't
        if "appName" in prd:
            return {"tables": prd.get("tables", []), "prisma": "PRISMA-FULL", "sql": "SQL-FULL"}
        calls["schema_step"] += 1
        if fail_at == "schema":
            raise RuntimeError("simulated kill -9")
        return {"tables": prd.get("tables", []), "prisma": "PRISMA-FULL", "sql": "SQL-FULL"}

    def gen_backend(prd):
        if prd.get("pages"):
            calls["assembly_be"] += 1  # final-regen path (existing behavior)
        else:
            calls["backend_step"] += 1
            if fail_at == "backend":
                raise RuntimeError("simulated kill -9")
        import copy
        return {"files": [dict(BE_FILE)], "openapi": copy.deepcopy(BE_OPENAPI),
                "requirements": "fastapi\n"}

    def gen_frontend(prd):
        if os.getenv("INTARA_TEMPLATE_ONLY") == "1":
            calls["gate_regen"] += 1  # validate's template-only regen
        elif calls.get("_wiring_done"):
            calls["assembly_fe"] += 1  # final gap-fill regen (existing behavior)
        else:
            calls["frontend_step"] += 1
            if fail_at == "frontend":
                raise RuntimeError("simulated kill -9")
        return {"files": [dict(FE_FILE)]}

    monkeypatch.setattr(sg, "generate_schema", gen_schema)
    monkeypatch.setattr(bg, "generate_backend", gen_backend)
    monkeypatch.setattr(fg, "generate_frontend", gen_frontend)
    # heavy gates stay mocked (no node/toolchain in CI); light validators run for real
    monkeypatch.setattr(gates, "run_fe_gates", lambda *a: [])
    monkeypatch.setattr(gates, "run_be_gates", lambda *a: [])
    monkeypatch.setattr(gates, "run_contract_checks", lambda *a: [])
    monkeypatch.setattr(gates, "repair_gate_files", lambda *a, **k: {})


def _fresh_orchestrator():
    import services.orchestrator as orch
    importlib.reload(orch)
    orch.BUILD_STATE.clear()
    orch.BUILD_RUNNING.clear()
    orch.SSE_QUEUES.clear()
    return orch


def _run_build(orch, wid, plan):
    return asyncio.run(orch.run_build_sequential(wid, plan, "test app"))


# ---------- P3.1 store ----------

def test_migration_006b_additive_only():
    fp = os.path.join(ROOT, "supabase", "migrations", "006b_artifact_contents.sql")
    sql = open(fp).read().lower()
    assert "create table if not exists artifact_contents" in sql
    assert "sha256" in sql and "content" in sql
    for banned in ("alter table wishes", "alter table wish_steps", "drop table", "delete from"):
        assert banned not in sql, f"migration must not contain: {banned}"


def test_artifact_put_get_roundtrip_canonical(monkeypatch):
    _scrub_env(monkeypatch)
    db = FakeDB()
    _patch_db(monkeypatch, db)
    import services.artifacts as art
    importlib.reload(art)
    sha1 = art.put({"b": 1, "a": [1, 2]})
    sha2 = art.put({"a": [1, 2], "b": 1})  # key order must not matter
    assert sha1 == sha2 == art.digest({"a": [1, 2], "b": 1})
    assert art.get(sha1) == {"b": 1, "a": [1, 2]}
    assert db.blobs[sha1] == {"b": 1, "a": [1, 2]}


def test_artifact_get_miss_and_put_limits(monkeypatch):
    _scrub_env(monkeypatch)
    db = FakeDB()
    _patch_db(monkeypatch, db)
    import services.artifacts as art
    importlib.reload(art)
    assert art.get("deadbeef") is None
    assert art.get(None) is None
    # oversize fails fast (canonical {"x":"y"} is 9 bytes)
    monkeypatch.setenv("ARTIFACT_MAX_BYTES", "5")
    with pytest.raises(RuntimeError, match="too large"):
        art.put({"x": "y"})
    # DB failure fails fast (never a silent hollow write)
    monkeypatch.delenv("ARTIFACT_MAX_BYTES")

    class Boom:
        def table(self, name):
            raise RuntimeError("db down")

    import db.wishes as wishes
    monkeypatch.setattr(wishes, "_client", lambda: Boom())
    with pytest.raises(RuntimeError):
        art.put({"x": "y"})


# ---------- P3.3 sweeper ----------

def test_sweeper_requeues_orphans(monkeypatch):
    _scrub_env(monkeypatch)
    plan = _make_plan()
    db, wid = _seed_db(plan, {
        "schema-foundation": ("done", {"tables": plan["tables"]}),
        "backend-users": ("running", None),
        "frontend-Users": ("pending", None),
    })
    db.wishes["other"] = {"prompt": "x", "prd": plan, "status": "ready"}
    db.steps["other"] = {}
    _patch_db(monkeypatch, db)
    import services.sweeper as sw
    importlib.reload(sw)
    out = sw.sweep_orphans()
    assert out == {"wishes": 1, "steps": 1}
    assert db.steps[wid]["backend-users"]["status"] == "pending"
    assert db.steps[wid]["backend-users"]["attempt"] == 2
    assert "orphaned" in (db.steps[wid]["backend-users"]["error"] or "")
    assert db.steps[wid]["schema-foundation"]["status"] == "done"  # untouched
    assert db.wishes[wid]["status"] == "failed"  # never stuck in building
    assert db.wishes[wid]["current_step_id"] == "backend-users"
    assert db.wishes["other"]["status"] == "ready"  # untouched


def test_sweeper_clean_tree_noop_and_db_down_failsoft(monkeypatch):
    _scrub_env(monkeypatch)
    plan = _make_plan()
    db, wid = _seed_db(plan, {"schema-foundation": ("done", {"tables": []})})
    db.wishes[wid]["status"] = "ready"
    _patch_db(monkeypatch, db)
    import services.sweeper as sw
    importlib.reload(sw)
    assert sw.sweep_orphans() == {"wishes": 0, "steps": 0}

    import db.wishes as wishes
    monkeypatch.setattr(wishes, "list_wishes_with_steps",
                        lambda limit=50: (_ for _ in ()).throw(RuntimeError("db down")))
    out = sw.sweep_orphans()
    assert out["wishes"] == 0 and "error" in out  # never raises, never blocks boot


# ---------- P3.2 resume ----------

def test_legacy_hollow_row_requeues_and_regenerates(monkeypatch):
    """Backward compat: pre-P3 rows (paths only, no content_sha) still requeue."""
    _scrub_env(monkeypatch)
    _stub_mem(monkeypatch)
    plan = _make_plan()
    schema_full = {"tables": plan["tables"], "prisma": "PRISMA-FULL", "sql": "SQL-FULL"}
    import services.artifacts as art
    importlib.reload(art)
    db, wid = _seed_db(plan)
    _patch_db(monkeypatch, db)
    schema_sha = art.put(schema_full)
    # schema done WITH content (new), backend done hollow (legacy, no sha)
    db.steps[wid]["schema-foundation"].update(
        {"status": "done", "output": {"tables": plan["tables"], "content_sha": schema_sha}})
    db.steps[wid]["backend-users"].update(
        {"status": "done", "output": {"files": ["server/routers/users.py"],
                                     "openapi": BE_OPENAPI}})
    calls = {"schema_step": 0, "backend_step": 0, "frontend_step": 0,
             "assembly_be": 0, "assembly_fe": 0, "gate_regen": 0}
    _patch_generators(monkeypatch, calls)
    orch = _fresh_orchestrator()
    assert _run_build(orch, wid, plan) is True
    # schema restored (no regen), hollow backend re-ran exactly once
    assert calls["schema_step"] == 0
    assert calls["backend_step"] == 1
    assert db.wishes[wid]["status"] == "ready"
    events = [p["event"] for p in orch.BUILD_STATE[wid]["log"]]
    assert "step_requeued" in events and "step_restored" in events


def test_store_failure_fails_step_never_hollow(monkeypatch):
    _scrub_env(monkeypatch)
    _stub_mem(monkeypatch)
    plan = _make_plan()
    db, wid = _seed_db(plan)
    _patch_db(monkeypatch, db)
    calls = {"schema_step": 0, "backend_step": 0, "frontend_step": 0,
             "assembly_be": 0, "assembly_fe": 0, "gate_regen": 0}
    _patch_generators(monkeypatch, calls)
    import services.artifacts as art
    monkeypatch.setattr(art, "put", lambda obj: (_ for _ in ()).throw(RuntimeError("store down")))
    orch = _fresh_orchestrator()
    assert _run_build(orch, wid, plan) is False
    assert db.wishes[wid]["status"] == "failed"
    assert db.steps[wid]["schema-foundation"]["status"] == "failed"


# ---------- P3.4 kill-resume ----------

def test_kill_resume_zero_repeated_llm_calls(monkeypatch):
    """Simulated kill -9 mid-wiring → residue → fresh process → sweep → retry.
    Retry must complete with zero repeated per-step LLM calls."""
    _scrub_env(monkeypatch)
    _stub_mem(monkeypatch)
    plan = _make_plan()

    # --- first run: crash mid-wiring (fault AFTER all LLM steps persisted) ---
    db, wid = _seed_db(plan)
    _patch_db(monkeypatch, db)
    calls = {"schema_step": 0, "backend_step": 0, "frontend_step": 0,
             "assembly_be": 0, "assembly_fe": 0, "gate_regen": 0}
    import services.generators.scaffold_gen as scaf
    real_fe_scaffold = scaf.frontend_scaffold

    def dying_scaffold(app_name):
        raise RuntimeError("simulated kill -9")

    _patch_generators(monkeypatch, calls)
    monkeypatch.setattr(scaf, "frontend_scaffold", dying_scaffold)
    orch = _fresh_orchestrator()
    assert _run_build(orch, wid, plan) is False  # died at wiring
    assert calls["schema_step"] == 1 and calls["backend_step"] == 1
    assert calls["frontend_step"] == 1
    # all LLM steps persisted WITH content before the crash
    for sid in ("schema-foundation", "backend-users", "frontend-Users"):
        row = db.steps[wid][sid]
        assert row["status"] == "done" and row["output"].get("content_sha"), sid
    assert len(db.blobs) == 3

    # --- unclean-shutdown residue: wish building, wiring running (no failure persist) ---
    db.wishes[wid]["status"] = "building"
    db.steps[wid]["wiring"]["status"] = "running"
    # fresh process: empty build state, restored scaffold fn
    monkeypatch.setattr(scaf, "frontend_scaffold", real_fe_scaffold)
    orch2 = _fresh_orchestrator()

    # --- boot sweeper ---
    import services.sweeper as sw
    importlib.reload(sw)
    out = sw.sweep_orphans()
    assert out == {"wishes": 1, "steps": 1}
    assert db.wishes[wid]["status"] == "failed"
    assert db.steps[wid]["wiring"]["status"] == "pending"
    assert not any(r["status"] in ("building", "running")
                   for rows in db.steps.values() for r in rows.values())

    # --- retry (what POST /wish/{wid}/retry spawns): zero repeated LLM calls ---
    calls["_wiring_done"] = True  # mark: frontend calls from here are assembly gap-fill
    before = dict(calls)
    assert _run_build(orch2, wid, plan) is True
    assert calls["schema_step"] == before["schema_step"], "schema must not regenerate"
    assert calls["backend_step"] == before["backend_step"], "backend must not regenerate"
    assert calls["frontend_step"] == before["frontend_step"], "frontend must not regenerate"
    # done steps were restored, not skipped-blind: real contents reached assembly
    final = db.wishes[wid]
    assert final["status"] == "ready"
    fe_files = final["artifacts"]["frontend"]["files"]
    users_page = [f for f in fe_files if f["path"] == "src/pages/Users.tsx"]
    assert users_page and "users" in users_page[0]["content"]
    assert all(r["status"] == "done" for r in db.steps[wid].values())
    events = [p["event"] for p in orch2.BUILD_STATE[wid]["log"]]
    assert events.count("step_restored") == 3  # schema + backend + frontend
    assert "step_done" in events and "build_done" in events
