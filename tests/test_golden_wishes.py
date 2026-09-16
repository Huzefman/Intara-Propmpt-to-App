"""
Intara — Golden Wishes pytest suite
Mocked fixtures, $0, runs in CI.
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from eval import eval_wish  # type: ignore

FIXTURE = ROOT / "tests" / "fixtures" / "wishes.json"

def load_wishes():
    return json.loads(FIXTURE.read_text())

def test_all_wishes_pass():
    wishes = load_wishes()
    assert len(wishes) == 5, "expect 5 golden wishes"
    for w in wishes:
        overall, results = eval_wish(w)
        fails = {k: msg for k, (ok, msg) in results.items() if not ok}
        assert overall, f"{w['id']} failed: {fails}"

def test_each_wish_individually():
    wishes = load_wishes()
    for idx, w in enumerate(wishes, 1):
        overall, results = eval_wish(w)
        assert overall, f"wish {idx} {w['id']} failed: {results}"

def test_schema_types_allowed():
    wishes = load_wishes()
    for w in wishes:
        tables = w["artifacts"]["schema"]["tables"]
        for t in tables:
            for f in t["fields"]:
                assert f["type"] in {"text","integer","timestamp","boolean"}, f"bad type {f}"

def test_frontend_has_pages():
    wishes = load_wishes()
    for w in wishes:
        files = w["artifacts"]["frontend"]["files"]
        assert any("pages/" in f["path"] for f in files), f"{w['id']} no pages"
