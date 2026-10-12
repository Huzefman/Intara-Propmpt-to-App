#!/usr/bin/env python3
"""Live plan-stage baseline (Phase 0, M0.7): 20 diverse wishes, no builds.

Drives POST /wish/plan for 4 wishes in each of 5 Appendix-D domains and records
per-wish outcome: plan status, serving provider (_meta.source), clarify score,
latency. A plan counts as SUCCESS when it reaches awaiting_approval, or planning
*with* clarify questions (needs user answers — still a healthy plan step).
`failed` status or mock-source-with-warning counts as fallback/failure.

Writes JSON report to evals/reports/baseline-YYYYMMDD-HHMMSS.json and prints a
summary. Reads no keys (uses the running backend on :8000 by default).

Usage: python scripts/eval_live.py [--base-url URL] [--limit N] [--out PATH]
"""
import argparse
import datetime
import json
import sys
import time

try:
    import httpx
except ImportError:
    print("httpx required (pip install httpx)")
    sys.exit(2)

WISHES = [
    # inventory & stock movements
    ("inventory", "An inventory tracker for a hardware shop with products, stock movements and reorder alerts"),
    ("inventory", "A warehouse stock manager with suppliers, purchase orders and low-stock warnings"),
    ("inventory", "A bookstore inventory with titles, suppliers and restock alerts"),
    ("inventory", "A spare-parts inventory for a garage with bins, quantities and reorder levels"),
    # appointment booking
    ("booking", "A salon booking system with services, staff calendars and customer reminders"),
    ("booking", "A clinic appointment scheduler with doctors, slots and patient records"),
    ("booking", "A car service booking app with service types, bays and pickup status"),
    ("booking", "A meeting room reservation tool with rooms, capacities and calendars"),
    # CRM / lead pipeline
    ("crm", "A lead pipeline CRM for a real-estate agent with stages, follow-ups and owner assignment"),
    ("crm", "A customer tracker for a bakery with orders, preferences and birthdays"),
    ("crm", "A freelance client CRM with projects, invoices and payment status"),
    ("crm", "A test-drive lead tracker for a car dealership with slots and salesperson assignment"),
    # repair / job tracker
    ("repair", "A phone repair shop tracker with jobs, parts used and pickup status"),
    ("repair", "An appliance service tracker with complaints, technicians and visit slots"),
    ("repair", "A laptop repair workflow with diagnosis stages, parts and billing"),
    ("repair", "A bike workshop job board with services, mechanics and delivery dates"),
    # leave & attendance (HR)
    ("hr", "An employee leave request system with approvals and balances"),
    ("hr", "A staff attendance tracker with check-ins, late marks and monthly summary"),
    ("hr", "A team shift planner with rosters, swaps and weekly view"),
    ("hr", "An onboarding checklist tracker for new hires with tasks and owners"),
]


def api(base: str, method: str, path: str, body=None, timeout: float = 30.0):
    r = httpx.request(method, base + path,
                      json=body if body is not None else None, timeout=timeout)
    r.raise_for_status()
    return r.json()


def classify(final: dict) -> tuple[str, dict]:
    """Pure outcome classification shared by the runner and unit tests.

    success = awaiting_approval (live), or planning WITH clarify questions.
    fallback = mock-sourced plan (degraded; counts as failure in live metrics).
    failed/timeout otherwise.
    """
    status = final.get("status", "?")
    prd = final.get("prd") or {}
    meta = prd.get("_meta") or {}
    clarify = prd.get("clarify") or {}
    has_questions = bool(clarify.get("questions"))
    info = {"plan_status": status, "meta_source": meta.get("source"),
            "model": meta.get("model"), "clarify_score": clarify.get("score"),
            "has_questions": has_questions,
            "warning": (meta.get("warning") or "")[:160]}
    if status == "failed":
        return "failed", info
    if meta.get("source") == "mock":
        return "fallback", info
    if status == "awaiting_approval":
        return "success", info
    if status == "planning" and has_questions:
        return "success", info
    return "timeout", info


def run_wish(base: str, domain: str, prompt: str, poll_timeout: float) -> dict:
    t0 = time.time()
    rec = {"domain": domain, "prompt": prompt}
    try:
        w = api(base, "POST", "/api/wish/plan", {"prompt": prompt}, timeout=60.0)
    except Exception as e:
        rec.update({"outcome": "error", "error": str(e)[:200],
                    "latency_s": round(time.time() - t0, 1)})
        return rec
    wid = w.get("id", "")
    rec["wish_id"] = wid
    deadline = time.time() + poll_timeout
    final = w
    while time.time() < deadline:
        time.sleep(5)
        try:
            final = api(base, "GET", f"/api/wish/{wid}", timeout=20.0)
        except Exception as e:
            rec.update({"outcome": "error", "error": f"poll: {e}"[:200],
                        "latency_s": round(time.time() - t0, 1)})
            return rec
        if final.get("status") != "planning":
            break
        prd = final.get("prd") or {}
        if (prd.get("clarify") or {}).get("questions"):
            break
    status = final.get("status", "?")
    outcome, info = classify(final)
    rec.update({
        "outcome": outcome,
        "plan_status": info["plan_status"],
        "meta_source": info["meta_source"],
        "model": info["model"],
        "clarify_score": info["clarify_score"],
        "has_questions": info["has_questions"],
        "warning": info["warning"],
        "latency_s": round(time.time() - t0, 1),
    })
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description="Live plan-stage baseline (no builds)")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", default=None)
    ap.add_argument("--poll-timeout", type=float, default=240.0)
    ap.add_argument("--delay", type=float, default=5.0,
                    help="seconds between wishes (free-tier courtesy)")
    args = ap.parse_args()

    targets = WISHES[:args.limit]
    results = []
    for i, (domain, prompt) in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {domain}: {prompt[:60]}...", flush=True)
        rec = run_wish(args.base_url, domain, prompt, args.poll_timeout)
        results.append(rec)
        print(f"    -> {rec['outcome']} ({rec.get('plan_status')}, "
              f"src={rec.get('meta_source')}, {rec.get('latency_s')}s)", flush=True)
        if i < len(targets):
            time.sleep(args.delay)

    by_outcome: dict[str, int] = {}
    by_source: dict[str, int] = {}
    lat = []
    for r in results:
        by_outcome[r["outcome"]] = by_outcome.get(r["outcome"], 0) + 1
        by_source[str(r.get("meta_source"))] = by_source.get(str(r.get("meta_source")), 0) + 1
        if isinstance(r.get("latency_s"), (int, float)):
            lat.append(r["latency_s"])
    lat.sort()
    summary = {
        "n": len(results),
        "outcomes": by_outcome,
        "meta_sources": by_source,
        "latency_s": {"min": lat[0] if lat else None,
                      "median": lat[len(lat) // 2] if lat else None,
                      "max": lat[-1] if lat else None},
        "note": "fallback = mock source; degraded builds count as failures per AGENT.md",
    }
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = args.out or f"evals/reports/baseline-{stamp}.json"
    import os
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, indent=1)
    print(json.dumps(summary, indent=1))
    print(f"report: {out}")
    bad = sum(by_outcome.get(k, 0) for k in ("failed", "error", "timeout"))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
