"""Run-first front door tests: wish shell + status writeback.

The v2 product path creates a lightweight wish row before starting a spec run,
then the run advances that wish's status. These tests pin both halves without
touching Supabase or an LLM.
"""
import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)


def _load_main():
    spec = importlib.util.spec_from_file_location(
        "real_main_for_run_first", os.path.join(SRV, "main.py"))
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
    return mod


def test_wish_shell_endpoint_creates_shell(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("starlette.testclient")
    from fastapi.testclient import TestClient
    mod = _load_main()
    import routers.wishes as W

    calls = {}

    def fake_shell(prompt, owner=None):
        calls["prompt"] = prompt
        calls["owner"] = owner
        return {"id": "w1", "prompt": prompt, "prd": {}, "artifacts": {},
                "status": "planning"}

    monkeypatch.setattr(W, "make_plan_shell", fake_shell)
    c = TestClient(mod.app)
    r = c.post("/api/wish/shell", json={"prompt": "  track tasks  "})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "w1"
    assert calls["prompt"] == "track tasks"
    assert c.post("/api/wish/shell", json={"prompt": "x"}).status_code == 400
    assert c.post("/api/wish/shell", json={"prompt": "x" * 501}).status_code == 400


def test_writeback_merges_artifacts_and_advances_status(monkeypatch):
    import routers.runs as R
    import db.wishes as D

    monkeypatch.setattr(D, "get_wish_with_steps", lambda wid: {
        "status": "planning", "artifacts": {"old": 1}})
    seen = {}

    def fake_set(wid, status, **kw):
        seen.update({"wid": wid, "status": status, **kw})

    monkeypatch.setattr(D, "set_wish_status", fake_set)
    R._writeback_wish("w1", {"v2": {"run_id": "r1"}}, status="building")
    assert seen["wid"] == "w1" and seen["status"] == "building"
    assert seen["artifacts"]["old"] == 1
    assert seen["artifacts"]["v2"]["run_id"] == "r1"

    R._writeback_wish("w1", {"v2": {"run_id": "r1", "status": "done"}})
    assert seen["status"] == "planning", "no explicit status must preserve the wish status"

    R._writeback_wish("w1", {}, prd_patch={"appName": "Tracker"})
    assert seen["prd"]["appName"] == "Tracker"
