"""
Iterate — chat-driven code rewrites (diff-first, step + wiring, snapshots).

Preview costs LLM calls (router enforces the shared 20/day chat cap).
Apply/revert are pure DB ops (free). Nothing lands in wishes.artifacts
until the user Accepts; every apply keeps a snapshot for one-click revert.
Fail-open: wish_iterations table missing → pending previews live in memory
and applies go through without snapshots.
"""
import contextvars
import json
import re

MAX_FILES = 3  # cap LLM edit calls per preview
MAX_OLD_CHARS = 12000  # cap tokens per edit call

# in-memory fallback when wish_iterations table is missing
MEM_ITERS = {}

STARDUST = (
    "Out of stardust for now — the shared free LLM pool is empty. "
    "Your wish, plan, and code are safe; try the change again after the daily reset."
)


def _is_quota_msg(msg: str) -> bool:
    m = (msg or "").lower()
    return "429" in m or "quota" in m or "rate" in m or "limit" in m


def _graph(wish: dict) -> list[dict]:
    return (wish.get("prd") or {}).get("buildGraph", []) or []


def resolve_step(wish: dict, step_id: str | None, instruction: str) -> dict | None:
    """Explicit stepId wins; else keyword match on page/table names; else 1 LLM classify call."""
    graph = _graph(wish)
    if step_id:
        for n in graph:
            if n.get("id") == step_id:
                return n
        return None
    q = (instruction or "").lower()
    toks = set(re.findall(r"[a-z]{3,}", q))
    if toks:
        scored = []
        for n in graph:
            if n.get("kind") not in ("frontend_page", "backend_table"):
                continue
            ref = str(n.get("ref") or "").lower()
            nid = str(n.get("id") or "").lower()
            hit = sum(1 for t in toks if t in ref or t in nid)
            if hit:
                scored.append((hit, n))
        if scored:
            scored.sort(key=lambda x: -x[0])
            return scored[0][1]
    # LLM classify fallback (1 call) — only when keywords miss
    try:
        from services.llm import call_llm
        lines = [f"{n.get('id')} ({n.get('kind')}: {n.get('ref') or '-'})" for n in graph]
        prompt = (
            "Pick which build step a code-change request targets. "
            "Return ONLY the step id, no prose.\nSteps:\n" + "\n".join(lines)
            + f"\nRequest: {instruction[:500]}"
        )
        guess = call_llm(prompt, temperature=0.1).strip().split()[0].strip("\"'`.,")
        for n in graph:
            if n.get("id") == guess:
                return n
    except Exception as e:
        if getattr(e, "byok_error", False):
            raise
        if _is_quota_msg(str(e)):
            raise
        print(f"iterate classify failed: {e}")
    return None


def _artifacts_index(wish: dict) -> dict[str, dict]:
    """path -> {content, area}. area in frontend/backend/preview."""
    idx: dict[str, dict] = {}
    arts = wish.get("artifacts") or {}
    for f in ((arts.get("frontend") or {}).get("files") or []):
        if isinstance(f, dict) and f.get("path"):
            idx[f["path"]] = {"content": f.get("content", ""), "area": "frontend"}
    for f in ((arts.get("backend") or {}).get("files") or []):
        if isinstance(f, dict) and f.get("path"):
            idx.setdefault(f["path"], {"content": f.get("content", ""), "area": "backend"})
    for path, content in ((arts.get("preview") or {}).items()):
        idx.setdefault(path, {"content": content if isinstance(content, str) else "", "area": "preview"})
    return idx


def _step_declared_files(wid: str, step_id: str) -> list[str]:
    try:
        from db.wishes import get_steps
        for row in get_steps(wid):
            if row.get("step_id") == step_id:
                out = row.get("output") or {}
                files = out.get("files") or []
                return [str(p) for p in files if isinstance(p, str)]
    except Exception as e:
        print(f"iterate step files skipped: {e}")
    return []


_SHARED_SHELLS = {"src/api.ts", "src/types.ts"}


def step_target_files(wish: dict, wid: str, node: dict) -> list[dict]:
    """Primary files for a step: paths mentioning ref first, shared shells last. Capped."""
    idx = _artifacts_index(wish)
    ref = str(node.get("ref") or "").lower()
    declared = _step_declared_files(wid, node.get("id", ""))
    cands = [p for p in declared if p in idx]
    if not cands:
        # fallback: any path mentioning the ref
        cands = [p for p in idx if ref and ref in p.lower()]
    primary = [p for p in cands if ref and ref in p.lower()]
    rest = [p for p in cands if p not in primary and p not in _SHARED_SHELLS]
    shells = [p for p in cands if p in _SHARED_SHELLS]
    ordered = primary + rest + shells
    return [{"path": p, **idx[p]} for p in ordered[:MAX_FILES]]


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:\w+)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return _strip_preamble(t.strip())


