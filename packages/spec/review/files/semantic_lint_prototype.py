"""Prototype semantic lint for App Specs (see REVIEW_NOTES.md). The builder helpers at the top are only for generating the golds; port the section under # ---- checker."""
import json, re
from datetime import datetime

def F(id, type, *, enum=None, index=None, target=None, unique=None, default=None,
      computed=None, onDelete=None, required=None, relation_name=None):
    return {"id": id, "enum": enum, "type": type, "index": index, "target": target,
            "unique": unique, "default": default, "computed": computed,
            "onDelete": onDelete, "required": required, "relation_name": relation_name}

def REF(id, target, rel, *, onDelete="restrict", required=None, index=None):
    return F(id, "ref", target=target, relation_name=rel, onDelete=onDelete, required=required, index=index)

def E(id, vals):
    return {"id": id, "values": [{"color": c, "label": l, "value": v} for v, l, c in vals]}

def T(id, frm, to, label, roles, guard=None):
    return {"id": id, "to": to, "from": frm, "guard": guard, "label": label, "roles": roles}

def LC(field, states, initial, transitions):
    return {"field": field, "states": states, "initial": initial, "transitions": transitions}

def ENT(id, icon, label, plural, fields, display, lifecycle=None):
    return {"id": id, "icon": icon, "label": label, "fields": fields, "plural": plural,
            "display": display, "lifecycle": lifecycle}

def R(role, entity, ops, where=None):
    return {"ops": ops, "role": role, "where": where, "entity": entity}

ALL = ["read", "create", "update", "delete"]

def AUTO(id, trigger_type, entity, steps, schedule=None, transition=None):
    return {"id": id, "steps": steps,
            "trigger": {"type": trigger_type, "entity": entity, "schedule": schedule, "transition": transition}}

def STEP(action, params, when=None):
    return {"when": when, "action": action, "params": params}

# ---- blocks ----
def B(id, type, **props): return {"id": id, "type": type, "props": props}
def table(id, entity, columns, row_link=None, create=False):
    p = {"entity": entity, "columns": columns}
    if row_link: p["row_link"] = row_link
    if create: p["create"] = True
    return B(id, "data.table", **p)
def stat(id, entity, items): return B(id, "metric.stat", entity=entity, items=items)
def chart_bar(id, entity, title, x, y="count"): return B(id, "chart.bar", entity=entity, title=title, x=x, y=y)
def detail(id, entity, sections): return B(id, "record.detail", entity=entity, sections=[{"title": t, "fields": f} for t, f in sections])
def related(id, entity, via, columns, row_link=None, create=False):
    p = {"entity": entity, "via": via, "columns": columns}
    if row_link: p["row_link"] = row_link
    if create: p["create"] = True
    return B(id, "record.related_list", **p)
def filterbar(id, entity, fields, search): return B(id, "filter.bar", entity=entity, fields=fields, search=search)
def pipeline(id, entity): return B(id, "lifecycle.pipeline", entity=entity)
def kanban(id, entity, group_by, title, subtitle, badges, drag=True):
    return B(id, "data.kanban", entity=entity, group_by=group_by,
             card={"title": title, "subtitle": subtitle, "badges": badges}, drag_transitions=drag)
def calendar(id, entity, date_field, row_link): return B(id, "calendar.month", entity=entity, date_field=date_field, row_link=row_link)
def timeline(id, entity, date_field, title): return B(id, "activity.timeline", entity=entity, date_field=date_field, title=title)
def form(id, entity): return B(id, "form.record", entity=entity)
def hero(id, title, subtitle): return B(id, "content.hero", title=title, subtitle=subtitle)

def PAGE(id, route, title, roles, blocks, layout="grid"):
    return {"id": id, "roles": roles, "route": route, "title": title, "blocks": blocks, "layout": layout}

def NAV(page, label, icon, roles): return {"icon": icon, "page": page, "label": label, "roles": roles}

