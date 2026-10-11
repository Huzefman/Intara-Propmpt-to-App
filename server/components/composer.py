"""
Composer — resolves a component selection into an ordered, dependency-closed
build plan that maps onto the existing DAG step kinds.

Design rules:
- planned components can never be selected (composition error, never silent).
- requires[] are pulled in transitively; conflicts[] fail the composition.
- deterministic output: topological order, ties broken by component id.
- to_dag() emits the CURRENT step kinds (schema/backend_table/frontend_page +
  wiring/validate tails) so composition integrates without orchestrator changes.
  widget/workflow/integration units fold into their host page/backend node via
  the `via` annotation (dedicated kinds arrive in a later phase).
"""
from components.registry import CatalogError, check_params, get_component

# component kind -> DAG step kind + ref source param
STEP_KIND = {
    "entity": "backend_table",
    "page": "frontend_page",
}
REF_PARAM = {
    "entity": "table",
    "page": "page",
}


def compose(catalog: dict, selections: list[dict]) -> dict:
    """selections: [{id, config?}]. Returns {units, order, warnings}.

    Raises CatalogError on unknown/planned/conflicting/misconfigured components.
    """
    components = catalog.get("components", {})
    # NB: selected maps id -> [configs] (NOT id -> config): the same component
    # may be chosen repeatedly (e.g. one crud-entity per table).
    selected: dict[str, list[dict]] = {}

    def _add(cid: str, cfg: dict):
        selected.setdefault(cid, []).append(cfg)

    for sel in selections or []:
        cid = (sel or {}).get("id", "")
        entry = get_component(catalog, cid)
        if entry.get("status") == "planned":
            raise CatalogError(
                f"component {cid!r} is planned (not implemented yet) — "
                f"pick a stable alternative or wait for its release")
        problems, filled = check_params(entry, (sel or {}).get("config") or {})
        if problems:
            raise CatalogError("; ".join(problems))
        _add(cid, filled)

    # transitive requires (only stable/experimental can satisfy a dependency)
    changed = True
    while changed:
        changed = False
        for cid in list(selected.keys()):
            for dep in get_component(catalog, cid).get("requires", []) or []:
                if dep not in selected:
                    dep_entry = get_component(catalog, dep)
                    if dep_entry.get("status") == "planned":
                        raise CatalogError(
                            f"component {cid!r} requires {dep!r}, which is still planned")
                    dep_problems, filled = check_params(dep_entry, {})
                    if dep_problems:
                        raise CatalogError(
                            f"component {cid!r} requires {dep!r}, which needs config: "
                            + "; ".join(dep_problems))
                    _add(dep, filled)
                    changed = True

    # conflicts (symmetric check)
    for cid in selected:
        entry = get_component(catalog, cid)
        for other in entry.get("conflicts", []) or []:
            if other in selected:
                raise CatalogError(f"components {cid!r} and {other!r} conflict")
        for other_id, other_entry in components.items():
            if other_id in selected and cid in (other_entry.get("conflicts", []) or []):
                raise CatalogError(f"components {other_id!r} and {cid!r} conflict")

    # Deterministic emission in FIRST-SELECTION order (spec order), recursing
    # into deps first — so node emission matches the legacy DAG shape (entities
    # then pages in spec order) while staying topologically valid. Repeated
    # selections of one component each emit their own unit (one per table/page).
    units: list[dict] = []
    done: set[str] = set()
    order: list[str] = []
    emitted_count: dict[str, int] = {}

    def ensure(cid: str, stack: tuple = ()):
        if cid in done:
            return
        if cid in stack:
            raise CatalogError(f"dependency cycle: {' -> '.join(stack + (cid,))}")
        for dep in sorted(get_component(catalog, cid).get("requires", []) or []):
            if dep in selected:
                ensure(dep, stack + (cid,))
        done.add(cid)
        order.append(cid)

    for sel in selections or []:
        cid = (sel or {}).get("id", "")
        if not cid or cid not in selected:
            continue
        ensure(cid)
        # emit exactly this selection's config (auto-added dep configs sit at
        # the tail and are flushed below if never explicitly selected)
        k = emitted_count.get(cid, 0)
        cfgs = selected[cid]
        if k < len(cfgs):
            emitted_count[cid] = k + 1
            units.append({"component": cid,
                          "kind": get_component(catalog, cid).get("kind"),
                          "config": cfgs[k]})
    # flush auto-added dependency configs that had no explicit selection
    for cid in order:
        cfgs = selected[cid]
        for cfg in cfgs[emitted_count.get(cid, 0):]:
            units.append({"component": cid,
                          "kind": get_component(catalog, cid).get("kind"),
                          "config": cfg})

    warnings = []
    for cid in order:
        if get_component(catalog, cid).get("status") == "experimental":
            warnings.append(f"{cid} is experimental — output may need review")
    return {"units": units, "order": order, "warnings": warnings}


