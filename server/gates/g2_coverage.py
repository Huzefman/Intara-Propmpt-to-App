"""
G2 — requirement coverage (Phase 7, P7.3; rule = guide §9).

Deterministic existence check over the Critic's trace: every `must`
requirement needs a trace entry with a non-empty satisfied_by; `should`
gaps are advisory. The Critic's plausibility verdicts (satisfied/missing /
unclear) ride along for the Studio; the gate itself never calls an LLM.
"""
from __future__ import annotations


def check(requirements: list, trace: list) -> dict:
    reqs = requirements or []
    covered: dict = {}
    for t in trace or []:
        if not isinstance(t, dict):
            continue
        rid = t.get("requirement")
        sat = t.get("satisfied_by") or []
        if rid and sat:
            covered[rid] = sat
    missing_must: list = []
    missing_should: list = []
    for r in reqs:
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        if not rid or rid in covered:
            continue
        if r.get("priority") == "must":
            missing_must.append(rid)
        else:
            missing_should.append(rid)
    return {"missing_must": missing_must, "missing_should": missing_should,
            "covered": sorted(covered)}
