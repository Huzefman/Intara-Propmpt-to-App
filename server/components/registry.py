"""
Component registry — loads and validates the composable building-block catalog.

Catalog lives in server/components/catalog/*.json (one file per component) plus
categories.json (category -> default component sets). Entries carry a lifecycle
status: stable (generators exist), experimental (partial), planned (not yet —
selecting one is a composition error, not a silent downgrade).
"""
import json
import os
import re

CATALOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog")

REQUIRED_KEYS = {"id", "version", "kind", "title", "description", "categories",
                 "status", "requires", "conflicts", "params", "generator", "gates",
                 "capabilities"}
KNOWN_KINDS = {"entity", "page", "api", "widget", "workflow", "integration"}
KNOWN_STATUS = {"stable", "experimental", "planned"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


class CatalogError(ValueError):
    pass


def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_entry(entry: dict, source: str = "?") -> list[str]:
    """Return problem list (empty = valid). Never raises on bad shapes."""
    problems = []
    if not isinstance(entry, dict):
        return [f"{source}: entry must be an object"]
    missing = REQUIRED_KEYS - set(entry.keys())
    if missing:
        problems.append(f"{source}: missing keys {sorted(missing)}")
    eid = entry.get("id", "?")
    if entry.get("kind") not in KNOWN_KINDS:
        problems.append(f"{eid}: unknown kind {entry.get('kind')!r}")
    if entry.get("status") not in KNOWN_STATUS:
        problems.append(f"{eid}: unknown status {entry.get('status')!r}")
    if not SEMVER.match(str(entry.get("version", ""))):
        problems.append(f"{eid}: version must be semver, got {entry.get('version')!r}")
    if not isinstance(entry.get("categories"), list) or not entry.get("categories"):
        problems.append(f"{eid}: categories must be a non-empty list")
    for key in ("requires", "conflicts", "gates", "capabilities"):
        if not isinstance(entry.get(key), list):
            problems.append(f"{eid}: {key} must be a list")
    params = entry.get("params")
    if not isinstance(params, dict):
        problems.append(f"{eid}: params must be an object")
    else:
        for pname, pspec in params.items():
            if not isinstance(pspec, dict) or pspec.get("type") not in ("string", "array", "integer", "boolean", "object"):
                problems.append(f"{eid}: param {pname!r} needs a type in string|array|integer|boolean|object")
    gen = entry.get("generator")
    if not isinstance(gen, dict):
        problems.append(f"{eid}: generator must be an object")
    return problems


def load_catalog(catalog_dir: str = CATALOG_DIR) -> dict:
    """Load + validate the whole catalog. Returns {components, categories, version}.

    Raises CatalogError aggregating every problem (fail-closed: a broken catalog
    must never silently generate)."""
    components: dict[str, dict] = {}
    problems: list[str] = []
    try:
        names = sorted(os.listdir(catalog_dir))
    except Exception as e:
        raise CatalogError(f"catalog dir unreadable: {e}")
    for name in names:
        if name == "categories.json" or not name.endswith(".json"):
            continue
        path = os.path.join(catalog_dir, name)
        try:
            entry = _load_json(path)
        except Exception as e:
            problems.append(f"{name}: invalid JSON: {e}")
            continue
        problems.extend(validate_entry(entry, name))
        eid = entry.get("id", name)
        if eid in components:
            problems.append(f"{name}: duplicate component id {eid!r}")
        components[eid] = entry
    # dangling references
    for eid, entry in components.items():
        if not isinstance(entry, dict):
            continue
        for dep in entry.get("requires", []) or []:
            if dep not in components:
                problems.append(f"{eid}: requires unknown component {dep!r}")
        for other in entry.get("conflicts", []) or []:
            if other not in components:
                problems.append(f"{eid}: conflicts with unknown component {other!r}")
    categories: dict[str, list[str]] = {}
    cat_path = os.path.join(catalog_dir, "categories.json")
    try:
        cat_doc = _load_json(cat_path)
        categories = cat_doc.get("packs", {})
        for cat, ids in categories.items():
            for cid in ids:
                if cid not in components:
                    problems.append(f"categories.json: pack {cat!r} references unknown {cid!r}")
    except Exception as e:
        problems.append(f"categories.json: {e}")
    if problems:
        raise CatalogError("; ".join(problems))
    version = max((e.get("version", "0.0.0") for e in components.values()), default="0.0.0")
    return {"components": components, "categories": categories, "version": version}


def get_component(catalog: dict, component_id: str) -> dict:
    try:
        return catalog["components"][component_id]
    except KeyError:
        raise CatalogError(f"unknown component {component_id!r}")


def pack_for_category(catalog: dict, category: str) -> list[str]:
    """Default component id list for an app category. Unknown category -> []."""
    return list((catalog.get("categories") or {}).get(category, []))


def check_params(entry: dict, config: dict) -> list[str]:
    """Validate a component config against its param schema. Missing required
    params with defaults are filled and returned via (problems, filled)."""
    problems = []
    filled = dict(config or {})
    for pname, pspec in (entry.get("params") or {}).items():
        if pname not in filled:
            if "default" in pspec:
                filled[pname] = pspec["default"]
            elif pspec.get("required"):
                problems.append(f"{entry.get('id')}: missing required param {pname!r}")
    return problems, filled
