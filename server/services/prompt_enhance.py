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


def _fallback_questions(prompt: str, scored: dict) -> list[dict]:
    """Template questions for aspects the prompt doesn't cover (max 3)."""
    p = prompt.lower()
    questions: list[dict] = []

    if not scored["aspects"].get("audience"):
        questions.append({
            "id": "audience",
            "q": "Who is this for?",
            "options": [
                {"label": "Just me", "desc": "Solo maker trying an idea out"},
                {"label": "Small team", "desc": "Shared workspace with roles"},
                {"label": "End users", "desc": "Public app with sign-in"},
            ],
        })

    # domain-flavored second question
    if any(w in p for w in ("game", "play", "tic", "chess", "quiz")):
        questions.append({
            "id": "opponent",
            "q": "How should players be able to play against each other?",
            "options": [
                {"label": "Solo vs AI", "desc": "Single player challenges a computer opponent"},
                {"label": "Local 2-player", "desc": "Two people share one screen"},
                {"label": "Easy / Medium / Hard", "desc": "Pick a challenge level before each game"},
            ],
        })
    elif any(w in p for w in ("shop", "market", "store", "ecommerce", "e-commerce", "product", "spell")):
        questions.append({
            "id": "commerce",
            "q": "What should buyers be able to do?",
            "options": [
                {"label": "Browse only", "desc": "Catalog with search and filters"},
                {"label": "Cart + checkout", "desc": "Full cart and order flow"},
                {"label": "Wishlist", "desc": "Save items for later"},
            ],
        })
    elif any(w in p for w in ("blog", "forum", "post", "social", "comment", "question")):
        questions.append({
            "id": "social",
            "q": "How should people interact with content?",
            "options": [
                {"label": "Read only", "desc": "Publish and browse"},
                {"label": "Comments", "desc": "Discuss under each post"},
                {"label": "Votes + tags", "desc": "Rank and organize content"},
            ],
        })
    else:
        questions.append({
            "id": "scope",
            "q": "How much should the first version cover?",
            "options": [
                {"label": "Minimal core", "desc": "2–3 screens, essential flows only"},
                {"label": "Full featured", "desc": "4–6 screens with extras"},
            ],
        })

    if not scored["aspects"].get("data"):
        questions.append({
            "id": "data",
            "q": "Where should data live for the trial?",
            "options": [
                {"label": "Browser only", "desc": "Instant trial, no setup"},
                {"label": "Supabase", "desc": "Real database with auth"},
            ],
        })

    return questions[:3]


def clarify_prompt(prompt: str) -> dict:
    """
    Returns {score, ready, questions, redrafted}.
    LLM-first (single small call); deterministic fallback on any failure.
    """
    scored = score_prompt(prompt)

    # Try one small LLM call for sharper questions
    try:
        from services.llm import call_llm
        from utils.json_parse import parse_json

        instruction = (
            "You refine app ideas. Given the wish below, return ONLY JSON: "
            '{"score": <0-100 completeness>, "questions": [{"id": "short_id", "q": "question", '
            '"options": [{"label": "...", "desc": "..."}]}]}. Max 3 questions, max 3 options each. '
            "Questions should resolve the biggest ambiguities (audience, scope, key features). "
            "No markdown, JSON only.\n\nWish: " + prompt[:300]
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
            clean.append({"id": str(qq.get("id") or f"q{i+1}"), "q": str(qq["q"])[:200], "options": [{"label": str(o["label"])[:80], "desc": str(o.get("desc", ""))[:160]} for o in opts]})
        if clean:
            score = int(data.get("score", scored["score"]))
            score = max(5, min(98, score))
            return {
                "score": score,
                "ready": score >= READY_THRESHOLD,
                "questions": clean,
                "redrafted": prompt,
                "_meta": {"source": "live"},
            }
    except Exception as e:
        print(f"clarify LLM failed, template fallback: {e}")

    fallback_qs = _fallback_questions(prompt, scored)
    return {
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
