#!/usr/bin/env python3
"""Seed the exemplars table from packages/spec/exemplars/*.json (Phase 5).

Upserts {name, domain, spec, spec_hash, source} — the table pins specs;
vectors live in evals/retrieval_index.json (see services/retrieval.py).
Requires SUPABASE_URL/SUPABASE_KEY (server/.env). Idempotent by name.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, "server", ".env"))

from db.wishes import _client  # noqa: E402
from engine.versions import spec_hash  # noqa: E402


def _service_client():
    """Control-plane tables are service-key only (006 RLS, no anon policies)."""
    import os
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_SERVICE_KEY required to seed exemplars")
    from supabase import create_client
    return create_client(url, key)


def main() -> int:
    supa = _service_client()
    n = 0
    for fp in sorted(glob.glob(os.path.join(ROOT, "packages", "spec", "exemplars", "*.json"))):
        spec = json.load(open(fp))
        name = os.path.basename(fp)[:-5]
        domain = (spec.get("app") or {}).get("domain") or "unknown"
        payload = {"name": name, "domain": domain, "spec": spec,
                   "spec_hash": spec_hash(spec), "source": "hand-authored"}
        res = supa.table("exemplars").upsert(payload, on_conflict="name").execute()
        if not res.data:
            raise RuntimeError(f"exemplars upsert failed for {name}")
        n += 1
        print(f"seeded {name} ({domain}) {payload['spec_hash'][:12]}")
    print(f"done: {n} exemplars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
