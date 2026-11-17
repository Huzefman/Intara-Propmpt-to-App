#!/usr/bin/env python3
"""Sync the canonical component catalog into the frontend/docs copy.

The backend deploy root is `server/`, so the canonical JSON must live inside
it. The runtime and docs read a mirrored copy under `packages/spec/`; this
script rewrites that mirror and the test suite fails if the two drift.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "server" / "data" / "component_catalog.json"
DST = ROOT / "packages" / "spec" / "component-catalog.json"


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    DST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"synced {SRC.relative_to(ROOT)} -> {DST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
