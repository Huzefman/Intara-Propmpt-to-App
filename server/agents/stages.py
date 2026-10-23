"""
Pipeline stages S0–S6 + Edit (Phase 7, P7.2/P7.3).

Each stage: agent name, prompt version + tier, prompt builder, output model,
stage gate (deterministic; full G0/G1 at S5), deterministic fallback
(degraded, never silent). S5 Assembler is pure code (no LLM); the Critic is
a separate LLM step whose verdicts feed G2 + the ≤2 repair loop.
"""
from __future__ import annotations

import re
from typing import Any

from agents import prompts as P
from agents.schemas import (IterationOut, S0IntakeOut, S1ClarifyOut, S2ModelOut,
                            S3UiOut, S4LogicOut, S5CriticOut, S6SeedOut)

ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _bad_ids(items, path="") -> list[str]:
    return [f"bad id {x.get('id')!r} at {path or 'root'}"
            for x in items or []
            if not (isinstance(x, dict) and isinstance(x.get("id"), str)
                    and ID_RE.match(x["id"]))]


def _dupes(items) -> list[str]:
    seen: set = set()
    out = []
    for x in items or []:
        iid = x.get("id") if isinstance(x, dict) else None
        if iid in seen:
            out.append(f"duplicate id {iid!r}")
        seen.add(iid)
    return out


# ---------- stage gates (deterministic, slice-local) ----------

def _gate_s2(out: S2ModelOut) -> list[str]:
    errs = _dupes([{"id": e.id} for e in out.model.entities])
    errs += _dupes([{"id": e.id} for e in out.model.enums])
    if not out.model.entities:
        errs.append("model needs at least one entity")
    enum_ids = {e.id for e in out.model.enums}
    ent_ids = {e.id for e in out.model.entities}
    for e in out.model.entities:
        errs += _bad_ids([{"id": e.id}], "entities")
        errs += _bad_ids([{"id": f.id} for f in e.fields], f"entities.{e.id}")
        errs += _dupes([{"id": f.id} for f in e.fields])
        for f in e.fields:
            if f.type in ("ref", "multi_ref") and f.target not in ent_ids:
                errs.append(f"ref target {f.target!r} missing")
            if f.type in ("enum", "multi_enum") and f.enum not in enum_ids:
                errs.append(f"enum {f.enum!r} missing")
        lc = e.lifecycle
        if lc and (not lc.transitions or lc.initial in (None, "")):
            errs.append(f"lifecycle on {e.id} needs initial + transitions")
            continue
        if lc and lc.transitions:
            # from/to must be values of the lifecycle field's enum (G1 R16 early)
            fld = next((x for x in e.fields if x.id == lc.field), None)
            enum_vals = None
            if fld is not None and fld.type == "enum":
                for en in out.model.enums:
                    if en.id == fld.enum:
                        enum_vals = {v.value for v in en.values}
            if enum_vals is not None:
                if lc.initial not in enum_vals:
                    errs.append(f"initial {lc.initial!r} not in enum")
                for t in lc.transitions:
                    if t.from_ not in enum_vals:
                        errs.append(f"transition from-state {t.from_!r} unknown")
                    if t.to not in enum_vals:
                        errs.append(f"transition to-state {t.to!r} unknown")
                # reachability from initial (G1 R18 early)
                states = set(lc.states) if lc.states else set(enum_vals)
                adj: dict = {}
                for t in lc.transitions:
                    adj.setdefault(t.from_, set()).add(t.to)
                seen = {lc.initial}
                stack = [lc.initial]
                while stack:
                    cur = stack.pop()
                    for nxt in adj.get(cur, ()):
                        if nxt not in seen:
                            seen.add(nxt)
                            stack.append(nxt)
                for s in states:
                    if s not in seen:
                        errs.append(f"lifecycle state {s!r} unreachable from initial")
    return errs


def _gate_s3(out: S3UiOut, entity_ids: set, requirements: str = "") -> list[str]:
    errs = _dupes([{"id": p.id} for p in out.ui.pages])
    page_ids = {p.id for p in out.ui.pages}
    page_roles: set = set()
    for p in out.ui.pages:
        page_roles.update(p.roles or [])
    if "owner" not in page_roles:
        errs.append("anchor role 'owner' must appear on at least one page")
    for item in out.ui.nav:
        if item.page not in page_ids:
            errs.append(f"nav page {item.page!r} missing")
    covered: set = set()
    linked: set = set()
    try:
        from gates.g1_lint import BLOCKS as _BLOCKS
    except Exception:
        _BLOCKS = {}
    for p in out.ui.pages:
        for b in p.blocks or []:
            btype = b.type or ""
            info = _BLOCKS.get(btype)
            if info is not None:
                for req in info.get("required_props", []):
                    if req not in (b.props or {}):
                        errs.append(f"block {btype!r} missing required prop {req!r}")
            ent = (b.props or {}).get("entity")
            if isinstance(ent, str):
                if ent not in entity_ids:
                    errs.append(f"block entity {ent!r} missing")
                covered.add(ent)
            rl = (b.props or {}).get("row_link")
            if isinstance(rl, str):
                linked.add(rl)
    for eid in entity_ids:
        if eid not in covered:
            errs.append(f"entity {eid!r} in no block")
    nav_ids = {item.page for item in out.ui.nav}
    for p in out.ui.pages:
        if p.id not in nav_ids and p.id not in linked:
            errs.append(f"page {p.id!r} unreachable (not in nav, no row_link)")
    return errs


