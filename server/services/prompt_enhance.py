"""
Wish clarity scoring + clarifying Q&A.

LLM-first for question generation, deterministic fallback everywhere.
Never raises 429 — clarify is advisory, so quota exhaustion degrades to
template questions instead of blocking the user (the plan step still
fail-fasts on quota per the staged pipeline rules).
"""
import os
import re

READY_THRESHOLD = 70

_STOPWORDS = {
    "with", "from", "that", "this", "have", "will", "your", "about",
    "into", "over", "under", "while", "where", "when", "what", "which",
    "their", "there", "would", "could", "should", "want", "need", "make",
    "build", "create", "with", "simple", "just",
}

_DATA_WORDS = {"save", "store", "track", "history", "database", "persist", "record", "remember", "score", "order", "booking"}
_ROLE_WORDS = {"user", "users", "admin", "player", "players", "buyer", "team", "teams", "member", "customer", "wizard"}
_CONSTRAINT_WORDS = {"auth", "due", "difficulty", "price", "payment", "role", "permission", "easy", "medium", "hard", "deadline"}
_ACTION_VERBS = {"track", "manage", "play", "shop", "book", "share", "save", "sell", "buy", "review", "vote", "schedule", "monitor"}


def score_prompt(prompt: str) -> dict:
    """Deterministic 5..98 clarity score with aspect breakdown."""
    p = (prompt or "").lower()
    words = re.findall(r"[a-z]+", p)
    distinct = {w for w in words if len(w) > 4 and w not in _STOPWORDS}

    score = 45
    aspects: dict = {}

    if len(prompt) >= 120:
        score += 10
        aspects["detail"] = True
    elif len(prompt) >= 40:
        score += 5
        aspects["detail"] = "partial"
    else:
        aspects["detail"] = False

    entity_bonus = min(20, len(distinct) * 4)
    score += entity_bonus
    aspects["entities"] = len(distinct) >= 3

    if any(w in p for w in _ACTION_VERBS):
        score += 5
        aspects["actions"] = True
    else:
        aspects["actions"] = False

    if any(w in p for w in _DATA_WORDS):
        score += 5
        aspects["data"] = True
    else:
        aspects["data"] = False

    if any(w in p for w in _ROLE_WORDS):
        score += 5
        aspects["audience"] = True
    else:
        aspects["audience"] = False

    if any(w in p for w in _CONSTRAINT_WORDS):
        score += 5
        aspects["constraints"] = True
    else:
        aspects["constraints"] = False

    score = max(5, min(98, score))
    missing = [k for k, v in aspects.items() if v is not True]
    return {"score": score, "aspects": aspects, "missing": missing}


def derive_app_name(prompt: str) -> str:
    """Generate a clean 1-2 word app name from prompt."""
    p = (prompt or "").lower()
    words = [w for w in re.findall(r"[a-z0-9]+", p) if w not in _STOPWORDS and len(w) > 2]
    if not words:
        return "Intara App"
    cand = "".join(w.capitalize() for w in words[:2])
    return cand[:24] or "Intara App"


def _fallback_questions(prompt: str, scored: dict) -> list[dict]:
    """Template questions based on compiler components (max 3)."""
    p = prompt.lower()
    questions: list[dict] = []

    # 1. Primary component view
    questions.append({
        "id": "view_layout",
        "q": "Which primary view layout fits best?",
        "options": [
            {"label": "Kanban board", "desc": "Drag-and-drop cards grouped by status (data.kanban)"},
            {"label": "Data table", "desc": "Spreadsheet grid with sorting, search and CSV export (data.table)"},
            {"label": "Calendar", "desc": "Month grid for date-driven schedules and deadlines (calendar.month)"},
        ],
    })

    # 2. Roles & access
    questions.append({
        "id": "audience",
        "q": "Who will use this app, and how should access roles work?",
        "options": [
            {"label": "Just me (Personal)", "desc": "Single user — strictly 1 role (owner) with complete direct access"},
            {"label": "Team with roles", "desc": "Shared workspace with admin, editor and viewer roles"},
            {"label": "Multi-role workflow", "desc": "Domain-specific roles (e.g. doctor & patient, manager & staff)"},
        ],
    })

    # 3. Workflows & automations
    questions.append({
        "id": "workflow",
        "q": "What workflows and detail features are key?",
        "options": [
            {"label": "Lifecycle transitions", "desc": "Stage progression with status guards (lifecycle.pipeline)"},
            {"label": "Analytics & Metrics", "desc": "Stat cards, bar charts and timelines (metric.stat, chart.bar)"},
            {"label": "Record details & Sub-items", "desc": "Deep records with related sub-lists (record.detail)"},
        ],
    })

    return questions[:3]


