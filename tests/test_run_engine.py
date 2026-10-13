"""
Run engine tests — Phase 7 P7.1. No network, no keys.
Fake artifact store (dict) + canned stage overrides (no LLM):
- full build: done, versioned, traced, events ordered, calls summed
- degraded step → degraded run with labelled step (never silent)
- budget exceeded → failed with reason
- kill mid-s6 → residue → resume_run completes with ZERO repeated LLM calls
- SSE replay returns history in order
- v2 sweeper: no-creds fail-soft; orphan flip with fake store
Run: pytest tests/test_run_engine.py -v
"""
import asyncio
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)


def _patch_artifacts(monkeypatch):
    import services.artifacts as art
    blobs = {}

    def put(obj):
        import hashlib, json as _j
        sha = hashlib.sha256(_j.dumps(
            obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        blobs[sha] = obj
        return sha

    def get(sha):
        return blobs.get(sha)
    monkeypatch.setattr(art, "put", put)
    monkeypatch.setattr(art, "get", get)
    return blobs


def _ok(output, calls=1, degraded=False, reason=None):
    from agents.base import AgentResult
    return AgentResult(ok=True, output=output, degraded=degraded,
                       repair_used=False, parse_outcome="ok",
                       fallback_reason=reason, llm_calls=calls,
                       provider="mock", model="m")


MODEL = {"enums": [], "entities": [
    {"id": "widget", "label": "Widget",
     "fields": [{"id": "name", "type": "text", "required": True}],
     "display": {"title": "{name}"}}]}
UI = {"theme": {"archetype": "table-first"}, "nav": [{"page": "home", "label": "Home"}],
      "pages": [{"id": "home", "route": "/", "title": "Home", "roles": ["owner"],
                 "blocks": [{"id": "b1", "type": "data.table",
                             "props": {"entity": "widget", "create": True}}]}]}
ACCESS = {"roles": [{"id": "owner", "label": "Owner"}],
          "rules": [{"entity": "*", "role": "owner",
                     "ops": ["read", "create", "update", "delete"]}]}


def _overrides(calls, fail_at=None, degraded_at=()):
    base = {
        "s0": lambda p, t: _ok({"clean_wish": "widgets", "track": "business",
                                "scope": "mvp", "risk_flags": [], "language": "en"}),
        "s1": lambda p, t: _ok({"questions": [], "assumptions": ["Single shop"]}),
        "s2": lambda p, t: _ok({"model": MODEL}),
        "s3": lambda p, t: _ok({"ui": UI}),
        "s4": lambda p, t: _ok({"access": ACCESS, "automations": []}),
        "s5critic": lambda p, t: _ok({"trace": [{"requirement": "R1",
                                                 "satisfied_by": ["entity:widget"]}],
                                                "critiques": [], "unsatisfied": []}),
        "s6": lambda p, t: _ok({"seed": {}}),
    }
    ov = {}
    for key, fn in base.items():
        def _w(p, t, _k=key, _f=fn):
            if _k == fail_at:
                raise RuntimeError("simulated kill -9")
            calls.append(1)
            res = _f(p, t)
            if _k in degraded_at:
                res.degraded = True
                res.fallback_reason = "deterministic fallback used"
            return res
        ov[key] = _w
    return ov


def _inputs():
    return {"wish": "track widgets", "app_name": "Widgets",
            "requirements": [{"id": "R1", "text": "track widgets", "priority": "must"}]}


def test_full_build_done_versioned_traced(monkeypatch):
    _patch_artifacts(monkeypatch)
    from services.run_engine import RunEngine, MemoryRunStore
    calls: list = []
    eng = RunEngine(MemoryRunStore(), agents_override=_overrides(calls))
    rep = asyncio.run(eng.run(project_id="p1", kind="build", inputs=_inputs()))
    assert rep["status"] == "done", rep
    assert rep["spec"]["trace"] == [{"requirement": "R1",
                                     "satisfied_by": ["entity:widget"]}]
    assert rep["spec"]["model"]["entities"][0]["id"] == "widget"
    assert rep["llm_calls"] == 7
    assert calls and len(calls) == 7
    ver = eng.store.get_version(rep["version_id"])
    assert ver["spec"] == rep["spec"] and ver["source"] == "generate"
    from gates.g0_validate import validate
    from gates.g1_lint import lint
    assert validate(rep["spec"]) == [], "engine output must be G0-clean"
    assert lint(rep["spec"])["errors"] == [], "engine output must be G1-clean"
    types = [e["type"] for e in eng.replay(rep["run_id"])]
    assert types[0] == "run_started" and types[-1] == "run_done"
    assert "retrieval" in types, "retrieval must be logged per stage"


def test_degraded_step_degraded_run(monkeypatch):
    _patch_artifacts(monkeypatch)
    from services.run_engine import RunEngine, MemoryRunStore
    eng = RunEngine(MemoryRunStore(), agents_override=_overrides([], degraded_at=("s3",)))
    rep = asyncio.run(eng.run(project_id="p1", kind="build", inputs=_inputs()))
    assert rep["status"] == "degraded"
    assert rep["degraded_steps"] == ["s3"]
    steps = {s["step_key"]: s for s in rep["steps"]}
    assert steps["s3"]["status"] == "degraded"
    assert "deterministic fallback" in (steps["s3"]["fallback_reason"] or "")


def test_budget_exceeded_fails_fast(monkeypatch):
    _patch_artifacts(monkeypatch)
    from services.run_engine import RunEngine, MemoryRunStore
    eng = RunEngine(MemoryRunStore(), budgets={"max_llm_calls": 2},
                    agents_override=_overrides([]))
    rep = asyncio.run(eng.run(project_id="p1", kind="build", inputs=_inputs()))
    assert rep["status"] == "failed"
    assert "max_llm_calls" in (rep.get("error") or "")


def test_kill_resume_zero_repeated_calls(monkeypatch):
    _patch_artifacts(monkeypatch)
    from services.run_engine import RunEngine, MemoryRunStore
    store = MemoryRunStore()
    calls: list = []
    eng = RunEngine(store, agents_override=_overrides(calls, fail_at="s6"))
    with pytest.raises(RuntimeError, match="kill"):
        asyncio.run(eng.run(project_id="p1", kind="build", inputs=_inputs()))
    run_id = next(iter(store.runs))
    # residue as after kill -9: s5 persisted done; sweeper flips run to failed
    statuses = {s["step_key"]: s["status"] for s in store.get_steps(run_id)}
    assert statuses.get("s5") == "done" and len(calls) == 6
    store.set_status(run_id, "failed", "simulated kill -9")
    # fresh process, resume the SAME run: only missing s6 reruns
    calls2: list = []
    eng2 = RunEngine(store, agents_override=_overrides(calls2))
    rep = asyncio.run(eng2.resume_run(run_id))
    assert rep["status"] == "done", rep
    assert calls2 == [1], "only the missing s6 may burn a call"
    assert rep["spec"]["model"]["entities"][0]["id"] == "widget"
    assert not any(s["status"] in ("running",) for s in rep["steps"])


def test_resume_rejects_running(monkeypatch):
    _patch_artifacts(monkeypatch)
    from services.run_engine import RunEngine, MemoryRunStore
    store = MemoryRunStore()
    rid = store.create_run("p1", "build", _inputs())
    store.set_status(rid, "running")
    with pytest.raises(RuntimeError, match="already running"):
        asyncio.run(RunEngine(store).resume_run(rid))


def test_iterate_chat_patch_round_trip(monkeypatch):
    _patch_artifacts(monkeypatch)
    from services.run_engine import RunEngine, MemoryRunStore
    store = MemoryRunStore()
    eng = RunEngine(store, agents_override=_overrides([]))
    rep = asyncio.run(eng.run(project_id="p1", kind="build", inputs=_inputs()))
    assert rep["status"] == "done"

    def _edit(payload, tele):
        from agents.base import AgentResult
        return AgentResult(ok=True, output={
            "patch": [{"op": "replace", "path": "/app/tagline", "value": "v2"}],
            "summary": "new tagline"}, llm_calls=1)

    eng2 = RunEngine(store, agents_override={"edit": _edit})
    rep2 = asyncio.run(eng2.run(
        project_id="p1", kind="iterate",
        inputs={"base_version": rep["version_id"], "instruction": "new tagline"}))
    assert rep2["status"] == "done"
    assert rep2["spec"]["app"]["tagline"] == "v2"
    assert rep2["summary"] == "new tagline"
    child = store.get_version(rep2["version_id"])
    assert child["parent"] == rep["version_id"]


def test_v2_sweeper_no_creds_failsoft(monkeypatch):
    for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY"):
        monkeypatch.delenv(k, raising=False)
    from services.sweeper import sweep_v2_orphans
    out = sweep_v2_orphans()
    assert out["runs"] == 0 and "error" in out


def test_v2_sweeper_flips_orphans(monkeypatch):
    from services import run_engine as RE
    from services.sweeper import sweep_v2_orphans

    class FakeSupa:
        def __init__(self):
            self.runs = [{"id": "r1"}]
            self.steps = [{"step_key": "s2", "agent": "s2-modeler",
                           "status": "running", "input_hash": "h", "attempt": 1}]
            self.flips = []

        def table(self, name):
            outer = self

            class Q:
                def select(self, *a): return self
                def eq(self, *a): return self
                def limit(self, *a): return self
                def order(self, *a): return self
                def execute(self):
                    if name == "runs":
                        return type("R", (), {"data": outer.runs})()
                    return type("R", (), {"data": outer.steps})()
                def update(self, payload): self._p = payload; return self
            return Q()

    fake = FakeSupa()
    monkeypatch.setattr(RE.SupabaseRunStore, "__init__", lambda self: setattr(self, "supa", fake))
    flips = []
    monkeypatch.setattr(RE.SupabaseRunStore, "get_steps", lambda self, rid: fake.steps)
    monkeypatch.setattr(RE.SupabaseRunStore, "upsert_step",
                        lambda self, rid, key, agent, status, **kw: flips.append((key, status)))
    monkeypatch.setattr(RE.SupabaseRunStore, "set_status",
                        lambda self, rid, status, error=None: flips.append((rid, status)))
    out = sweep_v2_orphans()
    assert out == {"runs": 1, "steps": 1}
    assert ("s2", "pending") in flips and ("r1", "failed") in flips
