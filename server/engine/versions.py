"""
Spec version tree (Phase 4, P4.4; persists to project_versions in P4.5/Phase 7).

Each version pins a full spec snapshot + the patch from its parent + a human
summary (chat edits show human diffs; the JSON Patch sits behind Details).
The service is deliberately unopinionated: callers run G0/G1 on the result.
Storage here is in-memory; Supabase persistence lands with the control-plane
tables (migration 006) — the API (create/get/apply_patch/history) is stable.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid

from engine.patch import apply, invert


def spec_hash(spec: dict) -> str:
    raw = json.dumps(spec, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


class VersionTree:
    def __init__(self):
        self.versions: dict = {}

    def create(self, spec: dict, *, source: str = "generate") -> str:
        """Pin the first version. Returns the version id."""
        if source not in ("generate", "iterate", "manual", "import"):
            raise ValueError(f"bad source: {source!r}")
        vid = uuid.uuid4().hex[:12]
        self.versions[vid] = {
            "id": vid,
            "parent": None,
            "spec": copy.deepcopy(spec),
            "hash": spec_hash(spec),
            "patch": [],
            "summary": "initial version",
            "source": source,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        return vid

    def apply_patch(self, vid: str, ops: list, summary: str,
                    *, source: str = "iterate") -> str:
        """Validate ops against the pinned spec, store child version. Fail-fast."""
        if vid not in self.versions:
            raise KeyError(f"unknown version: {vid}")
        if not summary or not summary.strip():
            raise ValueError("summary required (chat shows human diffs)")
        base = self.versions[vid]["spec"]
        try:
            new_spec = apply(base, ops)
        except Exception as e:
            raise ValueError(f"patch rejected: {e}")
        child = uuid.uuid4().hex[:12]
        self.versions[child] = {
            "id": child,
            "parent": vid,
            "spec": new_spec,
            "hash": spec_hash(new_spec),
            "patch": copy.deepcopy(ops),
            "inverse_patch": invert(base, ops),
            "summary": summary.strip(),
            "source": source,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        return child

    def get(self, vid: str) -> dict:
        if vid not in self.versions:
            raise KeyError(f"unknown version: {vid}")
        return copy.deepcopy(self.versions[vid]["spec"])

    def undo(self, vid: str, summary: str = "undo") -> str:
        """New child version restoring the parent spec (undo = switch to parent)."""
        if vid not in self.versions:
            raise KeyError(f"unknown version: {vid}")
        parent = self.versions[vid]["parent"]
        if parent is None:
            raise ValueError("root version has nothing to undo")
        return self.apply_patch(vid, self.versions[vid].get("inverse_patch") or [],
                                summary, source="iterate")

    def history(self, vid: str) -> list:
        """Version ids root → vid."""
        if vid not in self.versions:
            raise KeyError(f"unknown version: {vid}")
        chain = []
        cur: str | None = vid
        while cur is not None:
            chain.append(cur)
            cur = self.versions[cur]["parent"]
        chain.reverse()
        return chain
