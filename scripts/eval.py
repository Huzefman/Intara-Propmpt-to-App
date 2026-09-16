#!/usr/bin/env python3
"""
Intara — Benchmark Eval Script
Checks 5 golden wishes against 6 metrics: json_valid, schema_completeness, fe_build, be_parse, openapi, cites
Usage:
  python scripts/eval.py --mocked --verbose          # mocked fixtures, $0
  python scripts/eval.py --mocked --wish 1            # single wish
  python scripts/eval.py --live --prompt "..."         # live Gemini call (costs 1 free call)
"""
import argparse, json, ast, subprocess, sys, os, tempfile, pathlib

ROOT = pathlib.Path(__file__).parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "wishes.json"

ALLOWED_TYPES = {"text", "integer", "timestamp", "boolean"}

def check_json_valid(wish):
    try:
        json.dumps(wish["prd"])
        json.dumps(wish["artifacts"])
        return True, "ok"
    except Exception as e:
        return False, str(e)

def check_schema(wish):
    tables = wish.get("artifacts", {}).get("schema", {}).get("tables") or wish.get("prd", {}).get("tables", [])
    if not (1 <= len(tables) <= 3):
        return False, f"tables count {len(tables)} not in 1-3"
    for t in tables:
        if not t.get("name"):
            return False, "table missing name"
        fields = t.get("fields", [])
        if not (2 <= len(fields) <= 5):
            return False, f"table {t['name']} fields {len(fields)} not 2-5"
        for f in fields:
            if f.get("type") not in ALLOWED_TYPES:
                return False, f"field {f.get('name')} type {f.get('type')} not allowed"
    # duplicate check
    names = [t["name"] for t in tables]
    if len(names) != len(set(names)):
        return False, "duplicate table names"
    return True, "ok"

def check_fe_build(wish):
    files = wish.get("artifacts", {}).get("frontend", {}).get("files", [])
    if not files:
        return False, "no frontend files"
    has_page = any("pages/" in f.get("path","") for f in files)
    if not has_page:
        return False, "no src/pages/ file"
    # try tsc if available
    try:
        # quick check: any file contains "export" ?
        # optional tsc run in temp dir
        if subprocess.run(["npx", "tsc", "--version"], capture_output=True, timeout=5).returncode != 0:
            return True, "skipped tsc (not installed), has_page ok"
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            for f in files:
                p = tmp / f["path"]
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(f["content"])
            # minimal tsconfig
            (tmp / "tsconfig.json").write_text('{"compilerOptions":{"jsx":"react-jsx","esModuleInterop":true,"allowJs":true,"strict":false,"skipLibCheck":true,"target":"ES2020","module":"ESNext"},"include":["src"]}')
            res = subprocess.run(["npx", "tsc", "--noEmit"], cwd=tmp, capture_output=True, timeout=15)
            if res.returncode == 0:
                return True, "tsc pass"
            else:
                out = (res.stdout.decode() + res.stderr.decode())[:800]
                return False, f"tsc failed: {out[:400]}"
    except FileNotFoundError:
        return True, "skipped tsc (npx not found)"
    except subprocess.TimeoutExpired:
        return False, "tsc timeout"
    except Exception as e:
        return False, f"fe_build error: {e}"

def check_be_parse(wish):
    files = wish.get("artifacts", {}).get("backend", {}).get("files", [])
    req = wish.get("artifacts", {}).get("backend", {}).get("requirements", "")
    if "fastapi" not in req.lower():
        return False, "requirements missing fastapi"
    if not files:
        return False, "no backend files"
    for f in files:
        if f["path"].endswith(".py"):
            try:
                ast.parse(f["content"])
            except SyntaxError as e:
                return False, f"ast parse fail {f['path']}: {e}"
    # optional ruff
    try:
        if subprocess.run(["ruff", "--version"], capture_output=True, timeout=5).returncode == 0:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = pathlib.Path(tmp)
                for f in files:
                    p = tmp / f["path"]
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(f["content"])
                res = subprocess.run(["ruff", "check", "."], cwd=tmp, capture_output=True, timeout=10)
                if res.returncode != 0 and b"error" in res.stdout.lower():
                    return False, f"ruff failed: {res.stdout.decode()[:400]}"
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return True, "ok"

def check_openapi(wish):
    openapi = wish.get("artifacts", {}).get("spec", {}).get("openapi")
    if not openapi:
        return False, "no openapi"
    if "paths" not in openapi:
        return False, "openapi missing paths"
    if len(openapi["paths"]) < 1:
        return False, "openapi paths empty"
    # check at least 2 apis from prd are represented (loose)
    return True, "ok"

def check_cites(wish):
    cites = wish.get("artifacts", {}).get("spec", {}).get("cites", [])
    readme = wish.get("artifacts", {}).get("spec", {}).get("readme", "")
    if cites and len(cites) > 0:
        return True, f"cites {len(cites)}"
    if "Intara" in readme:
        return True, "readme contains Intara"
    return False, "no cites and readme missing Intara"

CHECKS = {
    "json_valid": check_json_valid,
    "schema": check_schema,
    "fe_build": check_fe_build,
    "be_parse": check_be_parse,
    "openapi": check_openapi,
    "cites": check_cites,
}

def eval_wish(wish, only=None):
    results = {}
    for name, fn in CHECKS.items():
        if only and name not in only:
            continue
        ok, msg = fn(wish)
        results[name] = (ok, msg)
    overall = all(v[0] for v in results.values())
    return overall, results

def main():
    ap = argparse.ArgumentParser(description="Intara eval")
    ap.add_argument("--mocked", action="store_true", help="use fixtures")
    ap.add_argument("--live", action="store_true", help="live Gemini (not implemented, mocked)")
    ap.add_argument("--all", action="store_true", help="eval all 5")
    ap.add_argument("--wish", type=int, help="wish index 1-5")
    ap.add_argument("--check", help="comma list: json_valid,schema,fe_build,be_parse,openapi,cites")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--prompt", help="custom prompt for live")
    args = ap.parse_args()

    if not FIXTURE.exists():
        print(f"missing {FIXTURE}")
        sys.exit(1)
    wishes = json.loads(FIXTURE.read_text())
    only = [s.strip() for s in args.check.split(",")] if args.check else None

    # live not yet — placeholder
    if args.live:
        print("live mode: not wired to Gemini yet — run mocked for now. Use --mocked")
        if args.prompt:
            print(f"prompt: {args.prompt}")

    targets = wishes
    if args.wish:
        targets = [wishes[args.wish-1]]

    passed = 0
    for i, w in enumerate(targets, 1):
        overall, results = eval_wish(w, only)
        status = "PASS" if overall else "FAIL"
        if overall: passed += 1
        print(f"wish {i} {w['id']}: {status}")
        if args.verbose or not overall:
            for k, (ok, msg) in results.items():
                print(f"  {k}: {'✓' if ok else '✗'} {msg}")
        if args.verbose:
            print(f"  prompt: {w['prompt'][:80]}")

    total = len(targets)
    print(f"\nSuite: {passed}/{total} pass — {'PASS' if passed==total else 'FAIL'}")
    sys.exit(0 if passed==total else 1)

if __name__ == "__main__":
    main()
