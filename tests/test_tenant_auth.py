"""Multi-tenant isolation tests — auth gate, cross-account 404s, build quota.

Run: pytest tests/test_tenant_auth.py -v
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
        "main_tenant_auth", os.path.join(SRV, "main.py"))
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


def _client(mod):
    pytest.importorskip("fastapi")
    pytest.importorskip("starlette.testclient")
    from fastapi.testclient import TestClient
    return TestClient(mod.app)


def test_requires_bearer_token(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    mod = _load_main()
    c = _client(mod)
    r = c.get("/api/wishes")
    assert r.status_code == 401, r.text
    assert "Sign in" in r.json()["detail"]

    r = c.get("/api/wish/any-id")
    assert r.status_code == 401


def test_cross_account_wish_is_404(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    mod = _load_main()
    import db.wishes as dw

    monkeypatch.setattr(dw, "get_wish_with_steps", lambda wid: {
        "id": wid, "owner": "user-a", "prompt": "secret plan",
        "prd": {}, "artifacts": {}, "status": "ready",
    })

    from auth import require_user
    c = _client(mod)

    mod.app.dependency_overrides[require_user] = lambda: {
        "id": "user-b", "email": "b@example.com"}
    assert c.get("/api/wish/w1").status_code == 404

    mod.app.dependency_overrides[require_user] = lambda: {
        "id": "user-a", "email": "a@example.com"}
    ok = c.get("/api/wish/w1")
    assert ok.status_code == 200, ok.text
    assert ok.json()["owner"] == "user-a"


def test_ownerless_legacy_wish_is_invisible(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    mod = _load_main()
    import db.wishes as dw

    monkeypatch.setattr(dw, "get_wish_with_steps", lambda wid: {
        "id": wid, "owner": None, "prompt": "legacy", "prd": {},
        "artifacts": {}, "status": "ready",
    })
    from auth import require_user
    mod.app.dependency_overrides[require_user] = lambda: {
        "id": "user-a", "email": "a@example.com"}
    assert _client(mod).get("/api/wish/legacy-1").status_code == 404


def test_list_is_scoped_to_owner(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    mod = _load_main()
    import db.wishes as dw

    seen = {}

    def fake_list(limit=50, owner=None):
        seen["owner"] = owner
        return [{"id": "w1", "prompt": "mine", "prd": {},
                 "created_at": "2026-01-01", "status": "ready"}]

    monkeypatch.setattr(dw, "list_wishes_with_steps", fake_list)
    from auth import require_user
    mod.app.dependency_overrides[require_user] = lambda: {
        "id": "user-a", "email": "a@example.com"}
    rows = _client(mod).get("/api/wishes").json()
    assert seen["owner"] == "user-a"
    assert [r["id"] for r in rows] == ["w1"]


def test_signup_validates_input(monkeypatch):
    mod = _load_main()
    c = _client(mod)
    assert c.post("/api/auth/signup", json={
        "email": "not-an-email", "password": "123456"}).status_code == 400
    assert c.post("/api/auth/signup", json={
        "email": "ok@example.com", "password": "123"}).status_code == 400


def test_build_quota_blocks_fourth_build(monkeypatch):
    monkeypatch.setenv("DAILY_BUILD_LIMIT", "3")
    import quotas

    class FakeResult:
        count = 3
        data = [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}]

    class FakeQuery:
        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def gte(self, *a, **k):
            return self

        def execute(self):
            return FakeResult()

    class FakeClient:
        def table(self, name):
            assert name == "build_events"
            return FakeQuery()

    monkeypatch.setattr(quotas, "_client", lambda: FakeClient())
    with pytest.raises(Exception) as exc:
        quotas.check_build_quota({"id": "user-a"})
    assert getattr(exc.value, "status_code", None) == 429
    assert "3 builds per day" in str(exc.value.detail)


def test_build_quota_records_under_limit(monkeypatch):
    monkeypatch.setenv("DAILY_BUILD_LIMIT", "3")
    import quotas

    inserted = []

    class FakeResult:
        count = 2
        data = [{"id": "e1"}, {"id": "e2"}]

    class FakeQuery:
        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def gte(self, *a, **k):
            return self

        def insert(self, row):
            inserted.append(row)

            class R:
                data = [{"id": "new"}]

                def execute(self):
                    return self
            return R()

        def execute(self):
            return FakeResult()

    class FakeClient:
        def table(self, name):
            return FakeQuery()

    monkeypatch.setattr(quotas, "_client", lambda: FakeClient())
    quotas.consume_build({"id": "user-a"}, wish_id="w1", kind="build")
    assert inserted and inserted[0]["owner"] == "user-a"
    assert inserted[0]["wish_id"] == "w1"
