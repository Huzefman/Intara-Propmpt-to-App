"""
G0 — schema gate (Phase 4, P4.1/P4.2).

Validates a spec dict against the generated Pydantic models (which are
generated from packages/spec/app-spec.schema.json — never hand-edited).
Returns a list of human-readable error strings; empty means G0 passes.
Semantic checks live in g1_lint.py.
"""
from __future__ import annotations


def validate(spec: dict) -> list[str]:
    from engine.spec_models import AppSpec
    from pydantic import ValidationError
    try:
        AppSpec.model_validate(spec)
        return []
    except ValidationError as e:
        out = []
        for err in e.errors():
            loc = ".".join(str(p) for p in err.get("loc", ()))
            out.append(f"{loc or '<root>'}: {err.get('msg')} [{err.get('type')}]")
        return out
    except Exception as e:
        return [f"<root>: {e}"]
