"""
Runs API tests — Phase 8 roles editor. Real FastAPI app, fake engine
(MemoryRunStore preloaded with a gold version): deterministic patch
endpoint happy path, rejection paths, chat validation.
Run: pytest tests/test_runs_api.py -v
"""
import copy
import importlib
import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)


def _load_main():
    import services.run_engine as RE
    importlib.reload(RE)
    spec = importlib.util.spec_from_file_location(
        "real_main_for_runs", os.path.join(SRV, "main.py"))
    mod = importlib.util.module_from_spec(spec)
    old = sys.modules.get("main")
    sys.modules["main"] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        if old is not None:
            sys.modules["main"] = old
        else:
            sys.modules.pop("main", None)
    return mod, RE


def _engine_with_gold(monkeypatch):
    mod, RE = _load_main()
    store = RE.MemoryRunStore()
    gold = json.load(open(os.path.join(
        ROOT, "packages", "spec", "exemplars", "repair-tracker.json")))
    from engine.versions import spec_hash
    vid = "v-gold"
    store.versions[vid] = {"id": vid, "project_id": "p1", "parent": None,
                           "spec": copy.deepcopy(gold),
                           "hash": spec_hash(gold), "source": "generate"}
    rid = store.create_run("p1", "build", {"wish": "x"})
    eng = RE.RunEngine(store)
    monkeypatch.setattr(RE, "_engine", eng)
    return mod, eng, rid, vid


