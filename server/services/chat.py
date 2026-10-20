"""
Wish-scoped custom chat (Q&A + action hints).

One LLM call per answer. Compact context only (names + statuses, never
file contents) to keep token spend small against the shared free-tier pool.
Quota errors degrade to a friendly "out of stardust" reply — never mock
content, never a 429 that breaks the thread UI.
"""
import re

SYSTEM = (
    "You are Intara, a concise build assistant for one specific app wish. "
    "Answer ONLY about this app: its plan, tables, pages, build steps, errors, and next steps. "
    "Keep answers under 120 words, plain prose, no JSON, no code dumps. "
    "If asked about anything unrelated, say you only know this wish and suggest asking about its plan, steps, or errors. "
    "If you don't know, say so briefly."
)

_ACTION_FORK_WORDS = ("add", "fork", "also", "plus", "include", "with")

_FIX_WORDS = ("fix", "change", "update", "remove", "delete", "bug", "broken", "not working", "instead", "should")


def _compact_context(wish: dict) -> str:
    prd = wish.get("prd") or {}
    tables = [t.get("name") for t in (prd.get("tables") or []) if isinstance(t, dict)][:12]
    pages = [p.get("name") for p in (prd.get("pages") or []) if isinstance(p, dict)][:12]
    steps = wish.get("artifacts", {}).get("steps", {}) or {}
    graph = prd.get("buildGraph", []) or []
    step_bits = []
    last_error = ""
    for n in graph:
        sid = n.get("id", "?")
        st = steps.get(sid, {}).get("status", "pending") if isinstance(steps.get(sid), dict) else steps.get(sid, "pending")
        step_bits.append(f"{sid}:{st}")
        err = steps.get(sid, {}).get("error") if isinstance(steps.get(sid), dict) else None
        if st == "failed" and err and not last_error:
            last_error = str(err)[:300]
    lines = [
        f"Wish: {(wish.get('prompt') or '')[:500]}",
        f"App: {prd.get('appName') or 'unnamed'} — {(prd.get('tagline') or '')[:200]}",
        f"Status: {wish.get('status')}",
        f"Tables: {', '.join(tables) or '-'}",
        f"Pages: {', '.join(pages) or '-'}",
        f"Steps: {'; '.join(step_bits[:20]) or '-'}",
    ]
    if last_error:
        lines.append(f"Last error: {last_error}")
    return "\n".join(lines)


def detect_actions(wish: dict, question: str) -> list[dict]:
    """Keyword action hints executed client-side via existing endpoints."""
    q = (question or "").lower()
    actions: list[dict] = []
    steps = wish.get("artifacts", {}).get("steps", {}) or {}
    failed = [sid for sid, s in steps.items() if (s.get("status") if isinstance(s, dict) else s) == "failed"]
    if failed and ("retr" in q or "fix" in q or "fail" in q or "error" in q):
        for sid in failed[:2]:
            actions.append({"label": f"Retry {sid}", "kind": "retry", "stepId": sid})
    # rewrite intent → diff-first iterate preview ("Apply this fix"); server maps to a step
    if any(w in q for w in _FIX_WORDS) and wish.get("status") in ("ready", "failed", "building"):
        step_id = None
        toks = set(re.findall(r"[a-z]{3,}", q))
        for n in (wish.get("prd") or {}).get("buildGraph", []):
            if n.get("kind") not in ("frontend_page", "backend_table"):
                continue
            ref = str(n.get("ref") or "").lower()
            if ref and any(t in ref or ref in t for t in toks if len(t) >= 4):
                step_id = n.get("id")
                break
        fix = {"label": "✦ Apply this fix", "kind": "fix"}
        if step_id:
            fix["stepId"] = step_id
        actions.append(fix)
    if any(w in q for w in _ACTION_FORK_WORDS):
        try:
            from services.suggest import suggest_next
            for s in suggest_next(wish.get("prd") or {})[:2]:
                # only offer fork if the question resembles a suggestion
                if any(tok in q for tok in re.findall(r"[a-z]{4,}", s["label"].lower())):
                    actions.append({"label": f"Fork: + {s['label']}", "kind": "fork", "suffix": s["prompt_suffix"]})
                    break
        except Exception:
            pass
    return actions[:3]


def answer_chat(wish: dict, history: list[dict], question: str) -> dict:
    """
    Returns {reply, actions} or {reply, actions, degraded: True} on quota loss.
    Never raises 429 — the thread UI must stay usable.
    """
    actions = detect_actions(wish, question)
    hist_lines = []
    for m in (history or [])[-6:]:
        role = "User" if m.get("role") == "user" else "Intara"
        hist_lines.append(f"{role}: {(m.get('content') or '')[:600]}")
    prompt = (
        SYSTEM + "\n\n"
        + _compact_context(wish) + "\n"
        + ("Conversation so far:\n" + "\n".join(hist_lines) + "\n" if hist_lines else "")
        + f"User: {question[:1000]}\nIntara:"
    )
    try:
        from services.llm import call_llm
        reply = call_llm(prompt, temperature=0.3).strip()
        if not reply:
            raise ValueError("empty reply")
        return {"reply": reply[:2000], "actions": actions}
    except Exception as e:
        if getattr(e, "byok_error", False):
            # The account's own key failed — say so instead of blaming the
            # shared free pool (or pretending the reply came from their key).
            return {
                "reply": str(e)[:600],
                "actions": actions,
                "degraded": True,
            }
        msg = str(e).lower()
        if "429" in msg or "quota" in msg or "rate" in msg or "limit" in msg:
            return {
                "reply": "Out of stardust for now — the shared free LLM pool is empty. Your wish, plan, and code are safe; try chatting again after the daily reset.",
                "actions": actions,
                "degraded": True,
            }
        print(f"chat LLM failed: {e}")
        return {
            "reply": "I stumbled reading the stars just now — try asking again in a few seconds.",
            "actions": actions,
            "degraded": True,
        }
