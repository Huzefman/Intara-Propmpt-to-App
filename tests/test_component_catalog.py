"""Component catalog contract tests.

The S3 prompt, G1 linter, and runtime renderer must agree on the exact block
set and prop vocabulary. These tests make drift a failing test, not a runtime
surprise.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)


def _catalog():
    from gates.block_catalog import BLOCKS, CATALOG, prompt_catalog
    return BLOCKS, CATALOG, prompt_catalog


def test_catalog_is_well_formed_single_source():
    blocks, catalog, prompt_catalog = _catalog()
    prompt = prompt_catalog()
    types = [b["type"] for b in catalog["blocks"]]
    assert len(types) == len(set(types)), "block types must be unique"
    assert set(types) == set(blocks)
    for b in catalog["blocks"]:
        assert b["stability"] in ("stable", "experimental")
        assert set(b["required_props"]).isdisjoint(b["optional_props"])
        assert b.get("fits"), f"{b['type']} needs a fit description"
        assert b.get("example") is not None, f"{b['type']} needs an example"
    # The prompt is generated from the same catalog, not a second hardcoded list.
    assert all(t in prompt for t in types)
    assert "recipes" in catalog
    for recipe in ["Dashboard", "Collection", "Record", "Form", "Files", "Landing"]:
        assert recipe in catalog["recipes"]
        assert recipe in prompt
    from agents.prompts import s3_prompt
    fallback_prompt = s3_prompt("{}", "", "", "", "")
    assert all(t in fallback_prompt for t in types)
    assert "Dashboard" in fallback_prompt


def test_frontend_catalog_mirror_matches_backend():
    backend = json.load(open(os.path.join(
        ROOT, "server", "data", "component_catalog.json"), encoding="utf-8"))
    frontend = json.load(open(os.path.join(
        ROOT, "packages", "spec", "component-catalog.json"), encoding="utf-8"))
    assert frontend == backend, "run scripts/sync_component_catalog.py"


def test_runtime_registry_and_component_map_match_catalog():
    blocks, _, _ = _catalog()
    registry = open(os.path.join(
        ROOT, "packages", "runtime", "blocks", "registry.ts"), encoding="utf-8").read()
    components = open(os.path.join(
        ROOT, "packages", "runtime", "blocks", "components.ts"), encoding="utf-8").read()

    registry_types = set(re.findall(
        r'"([a-z][a-z0-9_.]+)":\s*\{\s*stability', registry))
    component_types = set(re.findall(
        r'"([a-z][a-z0-9_.]+)":\s*[A-Z]', components))
    assert registry_types == set(blocks), (
        f"registry drift: {registry_types ^ set(blocks)}")
    assert component_types == set(blocks), (
        f"component map drift: {component_types ^ set(blocks)}")

    for block_type, info in blocks.items():
        m = re.search(
            rf'"{re.escape(block_type)}":\s*\{{\s*stability:\s*"(\w+)"',
            registry)
        assert m and m.group(1) == info["stability"], (
            f"{block_type} stability drift")
