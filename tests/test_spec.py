"""
Spec gates — Phase 4 P4.1/P4.2. No network, no keys.
- G0: golds + base validate clean; bad type / missing required fail
- G1: golds pass with zero errors; every fail-patch fixture yields its rule(s);
  experimental block warns without failing
- Drift: scripts/gen_spec_types.py --check is green (schema ↔ generated types)
Run: pytest tests/test_spec.py -v
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)

SPEC = os.path.join(ROOT, "packages", "spec")
FIX = os.path.join(SPEC, "fixtures")


def _load(name):
    with open(os.path.join(SPEC, "exemplars", name)) as f:
        return json.load(f)


def _base():
    with open(os.path.join(FIX, "base.json")) as f:
        return json.load(f)


def test_g0_golds_and_base_pass():
    from gates.g0_validate import validate
    assert validate(_base()) == []
    assert validate(_load("repair-tracker.json")) == []
    assert validate(_load("inventory.json")) == []


def test_g0_rejects_bad_shape():
    from gates.g0_validate import validate
    import copy
    bad_type = _base()
    bad_type["model"]["entities"][0]["fields"][0]["type"] = "textarea"
    errs = validate(bad_type)
    assert errs, "closed field-type set must reject textarea"
    missing = _base()
    del missing["app"]["name"]
    assert validate(missing), "required app.name must fail"
    missing_root = _base()
    del missing_root["ui"]
    assert validate(missing_root), "required ui must fail"


def test_g1_golds_and_base_clean():
    from gates.g1_lint import lint
    assert lint(_base())["errors"] == []
    for name in ("repair-tracker.json", "inventory.json"):
        res = lint(_load(name))
        assert res["errors"] == [], f"{name}: {res['errors'][:3]}"


def test_g1_fail_patches_yield_their_rules():
    from gates.g1_lint import lint
    from engine.patch import apply
    with open(os.path.join(FIX, "fail-patches.json")) as f:
        suite = json.load(f)["cases"]
    assert len(suite) >= 36, "one failing fixture per rule (≥25 required)"
    for case in suite:
        broken = apply(_base(), case["ops"])
        res = lint(broken)
        got_errors = {e["rule"] for e in res["errors"]}
        got_warns = {w["rule"] for w in res["warnings"]}
        for rule in case.get("rules", []):
            assert rule in got_errors, f"{case['id']}: want {rule}, got {sorted(got_errors)}"
        for rule in case.get("warnings", []):
            assert rule in got_warns, f"{case['id']}: want warning {rule}"
        if case["id"] == "w01-experimental-warn":
            assert res["errors"] == [], "warnings must never fail the gate"


def test_gen_types_drift_check_green():
    r = subprocess.run([sys.executable, "scripts/gen_spec_types.py", "--check"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"drift:\n{r.stdout}\n{r.stderr}"


def test_migration_006_additive_only():
    sql = open(os.path.join(ROOT, "supabase", "migrations", "006_v2_control_plane.sql")).read().lower()
    for table in ("projects", "project_versions", "runs", "run_steps",
                  "run_events", "exemplars", "feedback"):
        assert f"create table if not exists {table}" in sql, table
    assert "llm_calls_run_id_fkey" in sql, "006a run_id FK lands here"
    for banned in ("alter table wishes", "alter table wish_steps", "drop table",
                   "delete from", "create table if not exists apps",
                   "create table if not exists records"):
        assert banned not in sql, f"migration must not contain: {banned}"


def test_prd_adapter_legacy_fixtures_pass_gates():
    """P5.1: all 5 legacy golden PRDs adapt to G0/G1-clean App Specs."""
    from engine.prd_adapter import adapt_prd
    from gates.g0_validate import validate
    from gates.g1_lint import lint
    with open(os.path.join(ROOT, "tests", "fixtures", "wishes.json")) as f:
        wishes = json.load(f)
    assert len(wishes) == 5
    for w in wishes:
        spec = adapt_prd(w["prd"], w["prompt"])
        g0 = validate(spec)
        assert g0 == [], f"{w['id']} G0: {g0[:3]}"
        res = lint(spec)
        assert res["errors"] == [], f"{w['id']} G1: {res['errors'][:3]}"
