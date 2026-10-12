"""
Startup sweeper (Phase 3, P3.3).

A fresh boot owns no builds, so any wish stuck `building` and any step stuck
`running` is orphaned by an unclean shutdown (kill -9, crash, deploy). The
sweeper requeues orphan steps to `pending` (resume is cheap: content-addressed
artifacts mean retry restores instead of regenerating) and flips orphan wishes
to `failed` with a pointer at the first non-done step — no row stays stuck in
`building`, and the retry endpoint picks the build back up.

Fail-soft: never blocks boot; returns counts for the startup log.
"""
from __future__ import annotations


def sweep_orphans(*, limit: int = 500) -> dict:
    summary: dict = {"wishes": 0, "steps": 0}
    try:
        from db.wishes import (list_wishes_with_steps, get_steps, update_step,
                               set_wish_status)
    except Exception as e:
        print(f"startup sweep skipped (db unavailable): {e}")
        summary["error"] = str(e)[:200]
        return summary
    try:
        wishes = list_wishes_with_steps(limit) or []
    except Exception as e:
        print(f"startup sweep skipped (list failed): {e}")
        summary["error"] = str(e)[:200]
        return summary
    for w in wishes:
        if (w or {}).get("status") != "building":
            continue
        wid = w.get("id")
        if not wid:
            continue
        try:
            steps = get_steps(wid) or []
        except Exception as e:
            print(f"sweep {wid}: steps unreadable, skipping: {e}")
            continue
        requeued = 0
        for s in steps:
            if (s or {}).get("status") != "running":
                continue
            try:
                update_step(wid, s.get("step_id"), status="pending",
                            error="orphaned by process restart; requeued for resume",
                            attempt=int(s.get("attempt") or 1) + 1)
                requeued += 1
            except Exception as e:
                print(f"sweep {wid}/{s.get('step_id')}: requeue failed: {e}")
        done = {s.get("step_id") for s in steps if s.get("status") == "done"}
        graph = w.get("build_graph") or (w.get("prd") or {}).get("buildGraph") or []
        current = None
        for n in graph:
            if (n or {}).get("id") not in done:
                current = n.get("id")
                break
        try:
            set_wish_status(wid, "failed", current_step_id=current)
            summary["wishes"] += 1
            summary["steps"] += requeued
            print(f"sweep {wid}: orphaned build → failed, {requeued} step(s) requeued"
                  + (f", resume at {current}" if current else ""))
        except Exception as e:
            print(f"sweep {wid}: wish flip failed: {e}")
    return summary
