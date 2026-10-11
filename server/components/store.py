"""
Composition persistence — records which catalog components a wish was planned
from into wish_components (migration 005).

Fail-soft by design: composition is analytics + future targeting metadata. It
must never break planning or building, so every DB touch is guarded and every
helper degrades to a no-op with a printed reason. Reads/writes use the standard
app credentials (ownerless wishes are writable under the demo RLS posture).
"""


def rows_for_wish(wid: str, prd: dict, catalog: dict) -> list[dict]:
    """Pure: build wish_components rows from prd['_components'].units."""
    comp = (prd or {}).get("_components") or {}
    defs = (catalog or {}).get("components", {})
    rows = []
    for u in comp.get("units", []) or []:
        cid = (u or {}).get("component", "")
        if not cid or cid not in defs:
            continue
        rows.append({
            "wish_id": wid,
            "component_id": cid,
            "version": (defs[cid] or {}).get("version", "0.0.0"),
            "config": (u or {}).get("config", {}),
            "status": "pending",
        })
    return rows


def record_wish_composition(wid: str, prd: dict) -> int:
    """Replace wish_components rows for a wish from its planned composition.

    Returns rows written (0 when there is nothing to record or on any error).
    """
    try:
        from components.registry import load_catalog
        catalog = load_catalog()
        rows = rows_for_wish(wid, prd, catalog)
        if not rows:
            return 0
        from db.wishes import _client
        supa = _client()
        supa.table("wish_components").delete().eq("wish_id", wid).execute()
        supa.table("wish_components").insert(rows).execute()
        return len(rows)
    except Exception as e:
        print(f"record_wish_composition skipped for {wid}: {str(e)[:160]}")
        return 0