def _gate_s4(out: S4LogicOut, entity_ids: set, page_roles: set | None = None,
             entity_fields: dict | None = None) -> list[str]:
    from engine.formula import parse as _parse, FormulaSyntaxError
    errs: list[str] = []
    role_ids = {r.id for r in out.access.roles}
    fields_of = entity_fields or {}
    for e in out.access.roles:
        if not ID_RE.match(e.id or ""):
            errs.append(f"bad role id {e.id!r}")
    # cross-stage contract: role SET EQUALITY with the UI (both directions).
    # S3 declares (owner anchor + approval roles), S4 reuses exactly.
    for r in role_ids:
        if r not in (page_roles or set()):
            errs.append(f"role {r!r} has no page (S3 must declare it first)")
    for pr in page_roles or ():
        if pr not in role_ids:
            errs.append(f"page role {pr!r} missing from access.roles")
    for a in out.automations:
        trig = a.trigger
        if trig.type in ("record.created", "record.updated", "lifecycle.transition"):
            if trig.entity not in entity_ids:
                errs.append(f"trigger entity {trig.entity!r} missing")
        for s in a.steps or []:
            if s.when:
                try:
                    _parse(s.when)
                except FormulaSyntaxError as ex:
                    errs.append(f"when does not parse: {ex}")
            if s.action == "set_field" and trig.entity in entity_ids:
                fld = (s.params or {}).get("field")
                if fld not in fields_of.get(trig.entity, []):
                    errs.append(f"set_field unknown field {fld!r}")
            if s.action == "create_record":
                ent = (s.params or {}).get("entity")
                if ent not in entity_ids:
                    errs.append(f"create_record unknown entity {ent!r}")
    return errs


def _gate_formulas(model) -> list[str]:
    from engine.formula import parse as _parse, FormulaSyntaxError
    errs = []
    for e in model.entities:
        names = {f.id for f in e.fields}
        for f in e.fields:
            formula = (f.computed or {}).formula if getattr(f, "computed", None) else None
            if not formula:
                continue
            try:
                _parse(formula)
            except FormulaSyntaxError as ex:
                errs.append(f"{e.id}.{f.id}: {ex}")
    return errs


# ---------- deterministic fallbacks (degraded, labelled) ----------

def _fb_s0(wish: str) -> dict:
    return {"clean_wish": wish[:2000], "track": "business", "scope": "mvp",
            "risk_flags": [], "language": "en"}


def _fb_s1() -> dict:
    return {"questions": [], "assumptions": ["Single location", "English-only v1",
                                            "Owner approves before build"]}


def _fb_s2() -> dict:
    return {"model": {"enums": [], "entities": [
        {"id": "record", "label": "Record",
         "fields": [{"id": "name", "type": "text", "required": True}],
         "display": {"title": "{name}"}}]}}


def _fb_s3(entity_ids: list) -> dict:
    pages = [{"id": "home", "route": "/", "title": "Home", "roles": ["owner"],
              "blocks": [{"id": f"b_{e}", "type": "data.table",
                          "props": {"entity": e, "create": True}} for e in entity_ids]}]
    return {"ui": {"theme": {"archetype": "table-first"}, "nav": [
        {"page": "home", "label": "Home"}] if pages else [], "pages": pages}}


def _fb_s4() -> dict:
    return {"access": {"roles": [{"id": "owner", "label": "Owner"}],
                                 "rules": [{"entity": "*", "role": "owner",
                                            "ops": ["read", "create", "update", "delete"]}]},
            "automations": []}


def _fb_critic(requirements: list) -> dict:
    return {"trace": [], "critiques": [{"requirement": r, "verdict": "unclear",
                                        "note": "critic unavailable"} for r in requirements],
            "unsatisfied": list(requirements)}


def _fb_s6() -> dict:
    return {"seed": {}}


def _fb_edit() -> dict:
    # The Edit stage has no deterministic fallback: a bad patch must surface,
    # never silently ship. The endpoint maps this to an error.
    raise RuntimeError("edit failed validation and has no safe fallback")


# ---------- S5 assembler (pure code, no LLM) ----------

