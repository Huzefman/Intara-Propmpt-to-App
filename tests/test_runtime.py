"""
Runtime package CI gate — Phase 6. Runs the TypeScript suite
(packages/runtime: engine, adapters, shell, blocks, G3/G4) via node --test
and asserts green. Skipped when node is absent.
Run: pytest tests/test_runtime.py -v
"""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME = os.path.join(ROOT, "packages", "runtime")


def test_node_runtime_suite_green():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    from tests._nodeutil import node_cmd
    r = subprocess.run(
        node_cmd("--test",
        "../spec/formula/formula.test.ts",
        "engine/**/*.test.ts", "adapters/**/*.test.ts",
        "shell/*.test.ts", "blocks/*.test.ts", "testing/**/*.test.ts",
        "automation/**/*.test.ts", "storage/**/*.test.ts",
        "auth/**/*.test.ts", "editing/**/*.test.ts"),
        cwd=RUNTIME, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"runtime suite failed:\n{r.stdout[-3000:]}\n{r.stderr[-500:]}"
    assert "fail 0" in r.stdout, r.stdout[-500:]


def test_runtime_typecheck_clean():
    tsc = os.path.join(ROOT, "react-prompt-app", "node_modules", ".bin", "tsc")
    if not os.path.exists(tsc):
        pytest.skip("repo tsc not installed")
    r = subprocess.run([tsc, "--noEmit", "-p", "tsconfig.json"],
                       cwd=RUNTIME, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"runtime tsc failed:\n{r.stdout[-3000:]}"
