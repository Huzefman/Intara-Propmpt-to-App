"""
G1 — semantic lint (Phase 4, P4.2; rule list = guide §9).

Every rule has a code (R01…); findings carry rule + message + JSON path.
`lint(spec)` returns {"errors": [...], "warnings": [...]}; empty errors = G1
passes. Warnings (experimental blocks) never fail the gate.

Reachability interpretations (documented, deterministic):
- A page is reachable when listed in nav OR referenced by another page's
  block props (row_link) — detail pages are linked, not nav'd.
- A page with empty roles is public: it counts for every role.
- Lifecycle states = explicit `states` when present, else the enum values of
  the lifecycle field; reachable = BFS from `initial` over transitions.
"""
from __future__ import annotations

import re
from typing import Any

ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TEMPLATE_VAR_RE = re.compile(r"\{([^{}]+)\}")

# Minimal catalog slice the linter enforces. Full catalog lives in
# server/components/ (Track B); spec blocks reference this stable set.
BLOCKS: dict = {
    "data.table": {"stability": "stable", "required_props": ["entity"]},
    "data.kanban": {"stability": "stable", "required_props": ["entity", "group_by"]},
    "metric.stat": {"stability": "stable", "required_props": ["entity"]},
    "filter.bar": {"stability": "stable", "required_props": ["entity"]},
    "record.detail": {"stability": "stable", "required_props": ["entity"]},
    "record.related_list": {"stability": "stable", "required_props": ["entity"]},
    "lifecycle.pipeline": {"stability": "stable", "required_props": ["entity"]},
    "metric.gauge": {"stability": "experimental", "required_props": ["entity"]},
    "form.record": {"stability": "stable", "required_props": ["entity"]},
    "chart.bar": {"stability": "stable", "required_props": ["entity"]},
    "calendar.month": {"stability": "stable", "required_props": ["entity"]},
    "activity.timeline": {"stability": "stable", "required_props": ["entity"]},
    "file.list": {"stability": "stable", "required_props": ["entity"]},
    "content.hero": {"stability": "stable", "required_props": []},
}

AUTO_ACTIONS = {"set_field", "create_record", "send_email", "notify", "webhook", "export_csv"}
AUTO_TRIGGERS = {"record.created", "record.updated", "lifecycle.transition", "schedule", "manual_button"}


def _finding(rule: str, message: str, path: str) -> dict:
    return {"rule": rule, "message": message, "path": path}


def _formula_names(formula: str) -> set:
    """Top-level variable roots referenced by a formula (parse must succeed)."""
    from engine.formula import parse
    node = parse(formula)
    names: set = set()

    def walk(n):
        if not isinstance(n, (list, tuple)) or not n:
            return
        tag = n[0]
        if tag == "var":
            names.add(n[1][0])
        else:
            for child in n[1:]:
                walk(child)

    walk(node)
    return names


def _check_formula(formula, visible: dict[str, set], path: str,
                   errors: list, syntax_rule: str, name_rule: str):
    """Parse-check (syntax_rule) + name resolution (name_rule) for a formula."""
    from engine.formula import parse, FormulaSyntaxError
    if not isinstance(formula, str) or not formula.strip():
        errors.append(_finding(syntax_rule, "empty formula", path))
        return
    try:
        node = parse(formula)
    except FormulaSyntaxError as e:
        errors.append(_finding(syntax_rule, f"formula does not parse: {e}", path))
        return
    # walk vars with full paths for dotted validation
    problems: list = []

    def walk(n):
        if not isinstance(n, (list, tuple)) or not n:
            return
        if n[0] == "var":
            p = tuple(n[1])
            root = p[0]
            if root in ("true", "false", "null"):
                return
            if root not in visible:
                problems.append(f"unknown field {root!r}")
            elif len(p) > 1 and visible[root] is not None and p[1] not in visible[root]:
                problems.append(f"unknown field {'.'.join(p)!r}")
        else:
            for child in n[1:]:
                walk(child)

    walk(node)
    for prob in problems:
        errors.append(_finding(name_rule, prob, path))


