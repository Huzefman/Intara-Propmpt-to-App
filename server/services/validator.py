"""
Validator — TSX + Python + cross-check.

validate_tsx is deliberately esbuild-FREE: per-file `esbuild --bundle` cannot
resolve bare imports (react, react-router-dom) outside a real project dir, so in
server environments it red-flags EVERY file with valid imports — which silently
forces all LLM pages into template fallback and then fails blocking gates on the
same phantom errors. Real type checking lives in the heavy gates
(gates.run_fe_gates: tsc --noEmit + vite build on the full tree with node_modules).
"""
import ast
import re


def validate_tsx(content: str, path: str = "") -> list[str]:
    errors = []
    # Default-export rule applies ONLY to .tsx pages (routers import them as default).
    # Shared components legitimately use named exports; the pages barrel re-exports.
    if "/pages/" in (path or "") and (path or "").endswith(".tsx") and "export default" not in content:
        errors.append("Missing default export (pages must default-export for routing)")
    if content.count("{") != content.count("}"):
        errors.append(f"Unbalanced braces: {content.count('{')} open vs {content.count('}')} close")
    # esbuild-independent JSX check: ={{...}} whose inner content cannot be an object
    # literal (starts with `!`, or is a bare identifier/member like `item`/`item.id`).
    # Catches the brace-balanced-but-invalid `checked={{!!form.x}}` / `value={{item}}`
    # double-wrap — the exact blind spot when esbuild is unavailable.
    for m in re.finditer(r"=\{\{(.*?)\}\}", content, re.S):
        inner = m.group(1).strip()
        if re.match(r"^[!]", inner) or re.match(r"^[\w\$][\w\$.]*$", inner):
            errors.append(f"Invalid double-brace JSX attribute: unwrap to single braces near '={{{{{inner[:60]}}}}}'")
            break
    return errors


def validate_python(content: str) -> list[str]:
    errors = []
    try:
        ast.parse(content)
    except SyntaxError as e:
        errors.append(f"Line {e.lineno}: {e.msg}")
    return errors


def validate_imports_consistency(frontend_files: list[dict], backend_files: list[dict]) -> list[str]:
    errors = []
    fe_paths = set()
    for f in frontend_files:
        for m in re.findall(r"fetch\(['\"`](/api/\w+)", f.get("content", "")):
            fe_paths.add(m)
    be_paths = set()
    for f in backend_files:
        for m in re.findall(r"@app\.\w+\(['\"](/api/\w+)", f.get("content", "")):
            be_paths.add(m)
    for p in fe_paths:
        base = p.split("/")[2] if len(p.split("/")) > 2 else p
        if not any(base in bp for bp in be_paths):
            errors.append(f"Frontend fetches {p} but no matching backend route")
    return errors
