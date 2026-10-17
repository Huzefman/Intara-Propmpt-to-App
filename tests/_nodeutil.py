"""
Node invocation helper for pytest gates that run TypeScript via node --test.

Type-stripped .ts runs natively from Node 22.18+ (and 23.6+); 22.6–22.17
support it behind --experimental-strip-types. The flag is added
automatically when the local node is older, so the suite is green on any
modern 22.x. CI pins Node 24.
"""
import re
import shutil
import subprocess

_STRIP_DEFAULT = (22, 18)


def _version(node: str) -> tuple:
    try:
        r = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10)
        m = re.match(r"v(\d+)\.(\d+)\.", r.stdout.strip())
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    except Exception:
        return (0, 0)


def node_cmd(*args: str) -> list:
    """node executable (+ type-strip flag when the node is old) + args."""
    node = shutil.which("node")
    cmd = [node] if node else []
    if node and _version(node) < _STRIP_DEFAULT:
        cmd.append("--experimental-strip-types")
    cmd.extend(args)
    return cmd
