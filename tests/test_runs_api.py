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
