"""
Formula conformance + fuzz — Phase 4 P4.3. No network, no keys.
- Shared packages/spec/formula/formula-cases.json through the Python impl
- Fuzz: 500 garbage inputs → only FormulaSyntaxError escapes parse; only
  FormulaError escapes evaluate; process never crashes
- No eval/exec/compile in either implementation
- TypeScript twin runs the same file via node --test (skipped if node absent)
Run: pytest tests/test_formula.py -v
"""
import json
import os
import random
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)

CASES = os.path.join(ROOT, "packages", "spec", "formula", "formula-cases.json")


def _cases():
    with open(CASES) as f:
        return json.load(f)["cases"]


def test_shared_cases_through_python():
    from engine.formula import evaluate, FormulaSyntaxError, FormulaError
    cases = _cases()
    assert len(cases) >= 100, "≥100 conformance cases required"
    for c in cases:
        want_err = c.get("expect_error")
        try:
            got = evaluate(c["formula"], record=c.get("record") or {},
                           related=c.get("related") or {}, now=c.get("now"))
        except Exception as e:
            assert want_err, f"{c['id']}: unexpected {type(e).__name__}: {e}"
            if want_err == "syntax":
                assert type(e) is FormulaSyntaxError, f"{c['id']}: {type(e).__name__}"
            else:
                assert type(e) is FormulaError, f"{c['id']}: {type(e).__name__}"
            continue
        assert not want_err, f"{c['id']}: expected {want_err}, got {got!r}"
        assert got == c["expect"], f"{c['id']}: {got!r} != {c['expect']!r}"


def test_fuzz_garbage_never_escapes():
    from engine.formula import parse, evaluate, FormulaSyntaxError, FormulaError
    rng = random.Random(406)
    pieces = ["qty", "parts.total", "(", ")", ",", ".", "+", "-", "*", "/", "%",
              "==", "!=", "<", ">", "and", "or", "not", "if", "sum", "1", "2.5",
              "'a", "'a'", '"b', "true", "null", " ", "_", "@", "[", "]", "\\",
              "startOfMonth(", "len(", "customer.email"]
    for i in range(500):
        src = "".join(rng.choice(pieces) for _ in range(rng.randint(1, 8)))
        try:
            node = parse(src)
        except FormulaSyntaxError:
            continue
        except Exception as e:
            pytest.fail(f"fuzz parse escaped {type(e).__name__}: {src!r}: {e}")
        assert isinstance(node, (list, tuple)), f"AST must be a tuple: {src!r}"
        try:
            evaluate(src, record={"qty": 2, "customer": {"email": "a"}},
                     related={"parts": [{"total": 1}]})
        except (FormulaSyntaxError, FormulaError):
            pass
        except Exception as e:
            pytest.fail(f"fuzz eval escaped {type(e).__name__}: {src!r}: {e}")


def test_no_eval_in_implementations():
    import re
    # standalone calls only (_eval/evaluate are fine; eval/exec/compile/Function are not)
    banned = re.compile(r"(?<![\w.'])(eval|exec|compile|Function)\s*\(")
    for rel in ("server/engine/formula.py", "packages/spec/formula/formula.ts"):
        src = open(os.path.join(ROOT, rel)).read()
        m = banned.search(src)
        assert not m, f"{rel} contains forbidden {m.group(1)}("


def test_typescript_twin_passes_shared_cases():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    from tests._nodeutil import node_cmd
    r = subprocess.run(node_cmd("--test", "packages/spec/formula/formula.test.ts"),
                       cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"node --test failed:\n{r.stdout[-2000:]}\n{r.stderr[-500:]}"
    assert "fail 0" in r.stdout, r.stdout[-500:]
