#!/usr/bin/env python3
"""Generate Pydantic + TS types from packages/spec/app-spec.schema.json.

Single source of truth: the schema. NEVER hand-edit the outputs.
  python scripts/gen_spec_types.py           # regenerate
  python scripts/gen_spec_types.py --check   # CI drift check (exit 1 on diff)
Outputs:
  packages/spec/app-spec.ts        (interfaces)
  server/engine/spec_models.py     (pydantic v2 models)
"""
import difflib
import json
import keyword
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "packages" / "spec" / "app-spec.schema.json"
TS_OUT = ROOT / "packages" / "spec" / "app-spec.ts"
PY_OUT = ROOT / "server" / "engine" / "spec_models.py"

HEADER = "GENERATED from app-spec.schema.json by scripts/gen_spec_types.py — DO NOT EDIT."


def pascal(s: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[^a-zA-Z0-9]+", s) if w)


# Generated model names that would shadow typing/pydantic imports.
_RESERVED_MODELS = {"field": "SpecField"}


def model_name(defname: str) -> str:
    return _RESERVED_MODELS.get(defname, pascal(defname))


def ref_base(ref: str) -> str:
    return ref.split("/")[-1]


class Gen:
    def __init__(self, schema: dict):
        self.schema = schema
        self.defs: dict = schema.get("$defs", {})
        self.extra_models: dict = {}  # name -> object schema (inline objects)
        self.ts_chunks: list = []
        self.py_chunks: list = []

    # ---------- type mapping ----------
    def _inline_name(self, hint: str) -> str:
        # Top-level $defs keep their (possibly remapped) model names so the
        # first pass doesn't re-register them as inline extras.
        return model_name(hint) if hint in self.defs else pascal(hint)

    def ts_of(self, sch: dict, hint: str) -> str:
        if not isinstance(sch, dict):
            return "unknown"
        if "$ref" in sch:
            return model_name(ref_base(sch["$ref"]))
        t = sch.get("type")
        if t == "array":
            return f"Array<{self.ts_of(sch.get('items', {}), hint + 'Item')}>"
        if t == "object":
            props = sch.get("properties")
            if props:
                name = self._inline_name(hint)
                if name not in self.extra_models:
                    self.extra_models[name] = sch
                return name
            if sch.get("additionalProperties") is not None:
                ap = sch["additionalProperties"]
                return f"Record<string, {self.ts_of(ap, hint + 'Value')}>"
            return "Record<string, unknown>"
        if t == "string":
            if "enum" in sch:
                return " | ".join(json.dumps(e) for e in sch["enum"])
            return "string"
        if t == "integer":
            return "number"
        if t == "number":
            return "number"
        if t == "boolean":
            return "boolean"
        return "unknown"  # typeless (e.g. `default` value slot)

    def py_of(self, sch: dict, hint: str) -> str:
        if not isinstance(sch, dict):
            return "Any"
        if "$ref" in sch:
            return model_name(ref_base(sch["$ref"]))
        t = sch.get("type")
        if t == "array":
            return f"list[{self.py_of(sch.get('items', {}), hint + 'Item')}]"
        if t == "object":
            props = sch.get("properties")
            if props:
                name = self._inline_name(hint)
                if name not in self.extra_models:
                    self.extra_models[name] = sch
                return name
            if sch.get("additionalProperties") is not None:
                ap = sch["additionalProperties"]
                return f"dict[str, {self.py_of(ap, hint + 'Value')}]"
            return "dict[str, Any]"
        if t == "string":
            if "enum" in sch:
                return f"Literal[{', '.join(repr(e) for e in sch['enum'])}]"
            return "str"
        if t == "integer":
            return "int"
        if t == "number":
            return "float"
        if t == "boolean":
            return "bool"
        return "Any"

    # ---------- emitters ----------
    def emit_model_ts(self, name: str, sch: dict):
        props = sch.get("properties", {})
        required = set(sch.get("required", []))
        lines = [f"export interface {name} {{"]
        for pname, ps in props.items():
            opt = "" if pname in required else "?"
            lines.append(f"  {pname}{opt}: {self.ts_of(ps, name + pascal(pname))};")
        lines.append("}")
        self.ts_chunks.append("\n".join(lines))

    def emit_model_py(self, name: str, sch: dict):
        props = sch.get("properties", {})
        required = set(sch.get("required", []))
        lines = [f"class {name}(BaseModel):"]
        if not props:
            lines.append("    pass")
        for pname, ps in props.items():
            attr = pname + "_" if keyword.iskeyword(pname) else pname
            alias = f', alias="{pname}"' if attr != pname else ""
            ann = self.py_of(ps, name + pascal(pname))
            pat = ps.get("pattern") if isinstance(ps, dict) else None
            dflt = ps.get("default", None) if isinstance(ps, dict) else None
            has_default = isinstance(ps, dict) and "default" in ps
            if pname in required and not has_default:
                if pat or alias:
                    opts = "".join([
                        f", pattern={pat!r}" if pat else "",
                        alias,
                    ])
                    lines.append(f"    {attr}: {ann} = Field({opts[2:]})")
                else:
                    lines.append(f"    {attr}: {ann}")
            else:
                if isinstance(dflt, (list, dict)):
                    lines.append(f"    {attr}: {ann} = Field(default_factory=lambda: {dflt!r}"
                                 + (f", pattern={pat!r}" if pat else "") + alias + ")")
                elif has_default:
                    lines.append(f"    {attr}: {ann} = Field(default={dflt!r}"
                                 + (f", pattern={pat!r}" if pat else "") + alias + ")")
                elif pat or alias:
                    opts = "".join([
                        f", pattern={pat!r}" if pat else "",
                        alias,
                    ])
                    lines.append(f"    {attr}: {ann} | None = Field(default=None{opts})")
                else:
                    lines.append(f"    {attr}: {ann} | None = None")
        self.py_chunks.append("\n".join(lines))

    def emit_alias_ts(self, name: str, sch: dict):
        if sch.get("enum"):
            union = " | ".join(json.dumps(e) for e in sch["enum"])
            self.ts_chunks.append(f"export type {name} = {union};")
        elif sch.get("type") == "string" and sch.get("pattern"):
            self.ts_chunks.append(f"export type {name} = string; // pattern: {sch['pattern']}")
        elif sch.get("type") == "string":
            self.ts_chunks.append(f"export type {name} = string;")
        elif sch.get("type") in ("integer", "number"):
            self.ts_chunks.append(f"export type {name} = number;")
        elif sch.get("type") == "boolean":
            self.ts_chunks.append(f"export type {name} = boolean;")
        else:
            self.ts_chunks.append(f"export type {name} = unknown;")

    def emit_alias_py(self, name: str, sch: dict):
        if sch.get("enum"):
            lit = f"Literal[{', '.join(repr(e) for e in sch['enum'])}]"
            self.py_chunks.append(f"{name} = {lit}")
        elif sch.get("type") == "string" and sch.get("pattern"):
            self.py_chunks.append(f"{name} = Annotated[str, Field(pattern={sch['pattern']!r})]")
        elif sch.get("type") == "string":
            self.py_chunks.append(f"{name}: TypeAlias = str")
        elif sch.get("type") in ("integer", "number"):
            self.py_chunks.append(f"{name}: TypeAlias = {'int' if sch.get('type') == 'integer' else 'float'}")
        elif sch.get("type") == "boolean":
            self.py_chunks.append(f"{name}: TypeAlias = bool")
        else:
            self.py_chunks.append(f"{name}: TypeAlias = Any")

    @staticmethod
    def _is_model(sch: dict) -> bool:
        return sch.get("type") == "object" or "properties" in sch

    def build(self) -> tuple[str, str]:
        ordered = list(self.defs.items())
        # Scalar aliases first (models reference them).
        for name, sch in ordered:
            if not self._is_model(sch):
                self.emit_alias_py(model_name(name), sch)
                self.emit_alias_ts(model_name(name), sch)
        # First pass registers inline models (type mapping), second pass emits.
        for name, sch in ordered:
            if self._is_model(sch):
                self.py_of(sch, name)
                self.ts_of(sch, name)
        for name, sch in ordered:
            if self._is_model(sch):
                self.emit_model_py(model_name(name), sch)
                self.emit_model_ts(model_name(name), sch)
        # Inline models discovered during mapping (stable order).
        for name, sch in list(self.extra_models.items()):
            if name not in [model_name(n) for n, _ in ordered]:
                self.emit_model_py(pascal(name), sch)
                self.emit_model_ts(pascal(name), sch)
        # Root model from top-level properties.
        root_props = self.schema.get("properties", {})
        root_req = set(self.schema.get("required", []))
        root_sch = {"properties": root_props}
        self.emit_model_py("AppSpec", {**root_sch, "required": sorted(root_req)})
        self.emit_model_ts("AppSpec", root_sch | {"required": sorted(root_req)})

        ts = f"// {HEADER}\n\n" + "\n\n".join(self.ts_chunks) + "\n"
        py = (f'"""{HEADER}"""\nfrom __future__ import annotations\n\n'
              f"from typing import Annotated, Any, Literal, TypeAlias\n\n"
              f"from pydantic import BaseModel, Field\n\n\n"
              + "\n\n\n".join(self.py_chunks)
              + "\n\n\n__all__ = [\n"
              + "".join(f'    "{model_name(n)}",\n' for n, s in ordered
                        if self._is_model(s))
              + "".join(f'    "{model_name(n)}",\n' for n, s in ordered
                        if not self._is_model(s))
              + "".join(f'    "{pascal(n)}",\n' for n in self.extra_models
                        if pascal(n) not in [model_name(x) for x, _ in ordered])
              + '    "AppSpec",\n]\n')
        return ts, py


def main() -> int:
    check = "--check" in sys.argv
    schema = json.loads(SCHEMA.read_text())
    ts, py = Gen(schema).build()
    if check:
        ok = True
        for path, fresh in ((TS_OUT, ts), (PY_OUT, py)):
            old = path.read_text() if path.exists() else ""
            if old != fresh:
                ok = False
                print(f"DRIFT: {path.relative_to(ROOT)} differs from schema")
                for line in difflib.unified_diff(
                        old.splitlines(), fresh.splitlines(),
                        str(path.relative_to(ROOT)), "regenerated", lineterm=""):
                    print(line)
        if not ok:
            print("run: python scripts/gen_spec_types.py")
            return 1
        print("spec types in sync")
        return 0
    TS_OUT.write_text(ts)
    PY_OUT.parent.mkdir(parents=True, exist_ok=True)
    PY_OUT.write_text(py)
    print(f"wrote {TS_OUT.relative_to(ROOT)} + {PY_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
