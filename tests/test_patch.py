"""
JSON Patch + version tree — Phase 4 P4.4. No network, no keys.
- RFC 6902 ops incl. escapes, array append, move/copy/test; errors on miss
- Property test: apply(p) then apply(invert(p)) == original (fixed guide-style
  patch + 200 randomized patches)
- VersionTree: create/patch/get/history/undo; rejects bad patches + empty summaries
Run: pytest tests/test_patch.py -v
"""
import copy
import os
import random
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
if SRV not in sys.path:
    sys.path.insert(0, SRV)

from engine.patch import apply, invert, PatchError  # noqa: E402


def test_apply_basics():
    doc = {"a": 1, "b": [1, 2], "c": {"d": "x"}}
    out = apply(doc, [
        {"op": "add", "path": "/e", "value": 5},
        {"op": "add", "path": "/b/-", "value": 3},
        {"op": "replace", "path": "/c/d", "value": "y"},
        {"op": "move", "from": "/a", "path": "/c/a"},
        {"op": "copy", "from": "/c/d", "path": "/c/e"},
        {"op": "test", "path": "/c/d", "value": "y"},
    ])
    assert out == {"b": [1, 2, 3], "c": {"d": "y", "a": 1, "e": "y"}, "e": 5}
    assert doc == {"a": 1, "b": [1, 2], "c": {"d": "x"}}, "apply must not mutate"


def test_pointer_escapes_and_indexes():
    doc = {"a/b": {"~key": [10]}, "arr": [{"n": 1}]}
    assert apply(doc, [{"op": "test", "path": "/a~1b/~0key/0", "value": 10}]) == doc
    out = apply(doc, [{"op": "replace", "path": "/arr/0/n", "value": 2}])
    assert out["arr"] == [{"n": 2}]


def test_apply_errors():
    doc = {"a": 1}
    with pytest.raises(PatchError):
        apply(doc, [{"op": "remove", "path": "/missing"}])
    with pytest.raises(PatchError):
        apply(doc, [{"op": "test", "path": "/a", "value": 2}])
    with pytest.raises(PatchError):
        apply(doc, [{"op": "frobnicate", "path": "/a"}])
    with pytest.raises(PatchError):
        apply(doc, [{"op": "add", "path": "a", "value": 1}])
    with pytest.raises(PatchError):
        apply(doc, "not-a-list")


def test_guide_style_patch_round_trip():
    """§4.3 example: add a field + a block prop, then undo."""
    doc = {"model": {"entities": {"job": {"fields": []}}}, "ui": {"pages": []}}
    patch = [
        {"op": "add", "path": "/model/entities/job/fields/-",
         "value": {"id": "due_date", "type": "date"}},
        {"op": "add", "path": "/ui/pages/-",
         "value": {"id": "jobs", "blocks": []}},
    ]
    after = apply(doc, patch)
    assert after["model"]["entities"]["job"]["fields"][0]["id"] == "due_date"
    assert apply(after, invert(doc, patch)) == doc


def _all_paths(doc, base=""):
    paths = []
    if isinstance(doc, dict):
        for k, v in doc.items():
            p = f"{base}/{k}"
            paths.append((p, v))
            paths += _all_paths(v, p)
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            p = f"{base}/{i}"
            paths.append((p, v))
            paths += _all_paths(v, p)
    return paths


def _random_patch(rng, doc):
    ops = []
    live = copy.deepcopy(doc)
    for _ in range(rng.randint(1, 5)):
        paths = _all_paths(live)
        kind = rng.choice(["add", "remove", "replace", "move", "copy", "test"])
        try:
            if kind in ("remove", "replace", "test") and paths:
                p, v = rng.choice(paths)
                if kind == "remove":
                    ops.append({"op": "remove", "path": p})
                elif kind == "replace":
                    ops.append({"op": "replace", "path": p, "value": rng.randint(0, 99)})
                else:
                    ops.append({"op": "test", "path": p, "value": copy.deepcopy(v)})
            elif kind == "add":
                containers = [(p, v) for p, v in paths
                              if isinstance(v, (dict, list))] + [("", live)]
                p, v = rng.choice(containers)
                if isinstance(v, list):
                    ops.append({"op": "add", "path": f"{p}/-",
                                "value": rng.randint(0, 99)})
                else:
                    ops.append({"op": "add", "path": f"{p}/k{rng.randint(0, 9)}",
                                "value": rng.randint(0, 99)})
            elif kind in ("move", "copy") and paths:
                p, v = rng.choice(paths)
                dests = [(q, w) for q, w in paths if isinstance(w, (dict, list))]
                if not dests:
                    continue
                q, w = rng.choice(dests)
                if isinstance(w, list):
                    op = {"op": kind, "from": p, "path": f"{q}/-"}
                else:
                    op = {"op": kind, "from": p, "path": f"{q}/m{rng.randint(0, 9)}"}
                # never move a node into itself
                if op["path"].startswith(p + "/") or p.startswith(op["path"] + "/"):
                    continue
                ops.append(op)
            else:
                continue
            live = apply(live, ops[-1:])
        except PatchError:
            if ops and kind in ("remove", "replace", "test", "move", "copy", "add"):
                # op failed against live doc — drop it and continue fuzzing
                ops.pop()
            continue
    return ops


def test_round_trip_property_randomized():
    seed_doc = {"a": [1, {"b": "x", "c": [True, None]}], "d": {"e": 2.5}}
    rng = random.Random(44)
    for i in range(200):
        doc = copy.deepcopy(seed_doc)
        ops = _random_patch(rng, doc)
        if not ops:
            continue
        after = apply(doc, ops)
        assert apply(after, invert(doc, ops)) == doc, f"iter {i}: {ops}"


def test_version_tree_lifecycle():
    from engine.versions import VersionTree
    t = VersionTree()
    v1 = t.create({"n": 1}, source="manual")
    assert t.get(v1) == {"n": 1}
    assert t.history(v1) == [v1]
    v2 = t.apply_patch(v1, [{"op": "add", "path": "/m", "value": 2}], "add m")
    assert t.get(v2) == {"n": 1, "m": 2}
    assert t.history(v2) == [v1, v2]
    v3 = t.undo(v2, "revert add m")
    assert t.get(v3) == {"n": 1}
    assert t.history(v3) == [v1, v2, v3]
    # stored patch + inverse survive
    assert t.versions[v2]["patch"][0]["op"] == "add"
    assert t.versions[v2]["inverse_patch"][0]["op"] == "remove"


def test_version_tree_rejects():
    from engine.versions import VersionTree
    t = VersionTree()
    v1 = t.create({"n": 1})
    with pytest.raises(ValueError):
        t.apply_patch(v1, [{"op": "remove", "path": "/missing"}], "bad op")
    with pytest.raises(ValueError):
        t.apply_patch(v1, [{"op": "add", "path": "/x", "value": 1}], "  ")
    with pytest.raises(KeyError):
        t.get("nope")
    with pytest.raises(ValueError):
        t.undo(v1)
