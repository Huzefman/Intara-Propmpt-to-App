"""Canonical component catalog loader.

One JSON file under `server/data/component_catalog.json` is the contract shared
by the S3 prompt, the G1 linter, and the runtime registry drift test. Keeping
the metadata here prevents the prompt, the gate, and the renderer from drifting
apart as blocks are added.
"""
from __future__ import annotations

import json
import os
from typing import Any

_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "component_catalog.json",
)

with open(_PATH, "r", encoding="utf-8") as _fh:
    CATALOG: dict[str, Any] = json.load(_fh)

_BY_TYPE: dict[str, dict] = {b["type"]: b for b in CATALOG["blocks"]}

# Page composition recipes to prevent all apps from becoming simple tables
PAGE_RECIPES: dict[str, str] = CATALOG.get("recipes", {
    "Dashboard": "metric.stat + chart.bar + activity.timeline",
    "Collection": "filter.bar + data.table / data.kanban / calendar.month",
    "Record": "record.detail + record.related_list + lifecycle.pipeline",
    "Form": "form.record",
    "Files": "file.list",
    "Landing": "content.hero",
})

# Compatibility shape used by G1, S3's gate, and existing tests.
BLOCKS: dict[str, dict] = {
    block_type: {
        "stability": info.get("stability", "stable"),
        "required_props": list(info.get("required_props") or info.get("required") or []),
        "optional_props": list(info.get("optional_props") or info.get("optional") or []),
    }
    for block_type, info in _BY_TYPE.items()
}


def prompt_recipes() -> str:
    """Format page recipes for the S3 prompt."""
    lines = ["Page recipes (compose pages with these block patterns so apps don't just become tables):"]
    for page_name, pattern in PAGE_RECIPES.items():
        lines.append(f"- {page_name} → {pattern}")
    return "\n".join(lines)


def prompt_catalog() -> str:
    """Compact catalog for the S3 system prompt.

    One line per block keeps the prompt bounded while still telling the model
    which props are required, which are optional, and when the block fits.
    Includes page composition recipes.
    """
    lines: list[str] = []
    for block_type, info in _BY_TYPE.items():
        required = ", ".join(info.get("required_props") or info.get("required") or []) or "none"
        optional = ", ".join(info.get("optional_props") or info.get("optional") or []) or "none"
        fit = info.get("fits") or ""
        stability = info.get("stability", "stable")
        suffix = " [experimental]" if stability != "stable" else ""
        lines.append(
            f"- {block_type}{suffix}: required={required}; optional={optional}; {fit}"
        )
    lines.append("")
    lines.append(prompt_recipes())
    return "\n".join(lines)