def clarify_prompt(prompt: str) -> dict:
    """
    Returns {appName, tagline, summary, score, ready, questions, redrafted}.
    LLM-first (single small call via Groq); deterministic fallback on any failure.
    """
    scored = score_prompt(prompt)

    # Try Groq LLM call for surface data + component-aware questions
    try:
        from gates.block_catalog import prompt_catalog
        from services.llm import call_llm
        from utils.json_parse import parse_json

        instruction = (
            "You are an expert app architect for Intara, a declarative component app builder.\n"
            "Given the user wish, return a JSON object with surface-level app information and 2-3 clarifying questions.\n"
            "The compiler engine builds apps using only this canonical component catalog:\n"
            + prompt_catalog() + "\n"
            "Return ONLY JSON:\n"
            "{\n"
            '  "appName": "Creative Memorable App Name",\n'
            '  "tagline": "A crisp one-line description of the app",\n'
            '  "summary": "1-2 sentence overview of core entities and workflows",\n'
            '  "score": <number 50-95>,\n'
            '  "questions": [\n'
            '    {"id": "audience", "q": "Who is using this app, and how should access roles work?", "options": [{"label": "Just me (Personal)", "desc": "Single user — strictly 1 role (owner) with complete direct access"}, {"label": "Team with roles", "desc": "Shared workspace with admin, editor and viewer roles"}, {"label": "Multi-role workflow", "desc": "Domain-specific roles (e.g. doctor & patient)"}]},\n'
            '    {"id": "view_layout", "q": "Which primary layout fits best?", "options": [{"label": "Kanban board", "desc": "Drag-and-drop cards across workflow stages"}, {"label": "Data table", "desc": "Spreadsheet grid with sorting and CSV export"}, {"label": "Calendar", "desc": "Month grid for date-driven items"}]},\n'
            '    {"id": "workflow", "q": "...", "options": [{"label": "...", "desc": "..."}]}\n'
            "  ]\n"
            "}\n"
            "Max 3 questions, max 3 options each. Include a question clarifying if the app is strictly personal (1 role) or multi-user team when ambiguous. Questions must have simple, non-technical options.\n\n"
            "Wish: " + prompt[:500]
        )
        raw = call_llm(instruction, temperature=0.3, json_mode=True)
        data = parse_json(raw)
        questions = data.get("questions", [])[:3]
        # validate shape, normalize
        clean = []
        for i, qq in enumerate(questions):
            if not isinstance(qq, dict) or "q" not in qq:
                continue
            opts = [o for o in (qq.get("options") or []) if isinstance(o, dict) and "label" in o][:3]
            if not opts:
                continue
            clean.append({
                "id": str(qq.get("id") or f"q{i+1}"),
                "q": str(qq["q"])[:200],
                "options": [{"label": str(o["label"])[:80], "desc": str(o.get("desc", ""))[:160]} for o in opts]
            })
        if clean:
            score = int(data.get("score", scored["score"]))
            score = max(5, min(98, score))
            app_name = str(data.get("appName") or derive_app_name(prompt)).strip()
            tagline = str(data.get("tagline") or f"A tailored app composed from Intara components.").strip()
            summary = str(data.get("summary") or prompt[:160]).strip()
            return {
                "appName": app_name,
                "tagline": tagline,
                "summary": summary,
                "score": score,
                "ready": score >= READY_THRESHOLD,
                "questions": clean,
                "redrafted": prompt,
                "_meta": {"source": "live"},
            }
    except Exception as e:
        if getattr(e, "byok_error", False):
            raise
        print(f"clarify LLM failed, template fallback: {e}")

    fallback_qs = _fallback_questions(prompt, scored)
    return {
        "appName": derive_app_name(prompt),
        "tagline": "Tailored app composed from Intara components.",
        "summary": prompt[:160],
        "score": scored["score"],
        "ready": scored["score"] >= READY_THRESHOLD,
        "questions": fallback_qs,
        "redrafted": prompt,
        "_meta": {"source": "mock", "missing": scored["missing"]},
    }


def redraft_prompt(prompt: str, answers: dict, questions: list | None = None) -> str:
    """Fold selected answers back into the wish text."""
    qtext = {q["id"]: q["q"] for q in (questions or []) if isinstance(q, dict) and "id" in q}
    parts = [prompt.strip()]
    for qid, label in (answers or {}).items():
        q = qtext.get(qid, qid)
        parts.append(f"{q} Answer: {label}.")
    redrafted = " ".join(parts)
    return redrafted[:2000]
