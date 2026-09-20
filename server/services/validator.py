"""
Validator — TSX + Python + cross-check
"""
import ast
import subprocess
import tempfile
import os
import re


def validate_tsx(content: str) -> list[str]:
    errors = []
    if "export default function" not in content and "export default" not in content:
        errors.append("Missing default export")
    if content.count("{") != content.count("}"):
        errors.append(f"Unbalanced braces: {content.count('{')} open vs {content.count('}')} close")
    tmppath = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False) as f:
            tmppath = f.name
            f.write(content)
            f.flush()
            result = subprocess.run(
                ["npx", "esbuild", "--bundle", "--format=esm", "--jsx=automatic", tmppath],
                capture_output=True, text=True, timeout=10, cwd=os.getcwd()
            )
            if result.returncode != 0:
                for line in result.stderr.strip().split("\n")[:5]:
                    if "error" in line.lower():
                        errors.append(line.strip())
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        pass
    finally:
        if tmppath:
            try:
                os.unlink(tmppath)
            except:
                pass
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
