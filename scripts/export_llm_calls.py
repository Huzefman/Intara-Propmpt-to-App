#!/usr/bin/env python3
"""
Export llm_calls telemetry from Supabase to CSV for the analysis notebook.

    python scripts/export_llm_calls.py            # -> evals/telemetry/llm_calls.csv
    python scripts/export_llm_calls.py --out x.csv

Reads server/.env for SUPABASE_URL + SUPABASE_SERVICE_KEY (falls back to
SUPABASE_KEY). Prompts are never stored in llm_calls (no PII) — this export
is safe to share. Fail-soft: missing creds or an empty table exit non-zero
with a clear message, never a traceback dump.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLS = ["created_at", "provider", "model", "agent", "step_key", "prompt_version",
        "tokens_in", "tokens_out", "latency_ms", "finish_reason",
        "parse_outcome", "repair_used", "fallback_reason", "wish_id", "run_id"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "evals" / "telemetry" / "llm_calls.csv"))
    ap.add_argument("--limit", type=int, default=0, help="stop after N rows (0 = all)")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(ROOT / "server" / ".env")

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        print("No Supabase creds found (server/.env: SUPABASE_URL + "
              "SUPABASE_SERVICE_KEY or SUPABASE_KEY).\nTelemetry exports need "
              "the project that recorded the calls.", file=sys.stderr)
        return 2

    from supabase import create_client
    supa = create_client(url, key)

    rows: list[dict] = []
    page = 1000
    start = 0
    while True:
        q = (supa.table("llm_calls").select("*")
             .order("created_at", desc=False)
             .order("id", desc=False)
             .range(start, start + page - 1))
        batch = q.execute().data or []
        rows.extend(batch)
        if len(batch) < page or (args.limit and len(rows) >= args.limit):
            break
        start += page
    if args.limit:
        rows = rows[: args.limit]

    if not rows:
        print("llm_calls is empty — run some live builds first.", file=sys.stderr)
        return 3

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