def lint(spec: dict) -> dict:
    errors: list = []
    warnings: list = []
    spec = spec if isinstance(spec, dict) else {}
    model = spec.get("model") or {}
    enums = {e.get("id"): e for e in model.get("enums") or [] if isinstance(e, dict)}
    entities = {e.get("id"): e for e in model.get("entities") or [] if isinstance(e, dict)}
    access = spec.get("access") or {}
    roles = {r.get("id"): r for r in access.get("roles") or [] if isinstance(r, dict)}
    ui = spec.get("ui") or {}
    pages = {p.get("id"): p for p in ui.get("pages") or [] if isinstance(p, dict)}

    def dupes(items: list, path: str, rule: str, what: str):
        seen: dict = {}
        for it in items:
            iid = it.get("id") if isinstance(it, dict) else None
            if iid in seen:
                errors.append(_finding(rule, f"duplicate {what} id {iid!r}", path))
            elif iid is not None:
                seen[iid] = True

    # R01–R07 uniqueness
    dupes(model.get("enums") or [], "model.enums", "R01", "enum")
    dupes(model.get("entities") or [], "model.entities", "R02", "entity")
    for e in model.get("entities") or []:
        if isinstance(e, dict):
            dupes(e.get("fields") or [], f"model.entities.{e.get('id')}.fields", "R03", "field")
    dupes(ui.get("pages") or [], "ui.pages", "R04", "page")
    for p in ui.get("pages") or []:
        if isinstance(p, dict):
            dupes(p.get("blocks") or [], f"ui.pages.{p.get('id')}.blocks", "R05", "block")
    dupes(access.get("roles") or [], "access.roles", "R06", "role")

    # R08 id format (spot-check the id-carrying kinds)
    def check_id(iid, path: str):
        if isinstance(iid, str) and not ID_RE.match(iid):
            errors.append(_finding("R08", f"id {iid!r} must be snake_case", path))

    for eid, e in entities.items():
        check_id(eid, f"model.entities.{eid}")
        for f in (e.get("fields") or []):
            if isinstance(f, dict):
                check_id(f.get("id"), f"model.entities.{eid}.fields.{f.get('id')}")
        lc = e.get("lifecycle") or {}
        for t in lc.get("transitions") or []:
            if isinstance(t, dict):
                check_id(t.get("id"), f"model.entities.{eid}.lifecycle.transitions.{t.get('id')}")
    for pid, p in pages.items():
        check_id(pid, f"ui.pages.{pid}")
        for b in (p.get("blocks") or []):
            if isinstance(b, dict):
                check_id(b.get("id"), f"ui.pages.{pid}.blocks.{b.get('id')}")
    for rid in roles:
        check_id(rid, f"access.roles.{rid}")
    for eid in enums:
        check_id(eid, f"model.enums.{eid}")
    for a in spec.get("automations") or []:
        if isinstance(a, dict):
            check_id(a.get("id"), f"automations.{a.get('id')}")

    # R07 duplicate transition ids
    for eid, e in entities.items():
        trans = ((e.get("lifecycle") or {}).get("transitions") or [])
        dupes(trans, f"model.entities.{eid}.lifecycle.transitions", "R07", "transition")

    # field-type closed set is G0; G1 needs per-entity field maps
    fields_of: dict = {}
    for eid, e in entities.items():
        fields_of[eid] = {f.get("id"): f for f in (e.get("fields") or []) if isinstance(f, dict)}

    # relation accessors: ref fields' relation_name visible on the TARGET entity
    accessors: dict = {eid: set() for eid in entities}
    accessor_target: dict = {}
    for eid, e in entities.items():
        for fid, f in fields_of[eid].items():
            if f.get("type") in ("ref", "multi_ref") and f.get("relation_name"):
                tgt = f.get("target")
                if tgt in accessors:
                    accessors[tgt].add(f["relation_name"])
                    accessor_target[(tgt, f["relation_name"])] = eid

    # R09/R10 ref + enum targets
    for eid, e in entities.items():
        for fid, f in fields_of[eid].items():
            p = f"model.entities.{eid}.fields.{fid}"
            if f.get("type") in ("ref", "multi_ref") and f.get("target") not in entities:
                errors.append(_finding("R09", f"ref target {f.get('target')!r} does not exist", p))
            if f.get("type") in ("enum", "multi_enum") and f.get("enum") not in enums:
                errors.append(_finding("R10", f"enum {f.get('enum')!r} does not exist", p))

    # R14–R18 lifecycles
    for eid, e in entities.items():
        lc = e.get("lifecycle")
        if not lc:
            continue
        base = f"model.entities.{eid}.lifecycle"
        fld = (fields_of[eid].get(lc.get("field")) or {})
        if not fld or fld.get("type") != "enum" or fld.get("enum") not in enums:
            errors.append(_finding("R14", f"lifecycle field {lc.get('field')!r} must be an enum-typed field", base))
            continue
        values = [v.get("value") for v in enums[fld["enum"]].get("values", [])]
        states = lc.get("states") or values
        if lc.get("initial") not in values:
            errors.append(_finding("R15", f"initial {lc.get('initial')!r} not in enum {fld['enum']!r}", base))
        for t in lc.get("transitions") or []:
            tp = f"{base}.transitions.{t.get('id')}"
            if t.get("from") not in states:
                errors.append(_finding("R16", f"transition from-state {t.get('from')!r} unknown", tp))
            if t.get("to") not in states:
                errors.append(_finding("R16", f"transition to-state {t.get('to')!r} unknown", tp))
            for r in t.get("roles") or []:
                if r not in roles:
                    errors.append(_finding("R17", f"transition role {r!r} does not exist", tp))
            if t.get("guard"):
                efields = set(fields_of[eid]) | accessors.get(eid, set())
                visible = {k: (None if k in fields_of[eid] else
                               set(fields_of.get(accessor_target.get((eid, k), ""), {})))
                           for k in efields}
                _check_formula(t["guard"], visible, tp + ".guard", errors, "R24", "R24")
        # R18 reachability from initial
        adj: dict = {}
        for t in lc.get("transitions") or []:
            adj.setdefault(t.get("from"), set()).add(t.get("to"))
        seen = {lc.get("initial")}
        stack = [lc.get("initial")]
        while stack:
            cur = stack.pop()
            for nxt in adj.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        for s in states:
            if s not in seen:
                errors.append(_finding("R18", f"lifecycle state {s!r} unreachable from initial", base))

    # R11/R29/R30/R31 blocks + R12 page roles + collect entity usage
    used_entities: set = set()
    for pid, p in pages.items():
        for r in p.get("roles") or []:
            if r not in roles:
                errors.append(_finding("R12", f"page role {r!r} does not exist", f"ui.pages.{pid}"))
        for b in p.get("blocks") or []:
            if not isinstance(b, dict):
                continue
            bp = f"ui.pages.{pid}.blocks.{b.get('id')}"
            btype = b.get("type") or ""
            info = BLOCKS.get(btype)
            if info is None:
                if btype.split(".")[0] == "planned" or btype.startswith("planned"):
                    errors.append(_finding("R30", f"planned block {btype!r} cannot ship", bp))
                else:
                    errors.append(_finding("R29", f"unknown block type {btype!r}", bp))
                continue
            if info["stability"] == "experimental":
                warnings.append(_finding("W01", f"experimental block {btype!r}", bp))
            props = b.get("props") or {}
            for req in info["required_props"]:
                if req not in props:
                    errors.append(_finding("R31", f"block {btype!r} missing required prop {req!r}", bp))
            ent = props.get("entity")
            if ent is not None:
                if ent not in entities:
                    errors.append(_finding("R11", f"block entity {ent!r} does not exist", bp))
                else:
                    used_entities.add(ent)

    # R13 nav targets
    nav_pages = set()
    for n in ui.get("nav") or []:
        if isinstance(n, dict):
            if n.get("page") not in pages:
                errors.append(_finding("R13", f"nav page {n.get('page')!r} does not exist", "ui.nav"))
            else:
                nav_pages.add(n["page"])

    # R20 page reachability (nav or row_link from another page)
    linked = set()
    for p in pages.values():
        for b in (p.get("blocks") or []):
            if isinstance(b, dict):
                rl = (b.get("props") or {}).get("row_link")
                if isinstance(rl, str) and rl in pages:
                    linked.add(rl)
    for pid in pages:
        if pid not in nav_pages and pid not in linked:
            errors.append(_finding("R20", f"page {pid!r} unreachable (not in nav, no row_link)", f"ui.pages.{pid}"))

    # R19 entity coverage
    for eid in entities:
        if eid not in used_entities:
            errors.append(_finding("R19", f"entity {eid!r} appears in no page/block", f"model.entities.{eid}"))

    # R21 role coverage (empty page roles = public)
    covered: set = set()
    for p in pages.values():
        pr = p.get("roles") or []
        if not pr:
            covered.update(roles)
        else:
            covered.update(r for r in pr if r in roles)
    for rid in roles:
        if rid not in covered:
            errors.append(_finding("R21", f"role {rid!r} has no page", f"access.roles.{rid}"))

    # R22/R23 computed formulas
    for eid, e in entities.items():
        efields = set(fields_of[eid]) | accessors.get(eid, set())
        visible = {k: (None if k in fields_of[eid] else
                       set(fields_of.get(accessor_target.get((eid, k), ""), {})))
                   for k in efields}
        for fid, f in fields_of[eid].items():
            comp = f.get("computed") or {}
            if comp.get("formula") is not None:
                # R22 = parses, R23 = names resolve
                _check_formula(comp["formula"], visible,
                               f"model.entities.{eid}.fields.{fid}.computed", errors, "R22", "R23")

    # R32 default/type fit
    def _fit(ftype: str, value: Any) -> bool:
        if value is None:
            return True
        if ftype == "int":
            return isinstance(value, int) and not isinstance(value, bool)
        if ftype in ("decimal", "money", "rating"):
            return (isinstance(value, (int, float)) and not isinstance(value, bool))
        if ftype == "bool":
            return isinstance(value, bool)
        if ftype in ("text", "longtext", "email", "phone", "url", "date", "datetime",
                     "time", "file", "image", "color"):
            return isinstance(value, str)
        if ftype == "multi_enum":
            return isinstance(value, list) and all(isinstance(x, str) for x in value)
        if ftype == "multi_ref":
            return isinstance(value, list)
        return True  # enum (membership below), ref, json: structural only here

    for eid, e in entities.items():
        for fid, f in fields_of[eid].items():
            if "default" in f and not _fit(f.get("type"), f.get("default")):
                errors.append(_finding(
                    "R32", f"default {f.get('default')!r} does not fit type {f.get('type')!r}",
                    f"model.entities.{eid}.fields.{fid}"))
            if f.get("type") == "enum" and isinstance(f.get("default"), str):
                enum_vals = [v.get("value") for v in (enums.get(f.get("enum")) or {}).get("values", [])]
                if f.get("enum") in enums and f["default"] not in enum_vals:
                    errors.append(_finding(
                        "R32", f"default {f.get('default')!r} not in enum {f.get('enum')!r}",
                        f"model.entities.{eid}.fields.{fid}"))

    # R33 display template vars resolve
    for eid, e in entities.items():
        disp = e.get("display") or {}
        for slot in ("title", "subtitle"):
            tpl = disp.get(slot)
            if not isinstance(tpl, str):
                continue
            for var in TEMPLATE_VAR_RE.findall(tpl):
                segs = var.split(".")
                if segs[0] not in fields_of[eid]:
                    errors.append(_finding(
                        "R33", f"display {{{var}}} references unknown field",
                        f"model.entities.{eid}.display.{slot}"))
                elif len(segs) > 1:
                    base = fields_of[eid][segs[0]]
                    if base.get("type") in ("ref", "multi_ref"):
                        tgt_fields = fields_of.get(base.get("target"), {})
                        if segs[1] not in tgt_fields:
                            errors.append(_finding(
                                "R33", f"display {{{var}}} references unknown field",
                                f"model.entities.{eid}.display.{slot}"))
                    elif segs[1] not in fields_of[eid]:
                        errors.append(_finding(
                            "R33", f"display {{{var}}} references unknown field",
                            f"model.entities.{eid}.display.{slot}"))

    # R26–R28 automations
    for a in spec.get("automations") or []:
        if not isinstance(a, dict):
            continue
        ap = f"automations.{a.get('id')}"
        trig = a.get("trigger") or {}
        if trig.get("type") not in AUTO_TRIGGERS:
            errors.append(_finding("R26", f"unknown trigger {trig.get('type')!r}", ap))
            continue
        trig_ent = trig.get("entity")
        if trig.get("type") in ("record.created", "record.updated", "lifecycle.transition"):
            if trig_ent not in entities:
                errors.append(_finding("R26", f"trigger entity {trig_ent!r} does not exist", ap))
                trig_ent = None
        if trig.get("type") == "lifecycle.transition" and trig_ent:
            trans_ids = {t.get("id") for t in
                         ((entities[trig_ent].get("lifecycle") or {}).get("transitions") or [])}
            if trig.get("transition") not in trans_ids:
                errors.append(_finding("R27", f"transition {trig.get('transition')!r} does not exist", ap))
        ctx_fields = set(fields_of.get(trig_ent, {})) | accessors.get(trig_ent, set()) if trig_ent else set()
        for i, step in enumerate(a.get("steps") or []):
            if not isinstance(step, dict):
                continue
            sp = f"{ap}.steps.{i}"
            if step.get("action") not in AUTO_ACTIONS:
                errors.append(_finding("R28", f"unknown action {step.get('action')!r}", sp))
                continue
            if step.get("action") == "set_field" and trig_ent:
                fld = (step.get("params") or {}).get("field")
                if fld not in fields_of.get(trig_ent, {}):
                    errors.append(_finding("R28", f"set_field unknown field {fld!r}", sp))
            if step.get("action") == "create_record":
                ent = (step.get("params") or {}).get("entity")
                if ent not in entities:
                    errors.append(_finding("R28", f"create_record unknown entity {ent!r}", sp))
            if step.get("when") and trig_ent:
                visible = {k: None for k in ctx_fields}
                _check_formula(step["when"], visible, sp + ".when", errors, "R25", "R25")

    # R34/R35/R36 seed + access
    seed = spec.get("seed") or {}
    if isinstance(seed, dict):
        for ent, rows in seed.items():
            if ent not in entities:
                errors.append(_finding("R34", f"seed entity {ent!r} does not exist", f"seed.{ent}"))
        keys: dict = {}  # _key -> entity
        for ent, rows in seed.items():
            if not isinstance(rows, list):
                continue
            for r in rows:
                if isinstance(r, dict) and isinstance(r.get("_key"), str):
                    if r["_key"] in keys:
                        errors.append(_finding("R35", f"duplicate seed key {r['_key']!r}", f"seed.{ent}"))
                    keys[r["_key"]] = ent
        for ent, rows in seed.items():
            if ent not in entities or not isinstance(rows, list):
                continue
            for r in rows:
                if not isinstance(r, dict):
                    continue
                for fname, val in r.items():
                    if fname.startswith("_"):
                        continue
                    if isinstance(val, str) and val.startswith("@"):
                        key = val[1:]
                        fdef = fields_of[ent].get(fname, {})
                        tgt = fdef.get("target") if fdef.get("type") in ("ref", "multi_ref") else None
                        if tgt:
                            if keys.get(key) != tgt:
                                errors.append(_finding(
                                    "R35", f"seed @{key} does not resolve to {tgt!r}",
                                    f"seed.{ent}"))
                        elif key not in keys:
                            errors.append(_finding(
                                "R35", f"seed @{key} does not resolve", f"seed.{ent}"))
    for i, rule in enumerate(access.get("rules") or []):
        if not isinstance(rule, dict):
            continue
        rp = f"access.rules.{i}"
        if rule.get("role") not in roles:
            errors.append(_finding("R36", f"rule role {rule.get('role')!r} does not exist", rp))
        if rule.get("entity") != "*" and rule.get("entity") not in entities:
            errors.append(_finding("R36", f"rule entity {rule.get('entity')!r} does not exist", rp))

    return {"errors": errors, "warnings": warnings}