def _normalize_ui(parts: dict) -> dict:
    """Apply deterministic, lint-safe fixes to the UI slice.

    A model sometimes puts a detail page (`/notes/:id`) in the nav. G1 R39
    rejects that: detail pages are reached through a `row_link`, while nav is
    only for top-level destinations. Normalizing here keeps a single bad nav
    entry from failing an otherwise valid build; missing pages and other gate
    problems are deliberately left in place so G0/G1 still report them.
    """
    raw = parts.get("ui")
    ui = dict(raw) if isinstance(raw, dict) else {"pages": []}
    pages = {
        p.get("id"): p
        for p in (ui.get("pages") or [])
        if isinstance(p, dict) and isinstance(p.get("id"), str)
    }
    nav = []
    for item in ui.get("nav") or []:
        if not isinstance(item, dict):
            continue
        page = pages.get(item.get("page"))
        if page is None:
            nav.append(item)
            continue
        route = page.get("route")
        if isinstance(route, str) and ":id" in route:
            continue  # detail page: reachable via row_link, never nav
        clean = dict(item)
        if "roles" in clean:
            page_roles = page.get("roles") or []
            clean["roles"] = [r for r in (clean.get("roles") or []) if r in page_roles]
        nav.append(clean)
    ui["nav"] = nav
    return ui


def assemble_spec(parts: dict) -> dict:
    """Merge stage slices into an AppSpec dict (S5 assembler, deterministic)."""
    app = parts.get("app") or {"name": "App"}
    return {
        "spec_version": "1.0",
        "app": {"name": app.get("name", "App"), "tagline": app.get("tagline", ""),
                "domain": app.get("domain", ""), "locale": app.get("locale", "en"),
                "currency": app.get("currency", "USD"), "timezone": app.get("timezone", "UTC")},
        "personas": parts.get("personas") or [],
        "requirements": parts.get("requirements") or [],
        "assumptions": parts.get("assumptions") or [],
        "model": parts.get("model") or {"enums": [], "entities": []},
        "access": parts.get("access") or {"roles": [], "rules": []},
        "ui": _normalize_ui(parts),
        "automations": parts.get("automations") or [],
        "seed": parts.get("seed") or {},
        "integrations": [],
        "trace": parts.get("trace") or [],
    }


def summarize_spec(spec: dict) -> str:
    """Compact element inventory for the Critic prompt (small outputs)."""
    bits = []
    for e in (spec.get("model") or {}).get("entities", []):
        bits.append(f"entity:{e.get('id')}[{','.join(f.get('id', '') for f in e.get('fields', []))}]")
    for p in (spec.get("ui") or {}).get("pages", []):
        bits.append(f"page:{p.get('id')}[{','.join((b.get('type') or '') for b in p.get('blocks', []))}]")
    for a in spec.get("automations", []):
        bits.append(f"automation:{a.get('id')}")
    return "; ".join(bits)


STAGES: dict[str, dict[str, Any]] = {
    "s0": {"agent": "s0-intake", "tier": "fast", "model": S0IntakeOut,
           "prompt": lambda i: P.s0_prompt(i["wish"]), "fallback": lambda i: _fb_s0(i["wish"])},
    "s1": {"agent": "s1-clarifier", "tier": "fast", "model": S1ClarifyOut,
           "prompt": lambda i: P.s1_prompt(i["clean_wish"], i.get("domains", "")),
           "fallback": lambda i: _fb_s1()},
    "s2": {"agent": "s2-modeler", "tier": "strong", "model": S2ModelOut,
           "prompt": lambda i: P.s2_prompt(i["wish"], i.get("answers", ""), i.get("assumptions", []), i.get("exemplars", "")),
           "gate": lambda o, i: _gate_s2(o) + _gate_formulas(o.model),
           "fallback": lambda i: _fb_s2()},
    "s3": {"agent": "s3-designer", "tier": "strong", "model": S3UiOut,
           "prompt": lambda i: P.s3_prompt(i["model_json"], i.get("personas", ""), i.get("blocks", ""), i.get("requirements_json", "")),
           "gate": lambda o, i: _gate_s3(o, set(i.get("entity_ids", []))),
           "fallback": lambda i: _fb_s3(list(i.get("entity_ids", [])))},
    "s4": {"agent": "s4-logic", "tier": "strong", "model": S4LogicOut,
           "prompt": lambda i: P.s4_prompt(i["model_json"], i.get("ui_summary", ""), i.get("actions", ""), i.get("page_roles", "")),
           "gate": lambda o, i: _gate_s4(o, set(i.get("entity_ids", [])), set(i.get("page_roles_list", [])), i.get("entity_fields", {})),
           "fallback": lambda i: _fb_s4()},
    "s5critic": {"agent": "s5-critic", "tier": "strong", "model": S5CriticOut,
                 "prompt": lambda i: P.s5critic_prompt(i["requirements_json"], i.get("spec_summary", "")),
                 "fallback": lambda i: _fb_critic(i.get("requirement_ids", []))},
    "s6": {"agent": "s6-seed", "tier": "fast", "model": S6SeedOut,
           "prompt": lambda i: P.s6_prompt(i["model_json"], i.get("domain", ""), i.get("locale", "en")),
           "fallback": lambda i: _fb_s6()},
    "edit": {"agent": "edit-agent", "tier": "fast", "model": IterationOut,
             "prompt": lambda i: P.edit_prompt(i["instruction"], i.get("spec_slice", ""), i.get("chat_context", "")),
             "fallback": lambda i: _fb_edit()},
}
