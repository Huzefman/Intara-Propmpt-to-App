"""
Gates — blocking build validation (fail-closed, never ships red).

FE: tsc --noEmit + vite build on the candidate tree (scaffold + fragments).
    Toolchain lives in a persistent workspace outside the repo
    (<tmp>/intara-gates/nodeproj); deps install once, reuse after.
BE: py_compile + import server.main:app from backend/ cwd + TestClient
    CRUD matrix from the contract (seed → toggle → delete, FK round-trip).
Contract: route matrix, {id} canonical, dep closure, placeholder scans.

Degraded (toolchain missing) is REPORTED, never a silent pass.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GATE_TMP = Path(tempfile.gettempdir()) / "intara-gates"
NODE_PROJ = GATE_TMP / "nodeproj"
# Pinned to the scaffold's closed dep set (tailwind v4 moved the postcss plugin — v3 only)
NODE_PKGS = {"react": "^18.3.1", "react-dom": "^18.3.1", "react-router-dom": "^6.23.0",
             "@supabase/supabase-js": "^2.45.0", "dexie": "^4.0.8",
             "typescript": "^5.5.3", "vite": "^5.4.2", "@vitejs/plugin-react": "^4.3.1",
             "@types/react": "^18.3.3", "@types/react-dom": "^18.3.0",
             "tailwindcss": "^3.4.0", "postcss": "^8.4.0", "autoprefixer": "^10.4.0"}

TSC_TIMEOUT = 240
VITE_TIMEOUT = 240
NPM_TIMEOUT = 600
BE_TIMEOUT = 120


def _run(cmd: list[str], cwd: str | Path, timeout: int) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out.strip()[-4000:]
    except FileNotFoundError as e:
        return 127, f"toolchain missing: {e}"
    except subprocess.TimeoutExpired:
        return 124, f"gate timed out after {timeout}s: {' '.join(cmd)}"


def ensure_node_project() -> tuple[str | None, list[str]]:
    """Install-once workspace for FE gates. Returns (path, errors)."""
    try:
        NODE_PROJ.mkdir(parents=True, exist_ok=True)
        want = json.dumps({"name": "intara-gates", "private": True, "type": "module",
                           "dependencies": dict(NODE_PKGS)}, indent=2)
        pkg = NODE_PROJ / "package.json"
        marker = NODE_PROJ / ".installed"
        # reinstall whenever the pinned set changes (marker stores the exact json)
        if not pkg.exists() or not marker.exists() or marker.read_text() != want:
            pkg.write_text(want)
            try:
                marker.unlink()
            except Exception:
                pass
            code, out = _run(["npm", "install", "--no-audit", "--no-fund"], NODE_PROJ, NPM_TIMEOUT)
            if code != 0:
                return None, [f"DEGRADED: npm install failed, FE gates cannot run:\n{out[:1000]}"]
            marker.write_text(want)
        return str(NODE_PROJ), []
    except Exception as e:
        return None, [f"DEGRADED: node workspace setup failed: {e}"]


def _write_tree(root: Path, files: dict[str, str]):
    for path, content in files.items():
        dest = root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content if isinstance(content, str) else "")


def run_fe_gates(fe_files: list[dict], scaffold: dict[str, str]) -> list[str]:
    """tsc --noEmit + vite build. Returns error list (empty = green)."""
    proj, errs = ensure_node_project()
    if proj is None:
        return errs
    tree: dict[str, str] = dict(scaffold)
    for f in fe_files:
        if isinstance(f, dict) and f.get("path"):
            tree[f["path"]] = f.get("content", "")
    # never let harness files mask the candidate tree
    for drop in ("node_modules", ".installed", "package.json", "package-lock.json", "dist"):
        tree.pop(drop, None)
    try:
        _write_tree(Path(proj), tree)
        errors: list[str] = []
        code, out = _run(["npx", "tsc", "--noEmit", "-p", "."], proj, TSC_TIMEOUT)
        if code != 0:
            errors.append("tsc --noEmit failed:\n" + out[:2000])
        else:
            code2, out2 = _run(["npx", "vite", "build"], proj, VITE_TIMEOUT)
            if code2 != 0:
                errors.append("vite build failed:\n" + out2[:2000])
        return errors
    except Exception as e:
        return [f"DEGRADED: FE gate harness failed: {e}"]


BE_RUNNER = r'''
import json, os, sys
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
sys.path.insert(0, os.getcwd())
contract = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "contract.json")))
errors = []
try:
    from server.main import app
    print("import ok")
except Exception as e:
    print(json.dumps({"errors": [f"import server.main:app failed: {e}"]})); sys.exit(0)
try:
    from fastapi.testclient import TestClient
    c = TestClient(app)
    r = c.get("/health")
    if r.status_code != 200:
        errors.append(f"/health -> {r.status_code}")
    tables = contract["tables"]
    depth = {}
    def dep(t):
        if t["name"] in depth: return depth[t["name"]]
        d = 0
        for fk in t.get("fks", []):
            d = max(d, 1 + dep({"name": fk["ref_table"], "fks": []}))
        depth[t["name"]] = d
        return d
    order = sorted(tables, key=dep)
    ids = {}
    def sample(t, fkvals):
        body = {}
        for f in t.get("fields", []):
            if f["name"] == "id": continue
            if f["name"] in fkvals: body[f["name"]] = fkvals[f["name"]]; continue
            ft = f.get("type", "text")
            body[f["name"]] = {"text": "smoke", "integer": 7, "boolean": True,
                               "timestamp": "2026-01-01T00:00:00", "uuid": "u-smoke"}.get(ft, "smoke")
        return body
    for t in order:
        name = t["name"]
        fkvals = {fk["col"]: ids[fk["ref_table"]] for fk in t.get("fks", []) if fk["ref_table"] in ids}
        r = c.post(f"/api/{name}", json=sample(t, fkvals))
        if r.status_code != 200:
            errors.append(f"POST /api/{name} -> {r.status_code} {str(r.text)[:200]}"); continue
        rid = r.json().get("id")
        if not rid:
            errors.append(f"POST /api/{name}: no id returned"); continue
        ids[name] = rid
        if c.get(f"/api/{name}").status_code != 200: errors.append(f"GET /api/{name} failed")
        if c.get(f"/api/{name}/{rid}").status_code != 200: errors.append(f"GET /api/{name}/{rid} failed")
        first = next((f for f in t.get("fields", []) if f["name"] != "id"), {"name": "title", "type": "text"})
        alt = {"text": "smoke2", "integer": 8, "boolean": False,
               "timestamp": "2026-02-02T00:00:00", "uuid": "u-smoke2"}.get(first.get("type", "text"), "smoke2")
        r2 = c.patch(f"/api/{name}/{rid}", json={first["name"]: alt})
        if r2.status_code != 200 or r2.json().get(first["name"]) != alt:
            errors.append(f"PATCH /api/{name}/{rid} failed: {r2.status_code} {str(r2.text)[:160]}")
        if c.put(f"/api/{name}/{rid}", json={**sample(t, fkvals), first["name"]: alt}).status_code != 200:
            errors.append(f"PUT /api/{name}/{rid} failed")
        if c.delete(f"/api/{name}/{rid}").status_code != 200: errors.append(f"DELETE /api/{name}/{rid} failed")
        if c.get(f"/api/{name}/{rid}").status_code != 404: errors.append(f"GET deleted /api/{name}/{rid} != 404")
    print(json.dumps({"errors": errors[:12]}))
except Exception as e:
    import traceback; print(json.dumps({"errors": [f"CRUD matrix crashed: {e}", traceback.format_exc()[-800:]]}))
'''


def run_be_gates(be_files: list[dict], contract: dict) -> list[str]:
    """py_compile + import-from-cwd + TestClient CRUD matrix. Empty = green."""
    tmp = Path(tempfile.mkdtemp(prefix="intara-be-"))
    try:
        tree = {f["path"]: f.get("content", "") for f in be_files
                if isinstance(f, dict) and f.get("path")}
        _write_tree(tmp / "backend", tree)
        (tmp / "contract.json").write_text(json.dumps(contract))
        (tmp / "run.py").write_text(BE_RUNNER)
        errors: list[str] = []
        code, out = _run([sys.executable, "-m", "compileall", "-q", "backend"], tmp, BE_TIMEOUT)
        if code != 0:
            return [f"py_compile failed:\n{out[:1500]}"]
        code, out = _run([sys.executable, "run.py"], tmp, BE_TIMEOUT)
        for line in out.splitlines():
            line = line.strip()
            if line.startswith('{"errors"'):
                try:
                    errors.extend(json.loads(line).get("errors", []))
                except Exception:
                    errors.append(line[:500])
        if code not in (0,) and not errors:
            errors.append(f"BE runner exited {code}:\n{out[:1500]}")
        return errors
    except Exception as e:
        return [f"DEGRADED: BE gate harness failed: {e}"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _paths_in_errors(errors: list[str]) -> list[str]:
    import re
    found: list[str] = []
    for e in errors:
        for m in re.findall(r"(?:src/|server/)[\w\-./]+\.(?:tsx?|py|json|js|css)", e):
            if m not in found:
                found.append(m)
    return found[:3]


def repair_gate_files(contract: dict, errors: list[str],
                      fe_tree: list[dict], be_tree: list[dict]) -> dict:
    """One patch attempt per failing file (reuses iterate machinery), mutating trees.
    Returns {"fe": bool, "be": bool} sides to re-run. Best-effort: never raises."""
    repaired = {"fe": False, "be": False}
    try:
        from services.iterate import _edit_file
    except Exception as e:
        print(f"gate repair unavailable: {e}")
        return repaired
    by_path = {f.get("path"): f for f in fe_tree + be_tree if isinstance(f, dict)}
    for path in _paths_in_errors(errors):
        node = by_path.get(path)
        if not node or not isinstance(node.get("content"), str):
            continue
        related = [e for e in errors if path in e][:4]
        instruction = ("Fix these build-gate errors with the smallest possible change, "
                       "preserving all behavior:\n" + "\n".join(related))[:800]
        try:
            new, _ = _edit_file(path, node["content"], instruction, contract.get("appName", "app"))
            if new and new != node["content"]:
                node["content"] = new
                repaired["fe" if path.startswith("src/") else "be"] = True
        except Exception as e:
            print(f"gate repair failed for {path}: {e}")
    return repaired


def run_contract_checks(contract: dict, fe_files: list[dict], be_files: list[dict],
                        openapi: dict, package_json: str, postcss: str | None) -> list[str]:
    from services.contract import (check_backend_routes, check_frontend_client,
                                   check_openapi, check_deps, check_placeholders,
                                   check_no_template_tokens)
    errs: list[str] = []
    errs += check_placeholders(fe_files + be_files)
    errs += check_no_template_tokens(fe_files + be_files)
    errs += check_backend_routes(be_files, contract)
    errs += check_frontend_client(fe_files, contract)
    errs += check_openapi(openapi, contract)
    errs += check_deps(package_json, postcss)
    return errs
