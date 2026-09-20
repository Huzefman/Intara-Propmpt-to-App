"""
Shared JSON parsing and quota detection utilities
"""
import json
import re


def parse_json(text: str) -> dict:
    """Robust JSON extraction — strips markdown, repairs trailing commas, handles truncation."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Find outermost JSON object
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        text = m.group(0)
    # Repair common LLM JSON issues: trailing commas, single quotes, truncated
    # Remove trailing commas before } or ]
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)
    # Try to parse, if fails due to truncation, try to truncate to last complete object
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # If truncated, try to find last complete '}' and parse up to there
        if "Expecting ',' delimiter" in str(e) or "Unterminated string" in str(e):
            # Try to repair by removing the last incomplete entry
            # Find last '},' before error position and truncate
            try:
                # Attempt to parse with strict=False and allow trailing commas already handled
                # Try to truncate at last valid '}' 
                last_brace = text.rfind("}")
                if last_brace > 0:
                    truncated = text[:last_brace+1]
                    # Ensure braces are balanced by counting
                    open_braces = truncated.count("{")
                    close_braces = truncated.count("}")
                    if open_braces > close_braces:
                        truncated += "}" * (open_braces - close_braces)
                    return json.loads(truncated)
            except:
                pass
        raise


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