def test_patch_endpoint_happy_path(monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    pytest.importorskip("starlette.testclient")
    from fastapi.testclient import TestClient
    mod, eng, rid, vid = _engine_with_gold(monkeypatch)
    c = TestClient(mod.app)
    r = c.post(f"/api/runs/{rid}/patch", json={
        "base_version": vid,
        "ops": [{"op": "add", "path": "/access/roles/-",
                 "value": {"id": "auditor", "label": "Auditor"}},
                {"op": "replace", "path": "/ui/pages/0/roles",
                 "value": ["owner", "technician", "auditor"]},
                {"op": "add", "path": "/access/rules/-",
                 "value": {"entity": "job", "role": "auditor", "ops": ["read"]}}],
        "summary": "add auditor role"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["version_id"] != vid
    child = eng.store.get_version(body["version_id"])
    assert child["parent"] == vid
    assert any(x["id"] == "auditor" for x in body["spec"]["access"]["roles"])


def test_patch_endpoint_rejections(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("starlette.testclient")
    from fastapi.testclient import TestClient
    mod, eng, rid, vid = _engine_with_gold(monkeypatch)
    c = TestClient(mod.app)
    assert c.post(f"/api/runs/{rid}/patch",
                  json={"base_version": vid, "ops": [], "summary": "x"}).status_code == 400
    assert c.post(f"/api/runs/{rid}/patch",
                  json={"base_version": vid,
                        "ops": [{"op": "remove", "path": "/missing"}],
                        "summary": "bad op"}).status_code == 400
    # G1-breaking patch → 422 (remove the owner role the pages need)
    r = c.post(f"/api/runs/{rid}/patch", json={
        "base_version": vid,
        "ops": [{"op": "remove", "path": "/access/roles/0"}],
        "summary": "drop owner"})
    assert r.status_code == 422, r.text


def test_chat_validation(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("starlette.testclient")
    from fastapi.testclient import TestClient
    mod, eng, rid, vid = _engine_with_gold(monkeypatch)
    c = TestClient(mod.app)
    assert c.post(f"/api/runs/{rid}/chat",
                  json={"instruction": "x"}).status_code == 400
    r = c.get(f"/api/runs/{rid}")
    assert r.status_code == 200
    body = r.json()
    assert body["run"]["id"] == rid and body["spec"] is None


def test_versions_list_revert_and_summary(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("starlette.testclient")
    from fastapi.testclient import TestClient
    mod, eng, rid, vid = _engine_with_gold(monkeypatch)
    c = TestClient(mod.app)
    # patch stores its summary on the child version
    r = c.post(f"/api/runs/{rid}/patch", json={
        "base_version": vid,
        "ops": [{"op": "replace", "path": "/app/tagline", "value": "v2"}],
        "summary": "retitle"})
    assert r.status_code == 200, r.text
    child_id = r.json()["version_id"]
    assert eng.store.get_version(child_id)["summary"] == "retitle"
    # timeline lists parent→child with summaries
    r = c.get("/api/projects/p1/versions")
    assert r.status_code == 200, r.text
    ids = [v["id"] for v in r.json()["versions"]]
    assert ids == [vid, child_id]
    assert r.json()["versions"][1]["summary"] == "retitle"
    # revert the child → grandchild restoring the parent spec
    r = c.post(f"/api/versions/{child_id}/revert", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["spec"]["app"]["tagline"] != "v2"
    assert eng.store.get_version(body["version_id"])["parent"] == child_id
    # root has nothing to undo
    assert c.post(f"/api/versions/{vid}/revert", json={}).status_code == 409


class _FakeQ:
    def __init__(self, store, table, rows=None):
        self._store = store
        self._table = table
        self._rows = list(rows) if rows is not None else None
        self._insert = None

    def _all(self):
        return self._store.setdefault(self._table, [])

    def select(self, *a):
        self._rows = self._all()
        return self

    def eq(self, k, v):
        self._rows = [r for r in (self._rows if self._rows is not None else self._all())
                      if r.get(k) == v]
        return self

    def order(self, *a, **k):
        return self

    def limit(self, n):
        self._rows = (self._rows if self._rows is not None else self._all())[:n]
        return self

    def insert(self, payload):
        row = dict(payload)
        row.setdefault("id", f"fake-{len(self._all()) + 1}")
        self._all().append(row)
        self._insert = [row]
        return self

    def execute(self):
        return type("R", (), {"data": self._insert if self._insert is not None else (self._rows or [])})()


class _FakeSupa:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        return _FakeQ(self._tables, name)


def _engine_with_events(monkeypatch):
    mod, RE = _load_main()
    store = RE.MemoryRunStore()
    rid = store.create_run("p1", "build", {"wish": "x"})
    store.append_event(rid, "run_started", {"kind": "build"})
    store.append_event(rid, "step_done", {"step": "s0"})
    eng = RE.RunEngine(store)
    monkeypatch.setattr(RE, "_engine", eng)
    return mod, eng, rid


def test_eventlog_returns_history(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("starlette.testclient")
    from fastapi.testclient import TestClient
    mod, eng, rid = _engine_with_events(monkeypatch)
    c = TestClient(mod.app)
    r = c.get(f"/api/runs/{rid}/eventlog")
    assert r.status_code == 200, r.text
    assert [e["type"] for e in r.json()["events"]] == ["run_started", "step_done"]
    assert c.get("/api/runs/nope/eventlog").status_code == 404


def test_exemplars_and_feedback(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("starlette.testclient")
    from fastapi.testclient import TestClient
    mod, RE = _load_main()
    import routers.runs as runs_router
    fake = _FakeSupa()
    fake._tables["exemplars"] = [
        {"name": "t1", "domain": "d", "source": "hand-authored",
         "spec": {"app": {"name": "T", "tagline": "tag"},
                  "model": {"entities": [{"id": "e"}]},
                  "ui": {"pages": [{"id": "p"}]}}}]
    monkeypatch.setattr(runs_router, "_exemplars", lambda: fake)
    store = RE.MemoryRunStore()
    monkeypatch.setattr(RE, "_engine", RE.RunEngine(store))
    c = TestClient(mod.app)
    r = c.get("/api/exemplars")
    assert r.status_code == 200, r.text
    items = r.json()["exemplars"]
    assert len(items) == 1 and items[0]["entities"] == 1 and items[0]["pages"] == 1
    r = c.get("/api/exemplars/t1")
    assert r.status_code == 200 and r.json()["exemplar"]["domain"] == "d"
    assert c.get("/api/exemplars/nope").status_code == 404
    r = c.post("/api/feedback", json={"kind": "rating",
                                      "payload": {"stars": 5}})
    assert r.status_code == 200, r.text
    assert c.post("/api/feedback", json={"kind": "bogus"}).status_code == 400
    r = c.get("/api/feedback/export")
    assert r.status_code == 200 and len(r.json()["feedback"]) == 1
    r = c.get("/api/feedback/export?format=csv")
    assert r.status_code == 200 and "stars" in r.text and r.headers["content-type"].startswith("text/csv")