def _strip_preamble(text: str) -> str:
    """Drop intermittent moderation one-liners the free model prepends/appends (e.g. 'User Safety: safe')."""
    lines = text.split("\n")
    pat = re.compile(r"^\s*user safety\s*:.*$", re.IGNORECASE)
    while lines and (not lines[0].strip() or pat.match(lines[0])):
        lines.pop(0)
    while lines and (not lines[-1].strip() or pat.match(lines[-1])):
        lines.pop()
    return "\n".join(lines)


def _validate(path: str, content: str) -> list[str]:
    try:
        if path.endswith((".tsx", ".ts")):
            from services.validator import validate_tsx
            return validate_tsx(content, path)
        if path.endswith(".py"):
            from services.validator import validate_python
            return validate_python(content)
    except Exception as e:
        print(f"iterate validate skipped for {path}: {e}")
    return []


EDIT_MAX_TOKENS = 2000  # patch blocks are small; caps reasoning-dribble
EDIT_DEADLINE = 90  # wall-clock guard per LLM call (slow-drip responses evade read timeouts)


def _bounded_call(prompt: str, temperature: float, what: str) -> str:
    """call_llm with output cap + wall-clock deadline. Raises RuntimeError (429-prefixed on quota)."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
    from services.llm import call_llm
    # ThreadPoolExecutor does not copy contextvars: carry the request's BYOK
    # identity into the worker thread explicitly, or the call would fall back
    # to the shared pool.
    ctx = contextvars.copy_context()
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(ctx.run, call_llm, prompt, temperature, EDIT_MAX_TOKENS)
        try:
            return _strip_fences(fut.result(timeout=EDIT_DEADLINE))
        except FuturesTimeout:
            raise RuntimeError(
                f"{what} took too long (>{EDIT_DEADLINE}s) — try a narrower instruction targeting fewer lines")
        except RuntimeError as e:
            if getattr(e, "byok_error", False):
                # The account's own key failed. Don't relabel it as the shared
                # pool being out of stardust — the user needs the real reason.
                raise
            if _is_quota_msg(str(e)):
                raise RuntimeError(f"429 {STARDUST}")
            raise RuntimeError(f"{what} failed: {e}")


def _parse_blocks(raw: str) -> list[tuple[str, str]]:
    """Parse SEARCH/REPLACE hunks. Raises on malformed output."""
    blocks = []
    parts = raw.split("<<<<<<< SEARCH")
    for part in parts[1:]:
        if "=======" not in part or ">>>>>>> REPLACE" not in part:
            raise RuntimeError("model returned a malformed patch block — retry shortly")
        search, rest = part.split("=======", 1)
        replace, _ = rest.split(">>>>>>> REPLACE", 1)
        search = search.strip("\n")
        replace = replace.strip("\n")
        if not search.strip():
            raise RuntimeError("model returned an empty SEARCH block — retry shortly")
        if search == replace:
            continue  # no-op hunk
        blocks.append((search, replace))
    if not blocks:
        raise RuntimeError("model proposed no changes — try a more specific instruction")
    return blocks


def _norm_line(ln: str) -> str:
    return re.sub(r"\s+", " ", ln).strip()


def _apply_blocks(old: str, blocks: list[tuple[str, str]]) -> str:
    new = old
    for search, replace in blocks:
        if search in new:
            new = new.replace(search, replace, 1)
            continue
        # fuzzy fallback: whitespace-tolerant contiguous match (models re-indent)
        nlines = new.split("\n")
        nnorm = [_norm_line(l) for l in nlines]
        slines = [l for l in search.split("\n") if _norm_line(l)]
        if not slines:
            raise RuntimeError("patch SEARCH block is empty — retry shortly")
        hits = [i for i in range(len(nlines) - len(slines) + 1)
                if all(nnorm[i + j] == _norm_line(slines[j]) for j in range(len(slines)))]
        if len(hits) != 1:
            raise RuntimeError(
                "patch SEARCH text not found in file (file may have changed) — retry shortly"
                if not hits else "patch SEARCH text matches multiple places — be more specific")
        i = hits[0]
        span = nlines[i:i + len(slines)]
        new = "\n".join(nlines[:i] + [replace.strip("\n")] + nlines[i + len(span):])
    return new


def _edit_file(path: str, old: str, instruction: str, context: str) -> tuple[str, list[str]]:
    """Patch-based edit: 1 small LLM call returning SEARCH/REPLACE hunks, applied exactly.
    Raises on quota, timeout, malformed patches, or validation regressions."""
    prompt = (
        f"You are editing exactly one file ({path}) in the {context} codebase. "
        "Apply ONLY the requested change; keep everything else byte-identical.\n"
        "Return ONLY patch blocks in this exact format, no markdown fences, no prose:\n"
        "<<<<<<< SEARCH\n<2-8 exact lines copied from the current file>\n"
        "=======\n<replacement lines>\n>>>>>>> REPLACE\n"
        "One block per hunk. If no change is needed, return the single word NOCHANGE.\n"
        f"Change request: {instruction[:500]}\n"
        f"Current file:\n{old[:MAX_OLD_CHARS]}"
    )
    raw = _bounded_call(prompt, 0.2, f"edit call for {path}")
    if not raw or raw.strip() == "NOCHANGE":
        if not raw:
            # intermittent moderation-only response — one fresh sample
            raw = _bounded_call(prompt, 0.2, f"edit retry for {path}")
        if not raw or raw.strip() == "NOCHANGE":
            return old, []  # caller filters unchanged
    new = _apply_blocks(old, _parse_blocks(raw))
    if new == old:
        return old, []
    # Never make validation worse: pristine generator output itself can trip the
    # checker (e.g. esbuild on `!`), so only NEW errors count.
    old_errs = set(_validate(path, old))
    new_errs = set(_validate(path, new))
    if not (new_errs - old_errs):
        return new, []
    raise RuntimeError(f"{path} introduced errors: {'; '.join(sorted(new_errs - old_errs)[:4])}")


def _recheck_wiring(wish: dict, files: list[dict]) -> list[str]:
    """Wiring consistency re-check (0 LLM calls): cross-file import/API consistency
    over the patched file sets. Step edits never change prd tables/pages, so the
    deterministic shells are invariant by construction — no shell diffs emitted."""
    try:
        from services.validator import validate_imports_consistency
        arts = wish.get("artifacts") or {}
        fe = [{**f} for f in ((arts.get("frontend") or {}).get("files") or [])]
        be = [{**f} for f in ((arts.get("backend") or {}).get("files") or [])]
        patched = {f["path"]: f["after"] for f in files}
        for lst in (fe, be):
            for f in lst:
                if f.get("path") in patched:
                    f["content"] = patched[f["path"]]
        return validate_imports_consistency(fe, be)[:5]
    except Exception as e:
        print(f"iterate wiring recheck skipped: {e}")
        return []


def preview_iteration(wish: dict, wid: str, node: dict, instruction: str) -> dict:
    """Edit step files via LLM + deterministic rewire. Pure — persists nothing."""
    prd = wish.get("prd") or {}
    app_name = prd.get("appName", "IntaraApp")
    context = app_name
    if node.get("kind") == "backend_table":
        tbls = [t for t in (prd.get("tables") or []) if t.get("name") == node.get("ref")]
        if tbls:
            context += f" — table {node.get('ref')} fields {json.dumps(tbls[0].get('fields', []))[:600]}"
    elif node.get("kind") == "frontend_page":
        pgs = [p for p in (prd.get("pages") or []) if p.get("name") == node.get("ref")]
        if pgs:
            context += f" — page {node.get('ref')} route {pgs[0].get('route')}"
    targets = step_target_files(wish, wid, node)
    if not targets:
        raise RuntimeError(f"no editable files found for step {node.get('id')}")
    # File edits are independent — run concurrently so wall time ≈ slowest
    # single call instead of the sum (free-pool dribble is the bottleneck).
    from concurrent.futures import ThreadPoolExecutor
    files = []

    def _one(t: dict) -> dict | None:
        new, _warnings = _edit_file(t["path"], t.get("content", ""), instruction, context)
        if new != t.get("content", ""):
            return {"path": t["path"], "before": t.get("content", ""),
                    "after": new, "area": t.get("area", "frontend")}
        return None

    with ThreadPoolExecutor(max_workers=len(targets)) as ex:
        # Context per file edit: ThreadPoolExecutor workers start with an empty
        # context, which would silently drop the caller's BYOK identity.
        carried = [(t, contextvars.copy_context()) for t in targets]
        for result in ex.map(lambda pair: pair[1].run(_one, pair[0]), carried):
            if result:
                files.append(result)
    if not files:
        raise RuntimeError("the model made no changes — try a more specific instruction")
    warnings = _recheck_wiring(wish, files)
    summary = f"{len(files)} file(s) in {node.get('id')}: " + ", ".join(f["path"] for f in files[:4])
    if warnings:
        summary += " | wiring notes: " + "; ".join(warnings[:3])
    return {"step_id": node.get("id"), "files": files, "summary": summary}


# --- persistence (DB with in-memory fallback) ---

def _db():
    from db.wishes import _client
    return _client()


def store_preview(wid: str, step_id: str, instruction: str, files: list[dict]) -> str:
    import uuid
    iid = str(uuid.uuid4())
    slim = [{"path": f["path"], "before": f["before"], "after": f["after"], "area": f.get("area", "frontend")} for f in files]
    try:
        _db().table("wish_iterations").insert({
            "id": iid, "wish_id": wid, "step_id": step_id,
            "instruction": instruction[:500], "files_changed": slim, "status": "preview",
        }).execute()
    except Exception as e:
        print(f"iterate store preview skipped (memory fallback): {e}")
        MEM_ITERS[iid] = {"id": iid, "wish_id": wid, "step_id": step_id,
                          "instruction": instruction[:500], "files_changed": slim,
                          "prev_artifacts": None, "status": "preview"}
    return iid


def get_iteration(iid: str) -> dict | None:
    try:
        res = _db().table("wish_iterations").select("*").eq("id", iid).single().execute()
        if res.data:
            return res.data
    except Exception as e:
        print(f"iterate fetch skipped: {e}")
    return MEM_ITERS.get(iid)


def _set_iter_status(iid: str, status: str, prev_artifacts: dict | None = None):
    try:
        payload: dict = {"status": status}
        if prev_artifacts is not None:
            payload["prev_artifacts"] = prev_artifacts
        _db().table("wish_iterations").update(payload).eq("id", iid).execute()
    except Exception as e:
        print(f"iterate status skipped: {e}")
    if iid in MEM_ITERS:
        MEM_ITERS[iid]["status"] = status
        if prev_artifacts is not None:
            MEM_ITERS[iid]["prev_artifacts"] = prev_artifacts


def _patch_artifacts(wish: dict, files: list[dict]) -> dict:
    import copy
    arts = copy.deepcopy(wish.get("artifacts") or {})
    by_area = {"frontend": ((arts.get("frontend") or {}).get("files") or []),
               "backend": ((arts.get("backend") or {}).get("files") or []),
               "preview": None}
    for f in files:
        area = f.get("area", "frontend")
        if area == "preview":
            arts.setdefault("preview", {})[f["path"]] = f["after"]
            continue
        lst = (arts.setdefault(area, {}).setdefault("files", []))
        for row in lst:
            if row.get("path") == f["path"]:
                row["content"] = f["after"]
                break
        else:
            lst.append({"path": f["path"], "content": f["after"]})
    return arts


def apply_iteration(wish: dict, wid: str, it: dict) -> dict:
    """Snapshot current artifacts, patch files, bump step attempt, mark applied. No LLM."""
    from db.wishes import set_wish_status, get_steps, update_step
    files = it.get("files_changed") or []
    if not files:
        raise RuntimeError("nothing to apply")
    snapshot = wish.get("artifacts") or {}
    new_arts = _patch_artifacts(wish, files)
    set_wish_status(wid, "ready", artifacts=new_arts)
    # bump the step attempt + record the new prompt/output
    try:
        rows = {r["step_id"]: r for r in get_steps(wid)}
        row = rows.get(it.get("step_id"), {})
        update_step(wid, it.get("step_id"),
                    status="done",
                    prompt=f"iterate: {it.get('instruction','')[:500]}",
                    raw_response=json.dumps([f["path"] for f in files])[:20000],
                    output={"files": [f["path"] for f in files], "iterated": True},
                    attempt=int(row.get("attempt", 1)) + 1)
    except Exception as e:
        print(f"iterate step bump skipped: {e}")
    _set_iter_status(it["id"], "applied", prev_artifacts=snapshot)
    try:
        from db.wishes import get_wish_with_steps
        return get_wish_with_steps(wid)
    except Exception:
        wish["artifacts"] = new_arts
        wish["status"] = "ready"
        return wish


def revert_iteration(wish: dict, wid: str, it: dict) -> dict:
    """Restore the pre-apply snapshot. No LLM."""
    from db.wishes import set_wish_status
    prev = it.get("prev_artifacts")
    if not prev and it["id"] in MEM_ITERS:
        prev = MEM_ITERS[it["id"]].get("prev_artifacts")
    if not prev:
        raise RuntimeError("no snapshot to revert to (preview was never applied here)")
    set_wish_status(wid, "ready", artifacts=prev)
    _set_iter_status(it["id"], "reverted")
    try:
        from db.wishes import get_wish_with_steps
        return get_wish_with_steps(wid)
    except Exception:
        wish["artifacts"] = prev
        wish["status"] = "ready"
        return wish