def to_dag(catalog: dict, composition: dict) -> list[dict]:
    """Map composed units onto executable DAG nodes (existing step kinds).

    entity -> backend-{table}; page -> frontend-{page}; api/widget/workflow/
    integration fold into their host node via `via` (dedicated kinds later).
    Always wrapped with schema-foundation (when tables exist) + wiring + validate.
    """
    units = composition.get("units", [])
    graph: list[dict] = []

    def _entity_tables(cfg: dict) -> list[str]:
        if isinstance(cfg.get("tables"), list):
            return [t for t in cfg["tables"] if t]
        tables = [cfg.get("table"), cfg.get("service_table"),
                  cfg.get("slot_table"), cfg.get("booking_table")]
        return [t for t in tables if t]

    tables = sorted({t for u in units if u["kind"] == "entity" for t in _entity_tables(u["config"])})
    seen_ids: set[str] = set()

    def _push(node: dict):
        # DAG ids must stay unique (DB enforces UNIQUE(wish_id, step_id))
        if node["id"] in seen_ids:
            return
        seen_ids.add(node["id"])
        graph.append(node)

    if tables:
        _push({"id": "schema-foundation", "kind": "schema", "ref": None,
               "dependsOn": [], "status": "pending",
               "promptHint": "tables+migrations"})
    for u in units:
        kind, cfg = u["kind"], u["config"]
        if kind == "entity":
            for table in _entity_tables(cfg):
                _push({"id": f"backend-{table}", "kind": "backend_table", "ref": table,
                       "dependsOn": ["schema-foundation"] if tables else [],
                       "status": "pending", "promptHint": f"models+APIs for {table}"})
        elif kind == "page":
            page = cfg.get("page")
            if not page:
                continue
            _push({"id": f"frontend-{page}", "kind": "frontend_page", "ref": page,
                   "dependsOn": ["schema-foundation"] if tables else [],
                   "status": "pending",
                   "promptHint": f"page {page}" + (f" for table {cfg['entity']}" if cfg.get("entity") else "")})
        # api/widget/workflow/integration: folded into host nodes (phase 4 kinds)
    wiring_deps = [n["id"] for n in graph if n["id"] != "schema-foundation"]
    _push({"id": "wiring", "kind": "wiring", "ref": None, "dependsOn": wiring_deps,
           "status": "pending", "promptHint": "App.tsx nav, api wiring, mock seeds"})
    _push({"id": "validate", "kind": "validate", "ref": None, "dependsOn": ["wiring"],
           "status": "pending", "promptHint": "tsc/ast/openapi gates"})
    return graph


def compose_category(catalog: dict, category: str, configs: dict | None = None) -> dict:
    """Compose a full category pack. configs: {component_id: config} overrides."""
    from components.registry import pack_for_category
    configs = configs or {}
    selections = [{"id": cid, "config": configs.get(cid, {})}
                  for cid in pack_for_category(catalog, category)]
    if not selections:
        raise CatalogError(f"unknown category {category!r}")
    return compose(catalog, selections)
