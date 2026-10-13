"""
Agents + G2 tests — Phase 7 P7.2/P7.3. No network, no keys (mocked transports).
- run_agent: happy path, repair loop, exhausted→degraded fallback,
  transport failure→degraded, quota propagates (no repair burn)
- stages registry shape (agent/version/tier/model/prompt/fallback)
- prompts carry schema + untrusted delimiter
- assemble_spec produces G0-clean specs; G2 coverage semantics
- edit agent parses patch; invalid edit raises (no silent fallback)
Run: pytest tests/test_agents.py -v
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)


def _caller_factory(script):
    """script: list of (text, meta) or Exception, consumed per call."""
    calls = {"n": 0}

    def _call(prompt, temperature=0.2, **kw):
        info = kw.get("info")
        item = script[min(calls["n"], len(script) - 1)]
        calls["n"] += 1
        if isinstance(item, Exception):
            raise item
        text, meta = item
        if info is not None:
            info.update({"provider": "mock", "model": "mock",
                         "finish_reason": "stop"})
        tele = kw.get("telemetry")
        if tele is not None and isinstance(tele, dict):
            calls.setdefault("tele", []).append(dict(tele))
        return text, meta

    _call.calls = calls
    return _call


S2_OK = {"model": {"enums": [], "entities": [
    {"id": "widget", "label": "Widget",
     "fields": [{"id": "name", "type": "text", "required": True}],
     "display": {"title": "{name}"}}]}}


def _run_s2(caller, **kw):
    from agents.base import run_agent
    from agents.stages import STAGES
    st = STAGES["s2"]
    payload = {"wish": "widgets", "answers": "", "assumptions": [],
               "exemplars": "", "entity_ids": []}
    return run_agent(stage=st["agent"], prompt_version="s2-v1",
                     prompt=st["prompt"](payload), output_model=st["model"],
                     fallback_fn=lambda: st["fallback"](payload),
                     gate_fn=lambda o: st["gate"](o, payload),
                     caller=caller, **kw)


def test_agent_happy_path():
    caller = _caller_factory([(json.dumps(S2_OK), {"source": "mock", "model": "m"})])
    res = _run_s2(caller)
    assert res.ok and not res.degraded
    assert res.output.model.entities[0].id == "widget"
    assert res.parse_outcome == "ok" and res.llm_calls == 1
    assert caller.calls["tele"][0]["agent"] == "s2-modeler"


def test_agent_repair_loop_then_valid():
    bad = {"model": {"enums": [], "entities": [
        {"id": "widget", "label": "W",
         "fields": [{"id": "owner", "type": "ref", "target": "nope"}]}]}}
    caller = _caller_factory([(json.dumps(bad), {}), (json.dumps(S2_OK), {})])
    res = _run_s2(caller)
    assert res.ok and not res.degraded and res.repair_used
    assert res.parse_outcome == "llm_repaired" and res.llm_calls == 2


def test_agent_exhausted_repairs_degraded_fallback():
    bad = {"model": {"enums": [], "entities": []}}
    caller = _caller_factory([(json.dumps(bad), {})] * 4)
    res = _run_s2(caller, max_repairs=1)
    assert res.ok and res.degraded
    assert res.output["model"]["entities"][0]["id"] == "record"
    assert res.fallback_reason and res.llm_calls == 2


def test_agent_transport_failure_degraded():
    caller = _caller_factory([RuntimeError("connection reset")])
    res = _run_s2(caller)
    assert res.ok and res.degraded and res.parse_outcome == "failed"
    assert "connection reset" in (res.fallback_reason or "")


def test_agent_quota_propagates_without_burn():
    caller = _caller_factory([RuntimeError("429 quota exhausted")])
    with pytest.raises(RuntimeError, match="429"):
        _run_s2(caller)
    assert caller.calls["n"] == 1, "no repair loop on empty quota"


def test_stages_registry_shape():
    from agents.stages import STAGES
    from agents.prompts import PROMPT_VERSIONS, TIERS
    assert set(STAGES) == {"s0", "s1", "s2", "s3", "s4", "s5critic", "s6", "edit"}
    versions = set()
    for key, st in STAGES.items():
        for field in ("agent", "tier", "model", "prompt", "fallback"):
            assert field in st, f"{key} missing {field}"
        assert st["tier"] in ("fast", "strong")
        assert key in PROMPT_VERSIONS and key in TIERS
        assert TIERS[key] == st["tier"]
        versions.add(PROMPT_VERSIONS[key])
        prompt = st["prompt"]({"wish": "x", "clean_wish": "x", "answers": "",
                               "assumptions": [], "domains": "", "exemplars": "",
                               "model_json": "{}", "entity_ids": [], "personas": "",
                               "blocks": "", "ui_summary": "", "actions": "",
                               "requirements_json": "[]", "requirement_ids": [],
                               "spec_summary": "", "domain": "", "locale": "en",
                               "instruction": "do x", "spec_slice": "{}",
                               "chat_context": ""})
        assert "Return ONLY JSON" in prompt, f"{key} prompt missing schema block"
    assert len(versions) == len(STAGES), "prompt versions must be unique per stage"


def test_assemble_spec_g0_clean():
    from agents.stages import assemble_spec
    from gates.g0_validate import validate
    gold = json.load(open(os.path.join(
        ROOT, "packages", "spec", "exemplars", "inventory.json")))
    parts = {"app": gold["app"], "personas": gold.get("personas", []),
             "requirements": gold.get("requirements", []),
             "assumptions": gold.get("assumptions", []),
             "model": gold["model"], "access": gold["access"], "ui": gold["ui"],
             "automations": gold.get("automations", []),
             "seed": gold.get("seed", {}), "trace": gold.get("trace", [])}
    spec = assemble_spec(parts)
    assert validate(spec) == []
    assert spec["spec_version"] == "1.0"


def test_g2_coverage_semantics():
    from gates.g2_coverage import check
    reqs = [{"id": "R1", "priority": "must"}, {"id": "R2", "priority": "should"},
            {"id": "R3", "priority": "must"}]
    trace = [{"requirement": "R1", "satisfied_by": ["entity:x"]},
             {"requirement": "R2", "satisfied_by": []}]
    res = check(reqs, trace)
    assert res["missing_must"] == ["R3"]
    assert res["missing_should"] == ["R2"], "empty satisfied_by counts as uncovered"
    assert res["covered"] == ["R1"]
    full = check(reqs, trace + [{"requirement": "R3", "satisfied_by": ["page:y"]}])
    assert full["missing_must"] == []


def test_edit_agent_patch_and_no_fallback():
    from agents.base import run_agent
    from agents.stages import STAGES
    st = STAGES["edit"]
    payload = {"instruction": "add field", "spec_slice": "{}"}
    good = {"patch": [{"op": "add", "path": "/x", "value": 1}], "summary": "added x"}
    caller = _caller_factory([(json.dumps(good), {})])
    res = run_agent(stage=st["agent"], prompt_version="edit-v1",
                    prompt=st["prompt"](payload), output_model=st["model"],
                    fallback_fn=lambda: st["fallback"](payload), caller=caller)
    assert res.ok and res.output.patch[0]["op"] == "add"
    bad_caller = _caller_factory([(json.dumps({"nope": 1}), {})] * 3)
    with pytest.raises(RuntimeError, match="no safe fallback"):
        run_agent(stage=st["agent"], prompt_version="edit-v1",
                  prompt=st["prompt"](payload), output_model=st["model"],
                  fallback_fn=lambda: st["fallback"](payload),
                  caller=bad_caller, max_repairs=1)


def test_s4_gate_catches_unknown_page_role():
    from agents.stages import STAGES
    st = STAGES["s4"]
    out = st["model"](access={"roles": [{"id": "admin"}],
                              "rules": [{"entity": "*", "role": "admin",
                                         "ops": ["read"]}]},
                      automations=[])
    errs = st["gate"](out, {"entity_ids": set(), "page_roles_list": ["owner"],
                            "entity_fields": {}})
    assert any("admin" in e and "page" in e for e in errs), errs


def test_s2_gate_catches_bad_lifecycle_states():
    from agents.stages import STAGES
    st = STAGES["s2"]
    out = st["model"](model={
        "enums": [{"id": "st", "values": [{"value": "a", "label": "A"}]}],
        "entities": [{"id": "w", "label": "W",
                      "fields": [{"id": "s", "type": "enum", "enum": "st"}],
                      "lifecycle": {"field": "s", "initial": "a",
                                    "transitions": [
                                        {"id": "t1", "from": "any", "to": "a",
                                         "label": "T", "roles": []}]}}]})
    errs = st["gate"](out, {})
    assert any("any" in e for e in errs), errs


def test_s4_gate_enforces_role_subset_and_field_refs():
    from agents.stages import STAGES
    st = STAGES["s4"]
    out = st["model"](
        access={"roles": [{"id": "approver"}],
                "rules": [{"entity": "*", "role": "approver", "ops": ["read"]}]},
        automations=[{"id": "a1",
                      "trigger": {"type": "record.updated", "entity": "doc"},
                      "steps": [{"action": "set_field",
                                 "params": {"field": "nope"}}]}])
    errs = st["gate"](out, {"entity_ids": {"doc"},
                            "page_roles_list": ["owner"],
                            "entity_fields": {"doc": ["title"]}})
    assert any("approver" in e and "page" in e for e in errs), errs
    assert any("nope" in e for e in errs), errs
    clean = st["model"](
        access={"roles": [{"id": "owner"}],
                "rules": [{"entity": "*", "role": "owner", "ops": ["read"]}]},
        automations=[])
    assert st["gate"](clean, {"entity_ids": set(), "page_roles_list": ["owner"],
                              "entity_fields": {}}) == []


def test_s3_gate_requires_owner_anchor():
    from agents.stages import STAGES
    st = STAGES["s3"]
    out = st["model"](ui={"nav": [], "pages": []})
    assert any("owner" in e for e in st["gate"](out, {"entity_ids": set()})), \
        "owner anchor required"
