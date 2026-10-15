"""
PRD → App Spec adapter (Phase 5, P5.1).

Converts legacy planner PRDs ({appName, tagline, tables, pages, apis}) into
App Spec v1 so the 5 golden-fixture wishes (and any old plan) can flow through
G0/G1 and retrieval. Deterministic, no LLM. Output is guaranteed G0/G1-clean
by construction (covered by test):
- every entity appears in ≥1 table block (round-robin + fill-up)
- every page is in nav with the owner role; ids are snake_cased
Legacy field types map: text→text, integer→int, timestamp→datetime,
boolean→bool, anything else→text.
"""
from __future__ import annotations

import re

TYPE_MAP = {"text": "text", "integer": "int", "timestamp": "datetime",
            "boolean": "bool"}

# Storage-managed fields never belong in a spec (G1 R40).
SKIP_FIELDS = {"id", "created_at", "updated_at"}


def snake(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(name or ""))
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s or "unnamed"


def adapt_prd(prd: dict, prompt: str = "") -> dict:
    prd = prd if isinstance(prd, dict) else {}
    tables = prd.get("tables") or []
    pages = prd.get("pages") or []
    app_name = prd.get("appName") or "App"

    entities = []
    for t in tables:
        eid = snake(t.get("name"))
        fields = []
        for f in t.get("fields") or []:
            fid = snake(f.get("name"))
            if fid in SKIP_FIELDS:
                continue
            fields.append({"id": fid,
                           "type": TYPE_MAP.get((f.get("type") or "").lower(), "text")})
        if not fields:
            fields.append({"id": "name", "type": "text"})
        entities.append({"id": eid, "label": t.get("name") or eid, "fields": fields,
                         "display": {"title": f"{{{fields[0]['id']}}}"}})

    # round-robin entities over pages so every page has data; uncovered
    # entities get table blocks on the first page (R19 coverage).
    spec_pages = []
    used: set = set()
    for i, pg in enumerate(pages):
        pid = snake(pg.get("name")) or f"page_{i}"
        ent = entities[i % len(entities)]["id"] if entities else None
        blocks = []
        if ent:
            if ":id" in (pg.get("route") or ""):
                # detail pages show one record (G1 R39/R46)
                blocks.append({"id": f"b_{pid}", "type": "record.detail",
                               "props": {"entity": ent,
                                         "sections": [{"title": "Details",
                                                       "fields": ["name"]}]}})
            else:
                blocks.append({"id": f"b_{pid}", "type": "data.table",
                               "props": {"entity": ent, "create": True}})
            used.add(ent)
        spec_pages.append({"id": pid, "route": pg.get("route") or f"/{pid}",
                           "title": pg.get("name") or pid, "roles": ["owner"],
                           "blocks": blocks})
    if not spec_pages and entities:
        spec_pages.append({"id": "home", "route": "/", "title": "Home",
                           "roles": ["owner"], "blocks": []})
    if spec_pages:
        extra = [e["id"] for e in entities if e["id"] not in used]
        for j, eid in enumerate(extra):
            spec_pages[0]["blocks"].append(
                {"id": f"b_extra_{j}", "type": "data.table",
                 "props": {"entity": eid, "create": True}})

    # detail pages need inbound row_links (R20); table blocks link to the
    # detail page showing the same entity (R42). nav excludes :id pages (R39).
    detail_of: dict = {}
    for p in spec_pages:
        if ":id" in (p.get("route") or ""):
            for b in p.get("blocks") or []:
                ent = (b.get("props") or {}).get("entity")
                if ent:
                    detail_of[ent] = p["id"]
    for p in spec_pages:
        if ":id" in (p.get("route") or ""):
            continue
        for b in p.get("blocks") or []:
            if b.get("type") == "data.table":
                ent = (b.get("props") or {}).get("entity")
                if ent in detail_of:
                    b["props"]["row_link"] = detail_of[ent]
    linked_targets = set()
    for p in spec_pages:
        for b in p.get("blocks") or []:
            rl = (b.get("props") or {}).get("row_link")
            if isinstance(rl, str):
                linked_targets.add(rl)
    for eid, dpid in detail_of.items():
        if dpid not in linked_targets and spec_pages:
            spec_pages[0]["blocks"].append(
                {"id": f"b_link_{eid}", "type": "data.table",
                 "props": {"entity": eid, "create": True, "row_link": dpid}})

    # unique page ids (dup names → suffix)
    seen: dict = {}
    for p in spec_pages:
        if p["id"] in seen:
            seen[p["id"]] += 1
            p["id"] = f"{p['id']}_{seen[p['id']]}"
            for b in p["blocks"]:
                b["id"] = f"b_{p['id']}"
        else:
            seen[p["id"]] = 0

    requirements = []
    trace = []
    if prompt:
        requirements.append({"id": "R1", "text": prompt, "priority": "must"})
        trace.append({"requirement": "R1",
                      "satisfied_by": [f"entity:{e['id']}" for e in entities]
                      + [f"page:{p['id']}" for p in spec_pages]})

    return {
        "spec_version": "1.0",
        "app": {"name": app_name, "tagline": prd.get("tagline") or ""},
        "personas": [],
        "requirements": requirements,
        "assumptions": [],
        "model": {"enums": [], "entities": entities},
        "access": {"roles": [{"id": "owner", "label": "Owner"}],
                   "rules": [{"entity": "*", "role": "owner",
                              "ops": ["read", "create", "update", "delete"]}]},
        "ui": {"theme": {"archetype": "table-first"},
               "nav": [{"page": p["id"], "label": p["title"]} for p in spec_pages
                       if ":id" not in (p.get("route") or "")],
               "pages": spec_pages},
        "automations": [],
        "seed": {},
        "integrations": [],
        "trace": trace,
    }
