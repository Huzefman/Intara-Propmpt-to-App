import io
import json
import os
import sys
import zipfile
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)

from fastapi.testclient import TestClient
from tests.test_runs_api import _engine_with_gold

def test_download_run_code(monkeypatch):
    mod, eng, rid, vid = _engine_with_gold(monkeypatch)
    eng.store.append_event(rid, "run_done", {"version": vid})

    client = TestClient(mod.app)
    res = client.get(f"/api/runs/{rid}/download", headers={"Authorization": "Bearer dev"})
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"
    assert "fixit-app.zip" in res.headers["content-disposition"]

    # Verify zip content
    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        names = z.namelist()
        assert "fixit/package.json" in names
        assert "fixit/src/App.tsx" in names
        assert "fixit/src/schema.sql" in names
        assert "fixit/src/spec.json" in names
        assert "fixit/src/db.ts" in names
        assert "fixit/README.md" in names

def test_retry_recovers_wish_from_events(monkeypatch):
    mod, eng, _, _ = _engine_with_gold(monkeypatch)
    store = eng.store

    pid = "p1"
    # Create run with EMPTY inputs (like old runs or unmigrated runs)
    rid = store.create_run(pid, "build", {})
    store.set_status(rid, "failed", "assemble G0/G1 failed")
    # Simulate event with wish
    store.append_event(rid, "run_started", {"kind": "build", "wish": "School club manager"})

    client = TestClient(mod.app)
    res = client.post(f"/api/runs/{rid}/retry", headers={"Authorization": "Bearer dev"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["ok"] is True
    assert data["status"] == "running"
