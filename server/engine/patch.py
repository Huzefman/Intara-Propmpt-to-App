"""
JSON Patch (RFC 6902) apply + invert for App Spec editing (Phase 4, P4.4).

Iteration edits are precise patches (guide §4.3), never string surgery:
  add /model/entities/job/fields/- · remove /ui/pages/old · …
apply() is immutable (deep-copies). invert() computes the undo patch against
the pre-image document, so apply(apply(doc, p), invert(doc, p)) == doc —
enforced by the round-trip property test.
"""
from __future__ import annotations

import copy


class PatchError(ValueError):
    pass


def parse_pointer(ptr: str) -> list:
    """Split a JSON Pointer into segments (array indices as ints)."""
    if not isinstance(ptr, str):
        raise PatchError(f"bad path: {ptr!r}")
    if ptr == "":
        return []
    if not ptr.startswith("/"):
        raise PatchError(f"path must start with /: {ptr!r}")
    parts: list = []
    for seg in ptr.split("/")[1:]:
        seg = seg.replace("~1", "/").replace("~0", "~")
        if seg.isdigit() and seg != "":
            parts.append(int(seg))
        else:
            parts.append(seg)
    return parts


def _is_index(seg) -> bool:
    return isinstance(seg, int)


def _resolve(doc, parts: list, *, create_missing: bool = False):
    """Return (container, last) for parts. Raises PatchError on miss."""
    if not parts:
        return (None, None)
    cur = doc
    for seg in parts[:-1]:
        if isinstance(cur, dict) and isinstance(seg, str):
            if seg not in cur:
                if create_missing:
                    cur[seg] = {}
                else:
                    raise PatchError(f"path miss: {seg!r}")
            cur = cur[seg]
        elif isinstance(cur, list) and _is_index(seg):
            if seg < 0 or seg >= len(cur):
                raise PatchError(f"index out of range: {seg}")
            cur = cur[seg]
        else:
            raise PatchError(f"cannot descend into {type(cur).__name__} at {seg!r}")
    return cur, parts[-1]


def _get(doc, parts: list):
    if not parts:
        return doc
    parent, last = _resolve(doc, parts)
    if isinstance(parent, dict):
        if not isinstance(last, str) or last not in parent:
            raise PatchError(f"path miss: {last!r}")
        return parent[last]
    if isinstance(parent, list):
        if not _is_index(last) or last < 0 or last >= len(parent):
            raise PatchError(f"index out of range: {last!r}")
        return parent[last]
    raise PatchError("bad target")


def _add(doc, parts: list, value):
    if not parts:
        raise PatchError("add to root requires replace")
    parent, last = _resolve(doc, parts)
    if isinstance(parent, dict):
        if not isinstance(last, str):
            raise PatchError(f"bad key: {last!r}")
        parent[last] = value
    elif isinstance(parent, list):
        if last == "-" or last == "−":
            parent.append(value)
        elif _is_index(last) and 0 <= last <= len(parent):
            parent.insert(last, value)
        else:
            raise PatchError(f"index out of range: {last!r}")
    else:
        raise PatchError("bad target")


def _remove(doc, parts: list):
    if not parts:
        raise PatchError("remove root requires replace with null")
    parent, last = _resolve(doc, parts)
    if isinstance(parent, dict):
        if not isinstance(last, str) or last not in parent:
            raise PatchError(f"path miss: {last!r}")
        del parent[last]
    elif isinstance(parent, list):
        if not _is_index(last) or last < 0 or last >= len(parent):
            raise PatchError(f"index out of range: {last!r}")
        parent.pop(last)
    else:
        raise PatchError("bad target")


def apply(doc: dict | list, ops: list) -> dict | list:
    """Apply RFC 6902 ops to a deep copy of doc. Raises PatchError."""
    if not isinstance(ops, list):
        raise PatchError("patch must be a list of ops")
    out = copy.deepcopy(doc)
    for op in ops:
        if not isinstance(op, dict):
            raise PatchError(f"bad op: {op!r}")
        kind = op.get("op")
        path = parse_pointer(op.get("path", ""))
        if kind == "add":
            if "value" not in op:
                raise PatchError("add needs value")
            _add(out, path, copy.deepcopy(op["value"]))
        elif kind == "remove":
            _remove(out, path)
        elif kind == "replace":
            if "value" not in op:
                raise PatchError("replace needs value")
            _get(out, path)  # must exist
            if not path:
                out = copy.deepcopy(op["value"])
            else:
                parent, last = _resolve(out, path)
                if isinstance(parent, dict):
                    parent[last] = copy.deepcopy(op["value"])
                else:
                    parent[last] = copy.deepcopy(op["value"])
        elif kind == "move":
            frm = parse_pointer(op.get("from", ""))
            val = copy.deepcopy(_get(out, frm))
            _remove(out, frm)
            _add(out, path, val)
        elif kind == "copy":
            frm = parse_pointer(op.get("from", ""))
            _add(out, path, copy.deepcopy(_get(out, frm)))
        elif kind == "test":
            if "value" not in op:
                raise PatchError("test needs value")
            if _get(out, path) != op["value"]:
                raise PatchError(f"test failed at {op.get('path')}")
        else:
            raise PatchError(f"unknown op: {kind!r}")
    return out