# ---------------- checker ----------------
KW = {"and", "or", "not", "null", "true", "false", "in"}
BLOCK_KEYS = {
 "data.table": {"entity","columns","row_link","create"},
 "metric.stat": {"entity","items"},
 "chart.bar": {"entity","title","x","y"},
 "record.detail": {"entity","sections"},
 "record.related_list": {"entity","via","columns","row_link","create"},
 "filter.bar": {"entity","fields","search"},
 "lifecycle.pipeline": {"entity"},
 "data.kanban": {"entity","group_by","card","drag_transitions"},
 "calendar.month": {"entity","date_field","row_link"},
 "activity.timeline": {"entity","date_field","title"},
 "form.record": {"entity"},
 "content.hero": {"title","subtitle"},
}

def check(spec, name):
    errs, warns = [], []
    m = spec["model"]
    ents = {e["id"]: e for e in m["entities"]}
    enums = {e["id"]: [v["value"] for v in e["values"]] for e in m["enums"]}
    roles = {r["id"] for r in spec["access"]["roles"]}
    pages = {p["id"]: p for p in spec["ui"]["pages"]}
    fld = {e: {f["id"]: f for f in ents[e]["fields"]} for e in ents}
    incoming = {}  # (entity, relation_name) -> child entity
    for e in ents.values():
        for f in e["fields"]:
            if f["type"] == "ref":
                if f["target"] not in ents: errs.append(f"{e['id']}.{f['id']}: ref target {f['target']} missing")
                if f.get("relation_name"): incoming[(f["target"], f["relation_name"])] = (e["id"], f["id"])
            if f["type"] == "enum" and f["enum"] not in enums: errs.append(f"{e['id']}.{f['id']}: enum {f['enum']} missing")
    # forbidden filler
    for e in ents.values():
        for f in e["fields"]:
            if f["id"] in ("id", "created_at", "updated_at"): errs.append(f"{e['id']}.{f['id']}: system/filler field")
            if f["type"] == "ref" and f["id"].endswith("_id"): errs.append(f"{e['id']}.{f['id']}: ref named *_id")

    def resolve(ent, path, ctx, allow_rel=True):
        """returns (ok, [entities traversed])"""
        cur, trav = ent, []
        segs = path.split(".")
        for i, s in enumerate(segs):
            last = i == len(segs) - 1
            if s in fld[cur]:
                f = fld[cur][s]
                if f["type"] == "ref":
                    if not last: trav.append(f["target"]); cur = f["target"]
                elif not last:
                    errs.append(f"{ctx}: '{path}' traverses non-ref '{s}'"); return False, trav
            elif allow_rel and (cur, s) in incoming:
                cur = incoming[(cur, s)][0]; trav.append(cur)
                if last: return True, trav
            else:
                errs.append(f"{ctx}: '{path}' unresolved at '{s}' on {cur}"); return False, trav
        return True, trav

    def idents(expr):
        e2 = re.sub(r"'[^']*'|\"[^\"]*\"", " ", expr)
        for m_ in re.finditer(r"[$A-Za-z_][\w$]*(?:\.[A-Za-z_]\w*)*", e2):
            tok = m_.group(0)
            if tok.lower() in KW: continue
            rest = e2[m_.end():].lstrip()
            if rest.startswith("("): continue
            if tok.startswith("$user"): continue
            yield tok

    def check_expr(ent, expr, ctx):
        if expr is None: return
        for tok in idents(expr): resolve(ent, tok, ctx)

    # lifecycle
    for e in ents.values():
        lc = e.get("lifecycle")
        if not lc: continue
        f = fld[e["id"]].get(lc["field"])
        if not f or f["type"] != "enum": errs.append(f"{e['id']}: lifecycle field {lc['field']} not enum"); continue
        ev = set(enums[f["enum"]])
        if set(lc["states"]) != ev: errs.append(f"{e['id']}: lifecycle states != enum values")
        if lc["initial"] not in lc["states"]: errs.append(f"{e['id']}: bad initial")
        if f.get("default") != lc["initial"]: errs.append(f"{e['id']}: enum default != lifecycle initial")
        tids = set()
        reach = {lc["initial"]}
        for t in lc["transitions"]:
            if t["id"] in tids: errs.append(f"{e['id']}: dup transition {t['id']}")
            tids.add(t["id"])
            if t["from"] not in lc["states"] or t["to"] not in lc["states"]: errs.append(f"{e['id']}.{t['id']}: bad state")
            for r in t["roles"]:
                if r not in roles: errs.append(f"{e['id']}.{t['id']}: role {r} missing")
            check_expr(e["id"], t["guard"], f"{e['id']}.{t['id']}.guard")
        ch = True
        while ch:
            ch = False
            for t in lc["transitions"]:
                if t["from"] in reach and t["to"] not in reach: reach.add(t["to"]); ch = True
        if reach != set(lc["states"]): errs.append(f"{e['id']}: unreachable states {set(lc['states'])-reach}")
    # computed
    for e in ents.values():
        for f in e["fields"]:
            if f.get("computed"): check_expr(e["id"], f["computed"]["formula"], f"{e['id']}.{f['id']}.computed")
            if f["type"] == "enum" and f.get("default") is not None and f["default"] not in enums.get(f["enum"], []):
                errs.append(f"{e['id']}.{f['id']}: bad enum default")
        d = e["display"]
        for k in ("title", "subtitle"):
            v = d.get(k)
            if v:
                for part in re.split(r"\s+-\s+|\s+", v):
                    if part and re.fullmatch(r"[A-Za-z_][\w.]*", part): resolve(e["id"], part, f"{e['id']}.display.{k}")
    # access
    rules = spec["access"]["rules"]
    rd = {}
    for i, r in enumerate(rules):
        if r["role"] not in roles: errs.append(f"rule{i}: role {r['role']}")
        if r["entity"] not in ents: errs.append(f"rule{i}: entity {r['entity']}")
        else: check_expr(r["entity"], r["where"], f"rule{i}.where")
        for op in r["ops"]:
            if op not in ALL: errs.append(f"rule{i}: op {op}")
            rd.setdefault((r["role"], r["entity"]), set()).add(op)
    def can_read(role, ent): return "read" in rd.get((role, ent), set())
    # pages
    routes = set(); GLOBAL_BIDS = set()
    for p in spec["ui"]["pages"]:
        if p["route"] in routes: errs.append(f"dup route {p['route']}")
        routes.add(p["route"])
        for r in p["roles"]:
            if r not in roles: errs.append(f"page {p['id']}: role {r}")
        bids = set()
        det_ent = None
        for b in p["blocks"]:
            if b["id"] in bids or b["id"] in GLOBAL_BIDS: errs.append(f"dup block id {b['id']} (block ids must be unique across the whole spec)")
            if b["id"] in pages: errs.append(f"block id {b['id']} equals a page id")
            bids.add(b["id"]); GLOBAL_BIDS.add(b["id"])
            if b["type"] == "record.detail": det_ent = b["props"]["entity"]
        if ":id" in p["route"] and det_ent is None: errs.append(f"page {p['id']}: param route without record.detail")
        for b in p["blocks"]:
            t, pr, ctx = b["type"], b["props"], f"{p['id']}.{b['id']}"
            if t not in BLOCK_KEYS: errs.append(f"{ctx}: unknown block {t}"); continue
            extra = set(pr) - BLOCK_KEYS[t]
            if extra: errs.append(f"{ctx}: unexpected props {extra}")
            ent = pr.get("entity")
            if ent:
                if ent not in ents: errs.append(f"{ctx}: entity {ent}"); continue
                for r in p["roles"]:
                    if not can_read(r, ent): errs.append(f"{ctx}: page role '{r}' has no read rule on {ent}")
            fields = []
            if t in ("data.table", "record.related_list"): fields = pr["columns"]
            if t == "filter.bar": fields = pr["fields"] + pr["search"]
            if t == "record.detail": fields = [f for s in pr["sections"] for f in s["fields"]]
            if t == "chart.bar": fields = [pr["x"]]
            if t == "data.kanban": fields = [pr["group_by"], pr["card"]["title"], pr["card"]["subtitle"]] + pr["card"]["badges"]
            if t in ("calendar.month", "activity.timeline"): fields = [pr["date_field"]]
            if t == "metric.stat":
                for it in pr["items"]:
                    check_expr(ent, it.get("where"), ctx + ".where")
                    if it.get("field"): resolve(ent, it["field"], ctx)
            for f in fields:
                ok, trav = resolve(ent, f, ctx, allow_rel=False)
                for r in p["roles"]:
                    for te in trav:
                        if not can_read(r, te): warns.append(f"{ctx}: role '{r}' shows {f} but cannot read {te}")
            if t == "record.related_list":
                via = pr["via"]
                if via not in fld[ent] or fld[ent][via]["type"] != "ref": errs.append(f"{ctx}: via {via} not ref on {ent}")
                elif det_ent and fld[ent][via]["target"] != det_ent: errs.append(f"{ctx}: via target {fld[ent][via]['target']} != page record {det_ent}")
            if t == "data.kanban" and fld[ent][pr["group_by"]]["type"] != "enum": errs.append(f"{ctx}: group_by not enum")
            if t == "lifecycle.pipeline" and not ents[ent]["lifecycle"]: errs.append(f"{ctx}: entity has no lifecycle")
            if "row_link" in pr:
                tgt = pages.get(pr["row_link"])
                if not tgt: errs.append(f"{ctx}: row_link {pr['row_link']} missing")
                elif ":id" not in tgt["route"]: errs.append(f"{ctx}: row_link target not a detail page")
                else:
                    tent = next((bb["props"]["entity"] for bb in tgt["blocks"] if bb["type"] == "record.detail"), None)
                    if tent != ent: errs.append(f"{ctx}: row_link {pr['row_link']} shows {tent}, rows are {ent}")
                    for r in p["roles"]:
                        if r not in tgt["roles"]: warns.append(f"{ctx}: role '{r}' sees row_link {pr['row_link']} but is not allowed on it")
    # nav
    navroles = set()
    for n in spec["ui"]["nav"]:
        pg = pages.get(n["page"])
        if not pg: errs.append(f"nav {n['page']} missing"); continue
        if ":id" in pg["route"]: errs.append(f"nav -> param page {n['page']}")
        for r in n["roles"]:
            navroles.add(r)
            if r not in pg["roles"]: errs.append(f"nav {n['page']}: role {r} not allowed on page")
        for r in pg["roles"]:
            if r not in n["roles"]: warns.append(f"page {pg['id']}: role {r} allowed but not in nav")
    for r in roles:
        if r not in navroles: errs.append(f"role {r} has no nav item")
    used = {b["props"].get("entity") for p in spec["ui"]["pages"] for b in p["blocks"]}
    for e in ents:
        if e not in used: errs.append(f"entity {e} on no page")
        for r in roles:
            pass
    # automations
    for a in spec["automations"]:
        tr = a["trigger"]; en = tr["entity"]
        if en not in ents: errs.append(f"auto {a['id']}: entity"); continue
        if tr["type"] == "lifecycle.transition":
            lc = ents[en]["lifecycle"]
            if not lc or tr["transition"] not in {t["id"] for t in lc["transitions"]}: errs.append(f"auto {a['id']}: transition")
        for s in a["steps"]:
            check_expr(en, s["when"], f"auto {a['id']}.when")
            for k, v in s["params"].items():
                if not isinstance(v, str): continue
                for tmpl in re.findall(r"\{([^{}]+)\}", v): resolve(en, tmpl.strip(), f"auto {a['id']}.{k}")
                if k in ("to", "recipients") and "{" not in v: resolve(en, v, f"auto {a['id']}.{k}")
                if k == "field": resolve(en, v, f"auto {a['id']}.field")
    # seed
    keys = {}
    for en, rows in spec["seed"].items():
        if en not in ents: errs.append(f"seed entity {en}"); continue
        for r in rows:
            k = r.get("_key")
            if not k: errs.append(f"seed {en}: row without _key"); continue
            if k in keys: errs.append(f"seed dup key {k}")
            keys[k] = en
    for e in ents:
        if e not in spec["seed"] or not spec["seed"][e]: errs.append(f"seed: no rows for {e}")
    uniq = {}
    for en, rows in spec["seed"].items():
        if en not in ents: continue
        for r in rows:
            for k, v in r.items():
                if k == "_key": continue
                if k not in fld[en]: errs.append(f"seed {en}/{r['_key']}: unknown field {k}"); continue
                f = fld[en][k]
                if f.get("computed"): errs.append(f"seed {en}/{r['_key']}: computed field {k} seeded")
                if v is None: continue
                if f["type"] == "ref":
                    if not (isinstance(v, str) and v.startswith("@")): errs.append(f"seed {en}/{r['_key']}.{k}: ref must be @key")
                    elif keys.get(v[1:]) != f["target"]: errs.append(f"seed {en}/{r['_key']}.{k}: {v} -> {keys.get(v[1:])} != {f['target']}")
                elif f["type"] == "enum":
                    if v not in enums[f["enum"]]: errs.append(f"seed {en}/{r['_key']}.{k}: enum {v}")
                elif f["type"] in ("datetime",):
                    try: datetime.fromisoformat(v.replace("Z", "+00:00"))
                    except Exception: errs.append(f"seed {en}/{r['_key']}.{k}: bad datetime {v}")
                elif f["type"] == "date":
                    try: datetime.strptime(v, "%Y-%m-%d")
                    except Exception: errs.append(f"seed {en}/{r['_key']}.{k}: bad date {v}")
                elif f["type"] in ("int",):
                    if not isinstance(v, int) or isinstance(v, bool): errs.append(f"seed {en}/{r['_key']}.{k}: int")
                elif f["type"] in ("decimal", "money"):
                    if not isinstance(v, (int, float)) or isinstance(v, bool): errs.append(f"seed {en}/{r['_key']}.{k}: number")
                elif f["type"] == "bool":
                    if not isinstance(v, bool): errs.append(f"seed {en}/{r['_key']}.{k}: bool")
                elif f["type"] == "email":
                    if "@" not in v: errs.append(f"seed {en}/{r['_key']}.{k}: email")
                if f.get("unique"):
                    if (en, k, v) in uniq: errs.append(f"seed {en}.{k}: duplicate unique {v}")
                    uniq[(en, k, v)] = 1
            for k, f in fld[en].items():
                if f.get("required") and not f.get("computed") and f.get("default") is None and r.get(k) is None:
                    errs.append(f"seed {en}/{r['_key']}: missing required {k}")
    # lifecycle guard sanity on seeds: completed visit must have notes etc -> done in builders
    # requirements / trace
    reqs = {r["id"]: r for r in spec["requirements"]}
    tr = {t["requirement"]: t["satisfied_by"] for t in spec["trace"]}
    for rid, r in reqs.items():
        if rid not in tr: errs.append(f"trace: {rid} missing")
    for rid in tr:
        if rid not in reqs: errs.append(f"trace: unknown {rid}")
    def tres(ref):
        kind, _, rest = ref.partition(":")
        if kind == "entity": return rest in ents
        if kind == "page": return rest in pages
        if kind == "automation": return rest in {a["id"] for a in spec["automations"]}
        if kind == "role": return rest in roles
        if kind == "lifecycle": return rest in ents and ents[rest]["lifecycle"] is not None
        if kind == "field":
            e_, _, f_ = rest.partition("."); return e_ in ents and f_ in fld[e_]
        return False
    for rid, refs in tr.items():
        if not refs: errs.append(f"trace {rid}: empty")
        for ref in refs:
            if not tres(ref): errs.append(f"trace {rid}: unresolved {ref}")
    # every automation/page/entity should be justified by trace (warn)
    traced = {x for refs in tr.values() for x in refs}
    for a in spec["automations"]:
        if f"automation:{a['id']}" not in traced: warns.append(f"automation {a['id']} not in trace")
    for p in spec["ui"]["pages"]:
        if f"page:{p['id']}" not in traced: warns.append(f"page {p['id']} not in trace")
    for e in ents:
        if f"entity:{e}" not in traced: warns.append(f"entity {e} not in trace")
    print(f"== {name}: {len(errs)} errors, {len(warns)} warnings | entities={len(ents)} pages={len(pages)} roles={len(roles)} "
          f"automations={len(spec['automations'])} reqs={len(reqs)} seed_rows={sum(len(v) for v in spec['seed'].values())}")
    for e in errs: print("  ERR ", e)
    for w in warns: print("  warn", w)
    return errs, warns

def skeleton(app, personas, requirements, assumptions, enums, entities, access, ui, automations, seed, trace):
    return {"ui": ui, "app": app, "seed": seed, "model": {"enums": enums, "entities": entities},
            "trace": trace, "access": access, "personas": personas, "assumptions": assumptions,
            "automations": automations, "integrations": [], "requirements": requirements, "spec_version": "1.0"}

def write(spec, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False); f.write("\n")
