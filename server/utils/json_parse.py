"""
Shared JSON parsing and quota detection utilities.

Parse ladder (stop at first success):
  1. json.loads direct
  2. fence/prose strip + trailing-comma repair
  3. escape/control-char normalisation (lone backslashes, raw control chars, BOM, smart quotes)
  4. truncation repair — ONLY when truncated is True (or unknown with a
     truncation-like error); skipped when truncated is False so callers can
     fail fast into an LLM repair instead of mangling good-but-big text.
"""
import json
import re


def _strip_wrappers(text: str) -> str:
    text = text.strip().lstrip("\ufeff")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Find outermost JSON object
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        text = m.group(0)
    # Repair common LLM JSON issues: trailing commas
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)
    return text


def _normalise_escapes(text: str) -> str:
    """Fix lone backslashes (\\U, \\x, stray \\) and smart quotes.

    Leaves valid escapes (\\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX) untouched.
    """
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    return re.sub(r"\\(?![\"\\/bfnrtu])", r"\\\\", text)


def _balance_closers(text: str) -> str:
    """Append missing `}`/`]` closers (and a closing quote if inside a string).

    Stack-walk respects string literals and backslash escapes, so braces inside
    strings are never counted.
    """
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in ("}", "]"):
                if stack and stack[-1] == ch:
                    stack.pop()
    if in_str:
        text += '"'
    return text + "".join(reversed(stack))


def _truncate_to_complete(text: str) -> str:
    """Cut to the last *parseable* prefix ending at a `}` or `]`.

    Tries endpoints right-to-left so a truncated tail (unfinished string,
    dangling comma, unclosed array) is dropped rather than mended into
    semantically wrong data.
    """
    closers = [i for i, ch in enumerate(text) if ch in "}]"]
    if not closers:
        raise ValueError("no closing brace/bracket to truncate to")
    last_err: Exception | None = None
    # The break is near the end in truncated output; cap attempts to stay linear.
    for end in reversed(closers[-32:]):
        cand = text[:end + 1]
        try:
            json.loads(_balance_closers(cand), strict=False)
            return _balance_closers(cand)
        except Exception as e:
            last_err = e
            continue
    raise ValueError(f"no parseable prefix found: {last_err}")


def detect_truncation(finish_reason) -> bool | None:
    """Map a provider finish_reason to truncated True/False/unknown(None)."""
    if finish_reason is None:
        return None
    r = str(finish_reason).strip().lower()
    if r in ("length", "max_tokens", "max-tokens", "maxtokens"):
        return True
    if "length" in r or "token" in r and "limit" in r:
        return True
    return False


def parse_json(text: str, *, truncated: bool | None = None) -> dict:
    """Robust JSON extraction — see module docstring for the ladder.

    truncated=True forces truncation repair; False skips it (fail fast);
    None (default) preserves legacy heuristic behavior.
    """
    stripped = _strip_wrappers(text)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # Escape/control-char normalisation (strict=False also allows raw controls)
    normalised = _normalise_escapes(stripped)
    try:
        return json.loads(normalised, strict=False)
    except json.JSONDecodeError:
        pass
    if truncated is False:
        raise json.JSONDecodeError("parse failed (truncation repair skipped)", text, 0)
    # Try to parse, if fails due to truncation, try to truncate to last complete object
    try:
        return json.loads(normalised, strict=False)
    except json.JSONDecodeError as e:
        msg = str(e)
        if truncated is True or "Expecting ',' delimiter" in msg or "Unterminated string" in msg:
            try:
                return json.loads(_truncate_to_complete(normalised), strict=False)
            except Exception:
                pass
        raise


def parse_json_with_repair(text: str, repair_fn, *, truncated: bool | None = None,
                           max_repair_chars: int = 4000) -> tuple[dict, bool]:
    """Parse with the ladder; on failure make ONE repair_fn(err, bad_text) call.

    Returns (data, repaired_flag). repair_fn receives the error message and the
    (capped) failing text and must return replacement text. Raises the original
    JSONDecodeError if repair also fails.
    """
    try:
        return parse_json(text, truncated=truncated), False
    except json.JSONDecodeError as first_err:
        snippet = text if len(text) <= max_repair_chars else text[-max_repair_chars:]
        try:
            fixed = repair_fn(str(first_err), snippet)
        except Exception as e:
            if getattr(e, "byok_error", False):
                raise
            raise first_err
        if not isinstance(fixed, str) or not fixed.strip():
            raise first_err
        try:
            return parse_json(fixed, truncated=truncated), True
        except json.JSONDecodeError:
            raise first_err


def is_quota_error(e: Exception) -> bool:
    """Detects 429 / quota / resource_exhausted across wrapped exceptions (tenacity RetryError etc)."""
    def check(msg: str) -> bool:
        m = msg.lower()
        return "429" in m or "quota" in m or "resource_exhausted" in m or "exhausted" in m

    if check(str(e)):
        return True
    for attr in ("__cause__", "__context__", "last_attempt"):
        try:
            inner = getattr(e, attr, None)
            if inner and check(str(inner)):
                return True
            if inner and hasattr(inner, "exception"):
                if check(str(inner.exception())):
                    return True
            if inner and hasattr(inner, "result"):
                try:
                    res = inner.result()
                except Exception as ex2:
                    if check(str(ex2)):
                        return True
        except:
            pass
    try:
        if hasattr(e, "args") and e.args:
            for arg in e.args:
                if check(str(arg)):
                    return True
    except:
        pass
    return False
