"""
Formula language — parser + evaluator (Phase 4, P4.3; grammar in
packages/spec/formula/grammar.md).

Tiny expression language for computed fields, guards and filters:
  qty * unit_price · sum(parts.line_total) · if(status == "ready", due_date, null)

Design: hand-written tokenizer + recursive-descent parser (no eval/exec/
compile anywhere in this file — enforced by test). Reads never raise
unexpected exceptions: parse failures raise FormulaSyntaxError, evaluation
failures raise FormulaError; the fuzz suite asserts nothing else escapes.
The TypeScript twin (packages/spec/formula/formula.ts) implements identical
semantics; both run the shared packages/spec/formula/formula-cases.json.
"""
from __future__ import annotations

import datetime
import math
import re
from typing import Any

KEYWORDS = {"and", "or", "not", "true", "false", "null"}


class FormulaSyntaxError(ValueError):
    pass


class FormulaError(ValueError):
    pass


# ---------- tokens ----------
_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<str>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
  | (?P<op>==|!=|<=|>=|&&|\|\||[+\-*/%<>()\.,!])
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<bad>.)
""", re.VERBOSE)

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"'}


def tokenize(src: str) -> list:
    toks = []
    pos = 0
    for m in _TOKEN_RE.finditer(src):
        if m.start() != pos:
            raise FormulaSyntaxError(f"unexpected character at {pos}")
        pos = m.end()
        kind = m.lastgroup
        text = m.group()
        if kind == "ws":
            continue
        if kind == "bad":
            raise FormulaSyntaxError(f"unexpected character {text!r} at {m.start()}")
        if kind == "str":
            quote = text[0]
            body = text[1:-1]
            out = []
            i = 0
            while i < len(body):
                c = body[i]
                if c == "\\" and i + 1 < len(body) and body[i + 1] in _ESCAPES:
                    out.append(_ESCAPES[body[i + 1]])
                    i += 2
                elif c == "\\":
                    raise FormulaSyntaxError(f"bad escape at {m.start() + i}")
                else:
                    out.append(c)
                    i += 1
            toks.append(("str", "".join(out)))
        elif kind == "num":
            toks.append(("num", float(text) if "." in text else int(text)))
        elif kind == "ident":
            toks.append(("ident", text))
        else:
            toks.append(("op", text))
    if pos != len(src):
        raise FormulaSyntaxError(f"unexpected character at {pos}")
    if not src.strip():
        raise FormulaSyntaxError("empty formula")
    return toks


# ---------- parser (AST tuples) ----------
class _Parser:
    def __init__(self, toks: list):
        self.toks = toks
        self.i = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def next(self):
        t = self.peek()
        self.i += 1
        return t

    def expect_op(self, ch: str):
        kind, val = self.next()
        if kind != "op" or val != ch:
            raise FormulaSyntaxError(f"expected {ch!r}, got {val!r}")
        return val

    def parse(self):
        node = self.parse_or()
        kind, val = self.peek()
        if kind is not None:
            raise FormulaSyntaxError(f"trailing input {val!r}")
        return node

    def parse_or(self):
        node = self.parse_and()
        while (self.peek()[0] == "ident" and self.peek()[1] == "or") or \
                self.peek() == ("op", "||"):
            self.next()
            node = ("binop", "or", node, self.parse_and())
        return node

    def parse_and(self):
        node = self.parse_not()
        while (self.peek()[0] == "ident" and self.peek()[1] == "and") or \
                self.peek() == ("op", "&&"):
            self.next()
            node = ("binop", "and", node, self.parse_not())
        return node

    def parse_not(self):
        if self.peek() == ("ident", "not") or self.peek() == ("op", "!"):
            self.next()
            return ("not", self.parse_not())
        return self.parse_cmp()

    def parse_cmp(self):
        node = self.parse_add()
        kind, val = self.peek()
        if kind == "op" and val in ("==", "!=", "<", "<=", ">", ">="):
            self.next()
            return ("binop", val, node, self.parse_add())
        return node

    def parse_add(self):
        node = self.parse_mul()
        while self.peek()[1] in ("+", "-") and self.peek()[0] == "op":
            op = self.next()[1]
            node = ("binop", op, node, self.parse_mul())
        return node

    def parse_mul(self):
        node = self.parse_unary()
        while self.peek()[1] in ("*", "/", "%") and self.peek()[0] == "op":
            op = self.next()[1]
            node = ("binop", op, node, self.parse_unary())
        return node

    def parse_unary(self):
        if self.peek() == ("op", "-"):
            self.next()
            return ("unop", "-", self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        kind, val = self.next()
        if kind == "num":
            return ("num", val)
        if kind == "str":
            return ("str", val)
        if kind == "ident" and val == "true":
            return ("bool", True)
        if kind == "ident" and val == "false":
            return ("bool", False)
        if kind == "ident" and val == "null":
            return ("null",)
        if kind == "ident" and val in ("and", "or", "not"):
            raise FormulaSyntaxError(f"keyword {val!r} used as value")
        if kind == "ident":
            path = [val]
            while self.peek() == ("op", "."):
                self.next()
                k2, v2 = self.next()
                if k2 != "ident" or v2 in KEYWORDS:
                    raise FormulaSyntaxError(f"bad path segment {v2!r}")
                path.append(v2)
            if self.peek() == ("op", "("):
                if len(path) != 1:
                    raise FormulaSyntaxError("only bare names are callable")
                self.next()
                args = []
                if self.peek() != ("op", ")"):
                    args.append(self.parse_or())
                    while self.peek() == ("op", ","):
                        self.next()
                        args.append(self.parse_or())
                self.expect_op(")")
                return ("call", path[0], args)
            return ("var", tuple(path))
        if kind == "op" and val == "(":
            node = self.parse_or()
            self.expect_op(")")
            return node
        raise FormulaSyntaxError(f"unexpected {val!r}")


def parse(src: str):
    """Parse a formula to an AST. Raises FormulaSyntaxError on any garbage."""
    if not isinstance(src, str) or not src.strip():
        raise FormulaSyntaxError("empty formula")
    return _Parser(tokenize(src)).parse()


# ---------- evaluator ----------
def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _truthy(v) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return len(v) > 0
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def _eq(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if _is_num(a) and _is_num(b):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return (set(a) == set(b)
                and all(_eq(a[k], b[k]) for k in a))
    return False


def _now_iso(ctx: dict) -> str:
    now = ctx.get("now")
    if isinstance(now, str) and now:
        return now
    try:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return "1970-01-01T00:00:00"


def _start_of_month(ctx: dict) -> str:
    now = _now_iso(ctx)
    m = re.match(r"(\d{4}-\d{2})", now)
    return f"{m.group(1)}-01" if m else now


def _lookup(path: tuple, env: dict):
    if path[0] not in env:
        raise FormulaError(f"unknown field {path[0]!r}")
    cur = env[path[0]]
    for seg in path[1:]:
        if isinstance(cur, list):
            # member access maps over related collections: parts.line_total
            out = []
            for item in cur:
                if not isinstance(item, dict) or seg not in item:
                    raise FormulaError(f"unknown field {seg!r} in {path[0]!r}")
                out.append(item[seg])
            cur = out
        elif isinstance(cur, dict):
            if seg not in cur:
                raise FormulaError(f"unknown field {'.'.join(path)!r}")
            cur = cur[seg]
        else:
            raise FormulaError(f"cannot access {seg!r} on non-record")
    return cur


def _arith(op: str, a, b):
    if _is_num(a) and _is_num(b):
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return None if b == 0 else a / b
        if op == "%":
            if isinstance(a, int) and isinstance(b, int):
                return None if b == 0 else a % b
            raise FormulaError(f"operator {op} needs integers")
    if op == "+" and isinstance(a, str) and isinstance(b, str):
        return a + b
    raise FormulaError(f"operator {op} needs numbers, got {type(a).__name__} and {type(b).__name__}")


def _num_list(name: str, v) -> list:
    if not isinstance(v, list):
        raise FormulaError(f"{name} needs a list")
    for x in v:
        if not _is_num(x):
            raise FormulaError(f"{name} needs numbers")
    return v


def _call(name: str, args: list, ctx: dict, lazy):
    if name == "if":
        if len(args) != 3:
            raise FormulaError("if needs 3 arguments")
        return lazy(args[1]) if _truthy(lazy(args[0])) else lazy(args[2])
    vals = [lazy(a) for a in args]
    if name == "sum":
        if len(vals) != 1:
            raise FormulaError("sum needs 1 argument")
        return sum(_num_list("sum", vals[0]), 0)
    if name == "count":
        if len(vals) != 1:
            raise FormulaError("count needs 1 argument")
        if not isinstance(vals[0], list):
            raise FormulaError("count needs a list")
        return len(vals[0])
    if name == "min":
        if len(vals) != 1:
            raise FormulaError("min needs 1 argument")
        xs = _num_list("min", vals[0])
        return min(xs) if xs else None
    if name == "max":
        if len(vals) != 1:
            raise FormulaError("max needs 1 argument")
        xs = _num_list("max", vals[0])
        return max(xs) if xs else None
    if name == "avg":
        if len(vals) != 1:
            raise FormulaError("avg needs 1 argument")
        xs = _num_list("avg", vals[0])
        return (sum(xs) / len(xs)) if xs else None
    if name == "len":
        if len(vals) != 1:
            raise FormulaError("len needs 1 argument")
        if not isinstance(vals[0], (str, list, dict)):
            raise FormulaError("len needs a string, list or record")
        return len(vals[0])
    if name == "str":
        if len(vals) != 1:
            raise FormulaError("str needs 1 argument")
        v = vals[0]
        if v is None:
            return ""
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)
    if name == "int":
        if len(vals) != 1:
            raise FormulaError("int needs 1 argument")
        v = vals[0]
        try:
            if isinstance(v, bool):
                raise ValueError()
            if isinstance(v, int):
                return v
            if isinstance(v, float):
                if not math.isfinite(v):
                    raise ValueError()
                return int(v)
            if isinstance(v, str):
                s = v.strip()
                if not re.fullmatch(r"[+-]?\d+", s):
                    raise ValueError()
                return int(s)
            raise ValueError()
        except (ValueError, TypeError):
            raise FormulaError(f"cannot convert to int: {v!r}")
    if name == "float":
        if len(vals) != 1:
            raise FormulaError("float needs 1 argument")
        v = vals[0]
        try:
            if isinstance(v, bool):
                raise ValueError()
            if isinstance(v, (int, float)):
                out = float(v)
            elif isinstance(v, str):
                s = v.strip()
                if not re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?", s):
                    raise ValueError()
                out = float(s)
            else:
                raise ValueError()
            if not math.isfinite(out):
                raise ValueError()
            return out
        except (ValueError, TypeError):
            raise FormulaError(f"cannot convert to float: {v!r}")
    if name == "now":
        if vals:
            raise FormulaError("now takes no arguments")
        return _now_iso(ctx)
    if name == "startOfMonth":
        if vals:
            raise FormulaError("startOfMonth takes no arguments")
        return _start_of_month(ctx)
    raise FormulaError(f"unknown function {name!r}")


def _eval(node, env: dict, ctx: dict):
    tag = node[0]
    if tag == "num" or tag == "str" or tag == "bool":
        return node[1]
    if tag == "null":
        return None
    if tag == "var":
        return _lookup(node[1], env)
    if tag == "not":
        return not _truthy(_eval(node[1], env, ctx))
    if tag == "unop":
        v = _eval(node[2], env, ctx)
        if node[1] == "-" and _is_num(v):
            return -v
        raise FormulaError("unary - needs a number")
    if tag == "binop":
        op = node[1]
        if op == "and":
            return _truthy(_eval(node[2], env, ctx)) and _truthy(_eval(node[3], env, ctx))
        if op == "or":
            return _truthy(_eval(node[2], env, ctx)) or _truthy(_eval(node[3], env, ctx))
        a = _eval(node[2], env, ctx)
        b = _eval(node[3], env, ctx)
        if op in ("==", "!="):
            return _eq(a, b) if op == "==" else not _eq(a, b)
        if op in ("<", "<=", ">", ">="):
            if _is_num(a) and _is_num(b):
                return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
            if isinstance(a, str) and isinstance(b, str):
                return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
            raise FormulaError(f"operator {op} needs numbers or strings")
        return _arith(op, a, b)
    if tag == "call":
        return _call(node[1], node[2], ctx, lambda n: _eval(n, env, ctx))
    raise FormulaError(f"bad AST node {tag!r}")


def evaluate(src: str, record: dict | None = None, related: dict | None = None,
             now: str | None = None):
    """Parse + evaluate. Raises FormulaSyntaxError / FormulaError, nothing else."""
    node = parse(src)
    env = dict(record or {})
    for k, v in (related or {}).items():
        env.setdefault(k, v)
    ctx = {"now": now} if now is not None else {}
    return _eval(node, env, ctx)