def _concrete(doc, parts: list) -> list:
    """Resolve a trailing "-" (array append) to its concrete index in doc."""
    if not parts or parts[-1] != "-":
        return list(parts)
    if len(parts) == 1:
        raise PatchError("cannot append to root")
    grandparent, lastkey = _resolve(doc, parts[:-1])
    if isinstance(grandparent, dict) and isinstance(lastkey, str):
        target = grandparent.get(lastkey)
    elif isinstance(grandparent, list) and _is_index(lastkey):
        target = grandparent[lastkey] if 0 <= lastkey < len(grandparent) else None
    else:
        target = None
    if not isinstance(target, list):
        raise PatchError("append target is not a list")
    return parts[:-1] + [len(target)]


def invert(doc: dict | list, ops: list) -> list:
    """Compute the undo patch for ops against the pre-image doc.

    Simulates application so "-" appends resolve to concrete indices, then
    reverses: apply(apply(doc, p), invert(doc, p)) == doc.
    """
    if not isinstance(ops, list):
        raise PatchError("patch must be a list of ops")
    working = copy.deepcopy(doc)
    undos: list = []

    def _exists(parts: list) -> bool:
        try:
            _get(working, parts)
            return True
        except PatchError:
            return False

    def _fmt(parts: list) -> str:
        return "" if not parts else "/" + "/".join(
            str(p).replace("~", "~0").replace("/", "~1") for p in parts)

    for op in ops:
        if not isinstance(op, dict):
            raise PatchError(f"bad op: {op!r}")
        kind = op.get("op")
        path = parse_pointer(op.get("path", ""))
        if kind == "add":
            if "value" not in op:
                raise PatchError("add needs value")
            concrete = _concrete(working, path)
            if _exists(concrete):
                # overwriting add: undo restores the old value, not remove
                undos.append({"op": "replace", "path": _fmt(concrete),
                              "value": copy.deepcopy(_get(working, concrete))})
            else:
                undos.append({"op": "remove", "path": _fmt(concrete)})
            _add(working, concrete, copy.deepcopy(op["value"]))
        elif kind == "remove":
            concrete = _concrete(working, path)
            undos.append({"op": "add", "path": _fmt(concrete),
                          "value": copy.deepcopy(_get(working, concrete))})
            _remove(working, concrete)
        elif kind == "replace":
            if "value" not in op:
                raise PatchError("replace needs value")
            concrete = _concrete(working, path)
            undos.append({"op": "replace", "path": _fmt(concrete),
                          "value": copy.deepcopy(_get(working, concrete))})
            _remove(working, concrete)
            _add(working, concrete, copy.deepcopy(op["value"]))
        elif kind == "move":
            frm = _concrete(working, parse_pointer(op.get("from", "")))
            val = copy.deepcopy(_get(working, frm))
            _remove(working, frm)
            concrete = _concrete(working, path)
            if _exists(concrete):
                # move overwrites: unwind = move back, then restore victim.
                # (appended reversed: global reverse restores execution order)
                undos.append({"op": "replace", "path": _fmt(concrete),
                              "value": copy.deepcopy(_get(working, concrete))})
                undos.append({"op": "move", "from": _fmt(concrete), "path": _fmt(frm)})
            else:
                undos.append({"op": "move", "from": _fmt(concrete), "path": _fmt(frm)})
            _add(working, concrete, val)
        elif kind == "copy":
            frm = _concrete(working, parse_pointer(op.get("from", "")))
            concrete = _concrete(working, path)
            if _exists(concrete):
                undos.append({"op": "replace", "path": _fmt(concrete),
                              "value": copy.deepcopy(_get(working, concrete))})
            else:
                undos.append({"op": "remove", "path": _fmt(concrete)})
            _add(working, concrete, copy.deepcopy(_get(working, frm)))
        elif kind == "test":
            if "value" not in op:
                raise PatchError("test needs value")
            if _get(working, _concrete(working, path)) != op["value"]:
                raise PatchError(f"test failed at {op.get('path')}")
            undos.append({"op": "test", "path": op.get("path", ""),
                          "value": copy.deepcopy(op.get("value"))})
        else:
            raise PatchError(f"unknown op: {kind!r}")
    undos.reverse()
    return undos
