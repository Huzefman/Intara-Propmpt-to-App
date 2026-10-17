# Fix Plan — 8 Issues

## Critical Fixes (3)

### Fix #1: Wire `schema_v2.py` into `schema_gen.py`
**File:** [`server/services/generators/schema_gen.py`](file:///Users/huzefa/prompt-to-app/server/services/generators/schema_gen.py)

Add an LLM-first path at the top of `generate_schema()` (before the deterministic code). Same pattern as frontend/backend: try LLM → validate → fallback to existing template.

```python
def generate_schema(prd: dict):
    # LLM-first if entities present
    if prd.get("entities"):
        try:
            from prompts.schema_v2 import build_schema_prompt
            from services.llm import call_llm
            raw = call_llm(build_schema_prompt(prd), temperature=0.2)
            data = _parse_json(raw)  # need to add _parse_json
            if data.get("tables") and data.get("sql") and data.get("prisma"):
                return data
        except Exception as e:
            print(f"LLM schema gen failed, template fallback: {e}")
    # ... existing deterministic code below (unchanged) ...
```

---

### Fix #2: `del` → `remove` in detail page template
**File:** [`server/services/generators/frontend_gen.py`](file:///Users/huzefa/prompt-to-app/server/services/generators/frontend_gen.py)

Two changes at **line 185** and **line 204**:
- `const del = async ()` → `const remove = async ()`
- `onClick={{del}}` → `onClick={{remove}}`

---

### Fix #3: `UnboundLocalError` in validator `finally` block
**File:** [`server/services/validator.py`](file:///Users/huzefa/prompt-to-app/server/services/validator.py)

Restructure lines 18-38 to avoid the scoping issue. Declare `tmppath = None` before the `try` block, and clean up in `finally` using the stored path.

---

## Medium Fixes (2)

### Fix #5: Assembler file deduplication
**File:** [`server/services/assembler.py`](file:///Users/huzefa/prompt-to-app/server/services/assembler.py)

Add dedup at lines 95-103 after merging scaffold + mock into frontend/backend files:
```python
# Deduplicate by path (last wins)
seen = {}
for f in fe_files:
    seen[f["path"]] = f
fe_files = list(seen.values())
```
Same for `be_files`.

---

### Fix #8: Mock fallback missing `entities` field
**File:** [`server/services/planner_v2.py`](file:///Users/huzefa/prompt-to-app/server/services/planner_v2.py)

Add `entities` derivation to the return dict in `mock_build_plan()` at **line 61**:
```python
"entities": [{"name": t["name"], "fields": t["fields"], "relationships": [], "businessRules": []} for t in tables],
```
This ensures the LLM backend path triggers even when using the mock planner.

---

## Minor Fixes / Refactoring (3)

### Fix #6 + #7: Deduplicate `_parse_json` and `_is_quota`

**New file:** [`server/utils/json_parse.py`](file:///Users/huzefa/prompt-to-app/server/utils/json_parse.py)

Extract the shared `parse_json()` and `is_quota_error()` into one utility module. Update imports in `analyzer.py`, `planner_v2.py`, `frontend_gen.py`, `backend_gen.py`.

---

## Summary

| # | Issue | File | Lines Changed | Risk |
|---|-------|------|---------------|------|
| 1 | Schema LLM path | `schema_gen.py` | ~15 added | Low |
| 2 | `del` keyword | `frontend_gen.py` | 2 lines | Zero |
| 3 | Validator scoping | `validator.py` | ~8 lines | Low |
| 5 | Assembler dedup | `assembler.py` | ~6 lines | Low |
| 8 | Mock entities | `planner_v2.py` | 1 line | Zero |
| 6+7 | Extract utils | New `utils/` + 4 imports | ~30 lines | Low |

Total: ~60 lines changed across 7 files. No breaking changes, no new dependencies.
