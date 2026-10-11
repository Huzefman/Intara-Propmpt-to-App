#!/usr/bin/env python3
"""Seed component_defs from server/components/catalog/*.json (upsert, safe to re-run).

Requires migration 005 applied + Supabase credentials in server/.env.
Writes go through RLS, so seeding needs the SERVICE_ROLE key (the publishable
key is read-only for component_defs by design — the registry must not be
writable by anonymous clients). Set SUPABASE_SERVICE_KEY in server/.env;
never expose it in frontend/Vite env.
Usage: python scripts/seed_components.py [--dry-run]
"""
import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "server"))


def resolve_seed_credentials(_env_file=None) -> tuple[str, str, bool]:
    """Return (url, key, using_service_key). Prefers SUPABASE_SERVICE_KEY."""
    from dotenv import load_dotenv
    load_dotenv(_env_file or (ROOT / "server" / ".env"))
    url = os.getenv("SUPABASE_URL", "")
    service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if url and service_key:
        return url, service_key, True
    return url, os.getenv("SUPABASE_KEY", ""), False


def explain_seed_error(err: Exception) -> str:
    msg = str(err)
    if "42501" in msg or "row-level security" in msg.lower():
        return ("RLS denied the write: component_defs only accepts writes with the "
                "service_role key. Add SUPABASE_SERVICE_KEY=<service_role key> to "
                "server/.env (Supabase dashboard → Project Settings → API → "
                "service_role; keep it server-side, never in Vite env) and re-run.")
    if "relation" in msg and "does not exist" in msg:
        return ("table component_defs is missing — apply "
                "supabase/migrations/005_component_registry.sql in the SQL editor first.")
    return msg[:200]


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed component registry")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from components.registry import load_catalog

    catalog = load_catalog()
    entries = catalog["components"]
    print(f"catalog: {len(entries)} components, {len(catalog['categories'])} packs, v{catalog['version']}")
    rows = []
    for eid, e in sorted(entries.items()):
        spec = {k: v for k, v in e.items() if k not in ("id", "version", "kind", "title", "status")}
        rows.append({"id": eid, "version": e.get("version", "0.0.0"),
                     "kind": e.get("kind"), "title": e.get("title", ""),
                     "spec": spec, "status": e.get("status", "planned")})
    if args.dry_run:
        print(json.dumps([r["id"] for r in rows], indent=1))
        return 0

    url, key, using_service = resolve_seed_credentials()
    if not url or not key:
        print("missing SUPABASE_URL + key — set SUPABASE_URL and SUPABASE_SERVICE_KEY in server/.env")
        return 2
    if not using_service:
        print("warning: SUPABASE_SERVICE_KEY not set, using publishable key — "
              "writes will likely be RLS-denied")
    from supabase import create_client
    supa = create_client(url, key)
    n = 0
    for r in rows:
        try:
            supa.table("component_defs").upsert(r, on_conflict="id").execute()
            n += 1
        except Exception as e:
            print(f"upsert {r['id']} failed: {explain_seed_error(e)}")
            return 1
    print(f"upserted {n}/{len(rows)} component defs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
