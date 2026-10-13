#!/usr/bin/env python3
"""core20 eval (Phase 7, P7.5): 20 wishes through the v2 pipeline, live.

Manual dispatch only (quota + wall-time): ~7 LLM calls/wish when healthy.
  python scripts/core20.py --probe        # 2 wishes (corpus + heldout), validates harness
  python scripts/core20.py --live         # full 20 (15 corpus + 5 heldout)
  python scripts/core20.py --live --limit 5
Drives POST /api/runs on the local backend, polls to terminal, then grades
each spec G0/G1/G2 (+G3 via node) and records diversity + budgets.
Writes evals/reports/core20-<ts>.json. Held-out domains (#6-10) measure
generalisation: they are NEVER in the retrieval corpus (P5.3).
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

WISHES = [
    ("A task tracker with projects, tasks and due dates", "productivity", False),
    ("A salon booking system with services and reminders", "appointment_booking", False),
    ("A parts inventory with reorder alerts", "retail_inventory", False),
    ("A repair shop tracker with jobs and billing", "repair_shop", False),
    ("A leave request system with approvals", "hr_leave", False),
    ("A CRM with leads, pipeline and activities", "crm", False),
    ("A library catalog with books and loans", "library", False),
    ("A gym class schedule with trainers and bookings", "fitness", False),
    ("A recipe box with ingredients and meal plans", "food", False),
    ("A pet clinic with patients and visits", "veterinary", False),
    ("A freelance time tracker with clients and invoices-lite", "freelance", False),
    ("A school club manager with members and events", "education", False),
    ("A garden planner with beds and plantings", "gardening", False),
    ("A car service log with vehicles and services", "automotive", False),
    ("A book club with books, meetings and notes", "social", False),
    ("An invoicing tracker with line items and payment status", "invoicing", True),
    ("A restaurant order board with tables and kitchen queue", "restaurant_orders", True),
    ("A gym membership manager with expiry and payments", "gym_membership", True),
    ("A school fee tracker with students and installments", "school_fees", True),
    ("A helpdesk with tickets, priorities and assignment", "helpdesk", True),
]


def api(method, path, payload=None, base="http://localhost:8000", timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def grade_g012(spec):
    from gates.g0_validate import validate as g0
    from gates.g1_lint import lint as g1
    from gates.g2_coverage import check as g2
    g0e = g0(spec)
    g1e = lint(spec)["errors"]
    reqs = spec.get("requirements") or []
    g2r = g2(reqs, spec.get("trace") or [])
    musts = [r.get("id") for r in reqs if r.get("priority") == "must"]
    cov = ([r for r in musts if r not in g2r["missing_must"]])
    return {"g0": not g0e, "g1": not g1e, "g2": not g2r["missing_must"],
            "g0_errors": g0e[:3], "g1_errors": [e["rule"] for e in g1e[:5]],
            "coverage": round(len(cov) / len(musts), 3) if musts else 1.0}


def grade_g3_node(spec):
    """G3 via node (testing/g3.ts — pure .ts, native stripping)."""
    g3_url = "file://" + os.path.join(ROOT, "packages", "runtime", "testing", "g3.ts")
    script = ("const {runG3} = await import(" + json.dumps(g3_url) + ");"
              "const r = await runG3(JSON.parse(process.argv[1]), 'core20');"
              "console.log(JSON.stringify({failures: r.failures, checks: r.checks}));")
    try:
        r = subprocess.run(["node", "--input-type=module", "-e", script, json.dumps(spec)],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return False, 0, r.stderr[-300:]
        out = json.loads(r.stdout.strip().splitlines()[-1])
        return (not out["failures"]), out["checks"], out["failures"][:2]
    except Exception as e:
        return False, 0, str(e)[:200]


def diversity(specs):
    feats = []
    for s in specs:
        ui = s.get("ui") or {}
        feats.append({
            "archetype": ((ui.get("theme") or {}).get("archetype") or "?"),
            "nav": tuple(sorted(n.get("page", "") for n in ui.get("nav", []))),
            "palette": ((ui.get("theme") or {}).get("palette") or "?"),
            "entities": frozenset(e.get("id", "") for e in (s.get("model") or {}).get("entities", [])),
        })
    combos = {(f["archetype"], f["nav"], f["palette"]) for f in feats}
    overlaps = []
    for i in range(len(feats)):
        for j in range(i + 1, len(feats)):
            a, b = feats[i]["entities"], feats[j]["entities"]
            union = a | b
            overlaps.append(len(a & b) / len(union) if union else 0.0)
    return {"distinct_combos": len(combos),
            "mean_entity_overlap": round(sum(overlaps) / len(overlaps), 3) if overlaps else 0.0}


def run_wish(prompt, base, poll=5, timeout_s=1800):
    t0 = time.time()
    started = api("POST", "/api/runs", {"wish": prompt, "kind": "build",
                                        "app_name": prompt.split()[0].title()},
                  base=base)
    run_id = started["run_id"]
    status, spec, version = "running", None, None
    while time.time() - t0 < timeout_s:
        time.sleep(poll)
        st = api("GET", f"/api/runs/{run_id}", base=base)
        status = st["run"].get("status")
        spec, version = st.get("spec"), st.get("version_id")
        if status in ("done", "degraded", "failed", "cancelled"):
            break
    st = api("GET", f"/api/runs/{run_id}", base=base)
    return {"run_id": run_id, "status": status, "spec": spec,
            "version_id": version, "wall_s": round(time.time() - t0, 1),
            "llm_calls": st.get("llm_calls", 0),
            "degraded_steps": st.get("degraded_steps", [])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--base-url", default="http://localhost:8000")
    args = ap.parse_args()
    if args.probe:
        targets = [WISHES[5], WISHES[15]]  # crm (corpus) + invoicing (heldout)
    elif args.live:
        targets = WISHES[:args.limit]
    else:
        print("choose --probe (2 wishes) or --live (up to 20). Manual dispatch only.")
        return 2
    results = []
    for i, (prompt, domain, heldout) in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {domain} (heldout={heldout}): {prompt[:50]}...")
        try:
            r = run_wish(prompt, args.base_url)
        except Exception as e:
            results.append({"prompt": prompt, "domain": domain, "heldout": heldout,
                            "status": "error", "error": str(e)[:300]})
            print(f"  ERROR {e}")
            continue
        row = {"prompt": prompt, "domain": domain, "heldout": heldout,
               "status": r["status"], "run_id": r["run_id"],
               "version_id": r.get("version_id"), "wall_s": r["wall_s"],
               "llm_calls": r.get("llm_calls", 0),
               "degraded_steps": r.get("degraded_steps", [])}
        if r["spec"]:
            row["gates"] = grade_g012(r["spec"])
            g3, checks, detail = grade_g3_node(r["spec"])
            row["gates"]["g3"] = g3
            row["gates"]["g3_checks"] = checks
            if not g3:
                row["gates"]["g3_detail"] = detail
            ui = r["spec"].get("ui") or {}
            row["features"] = {
                "archetype": ((ui.get("theme") or {}).get("archetype") or "?"),
                "nav": sorted(n.get("page", "") for n in ui.get("nav", [])),
                "palette": ((ui.get("theme") or {}).get("palette") or "?"),
                "entities": sorted(e.get("id", "") for e in (r["spec"].get("model") or {}).get("entities", [])),
            }
            row["spec"] = r["spec"]
        print(f"  {r['status']} wall={r['wall_s']}s gates={row.get('gates', {})}")
        results.append(row)
    ok = [r for r in results
          if r["status"] in ("done", "degraded")
          and (r.get("gates") or {}).get("g0") and (r.get("gates") or {}).get("g1")]
    specs = [r["spec"] for r in results if r.get("spec")]
    div = diversity(specs)
    walls = sorted(r.get("wall_s", 0) for r in results if r.get("status") in ("done", "degraded"))
    calls = sorted(r.get("llm_calls", 0) for r in results if r.get("status") in ("done", "degraded"))
    summary = {"n": len(results), "pass_g0g1": len(ok),
               "rate": round(len(ok) / len(results), 3) if results else 0,
               "median_wall_s": walls[len(walls) // 2] if walls else None,
               "median_llm_calls": calls[len(calls) // 2] if calls else None,
               "diversity": div, "results": results}
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(ROOT, "evals", "reports", f"core20-{ts}.json")
    json.dump(summary, open(out, "w"), indent=1)
    print(f"pass G0/G1: {len(ok)}/{len(results)}  diversity: {div}  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
