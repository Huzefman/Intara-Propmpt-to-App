/**
 * Formula language — parser + evaluator (Phase 4, P4.3; grammar in grammar.md).
 * TypeScript twin of server/engine/formula.py: identical semantics, both run
 * packages/spec/formula/formula-cases.json. No eval/Function anywhere
 * (enforced by test). Erasable syntax only (runs under node type-stripping).
 */

export class FormulaSyntaxError extends Error {
  constructor(msg: string) { super(msg); this.name = "FormulaSyntaxError"; }
}
export class FormulaError extends Error {
  constructor(msg: string) { super(msg); this.name = "FormulaError"; }
}

export type Value = null | boolean | number | string | Value[] | { [k: string]: Value };
export type AstNode = unknown[];

const KEYWORDS = new Set(["and", "or", "not", "true", "false", "null"]);

type Tok = { kind: "num" | "str" | "ident" | "op"; text: string; num?: number };

const ESCAPES: Record<string, string> = { n: "\n", t: "\t", r: "\r", "\\": "\\", "'": "'", '"': '"' };

export function tokenize(src: string): Tok[] {
  const toks: Tok[] = [];
  const re = /\s+|\d+(?:\.\d+)?|'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|==|!=|<=|>=|&&|\|\||[+\-*/%<>()\.,!]|[A-Za-z_][A-Za-z0-9_]*/y;
  let pos = 0;
  if (!src.trim()) throw new FormulaSyntaxError("empty formula");
  while (pos < src.length) {
    re.lastIndex = pos;
    const m = re.exec(src);
    if (!m || m.index !== pos) throw new FormulaSyntaxError(`unexpected character at ${pos}`);
    const text = m[0];
    pos += text.length;
    if (/^\s+$/.test(text)) continue;
    if (/^\d/.test(text)) {
      toks.push({ kind: "num", text, num: text.includes(".") ? parseFloat(text) : parseInt(text, 10) });
    } else if (text[0] === "'" || text[0] === '"') {
      const quote = text[0];
      const body = text.slice(1, -1);
      let out = "";
      for (let i = 0; i < body.length; i++) {
        const c = body[i];
        if (c === "\\") {
          const e = body[i + 1];
          if (!(e in ESCAPES)) throw new FormulaSyntaxError(`bad escape at ${m.index + i}`);
          out += ESCAPES[e];
          i++;
        } else out += c;
      }
      toks.push({ kind: "str", text: out });
    } else if (/^[A-Za-z_]/.test(text)) {
      toks.push({ kind: "ident", text });
    } else if (/^[+\-*/%<>()\.,!=]$/.test(text) || ["==", "!=", "<=", ">=", "&&", "||"].includes(text)) {
      toks.push({ kind: "op", text });
    } else {
      throw new FormulaSyntaxError(`unexpected character ${JSON.stringify(text)} at ${m.index}`);
    }
  }
  return toks;
}

class Parser {
  i = 0;
  toks: Tok[];
  constructor(toks: Tok[]) { this.toks = toks; }
  peek(): Tok | null { return this.i < this.toks.length ? this.toks[this.i] : null; }
  next(): Tok {
    const t = this.peek();
    if (!t) throw new FormulaSyntaxError("unexpected end of input");
    this.i++;
    return t;
  }
  expectOp(ch: string): void {
    const t = this.next();
    if (t.kind !== "op" || t.text !== ch) throw new FormulaSyntaxError(`expected '${ch}', got '${t.text}'`);
  }
  isOp(...ops: string[]): boolean {
    const t = this.peek();
    return !!t && t.kind === "op" && ops.includes(t.text);
  }
  isIdent(word: string): boolean {
    const t = this.peek();
    return !!t && t.kind === "ident" && t.text === word;
  }
  parse(): AstNode {
    const node = this.parseOr();
    const t = this.peek();
    if (t) throw new FormulaSyntaxError(`trailing input '${t.text}'`);
    return node;
  }
  parseOr(): AstNode {
    let node = this.parseAnd();
    while (this.isIdent("or") || this.isOp("||")) { this.next(); node = ["binop", "or", node, this.parseAnd()]; }
    return node;
  }
  parseAnd(): AstNode {
    let node = this.parseNot();
    while (this.isIdent("and") || this.isOp("&&")) { this.next(); node = ["binop", "and", node, this.parseNot()]; }
    return node;
  }
  parseNot(): AstNode {
    if (this.isIdent("not") || this.isOp("!")) { this.next(); return ["not", this.parseNot()]; }
    return this.parseCmp();
  }
  parseCmp(): AstNode {
    const node = this.parseAdd();
    const t = this.peek();
    if (t && t.kind === "op" && ["==", "!=", "<", "<=", ">", ">="].includes(t.text)) {
      this.next();
      return ["binop", t.text, node, this.parseAdd()];
    }
    return node;
  }
  parseAdd(): AstNode {
    let node = this.parseMul();
    while (this.isOp("+", "-")) { const op = this.next().text; node = ["binop", op, node, this.parseMul()]; }
    return node;
  }
  parseMul(): AstNode {
    let node = this.parseUnary();
    while (this.isOp("*", "/", "%")) { const op = this.next().text; node = ["binop", op, node, this.parseUnary()]; }
    return node;
  }
  parseUnary(): AstNode {
    if (this.isOp("-")) { this.next(); return ["unop", "-", this.parseUnary()]; }
    return this.parsePrimary();
  }
  parsePrimary(): AstNode {
    const t = this.next();
    if (t.kind === "num") return ["num", t.num];
    if (t.kind === "str") return ["str", t.text];
    if (t.kind === "ident" && t.text === "true") return ["bool", true];
    if (t.kind === "ident" && t.text === "false") return ["bool", false];
    if (t.kind === "ident" && t.text === "null") return ["null"];
    if (t.kind === "ident" && ["and", "or", "not"].includes(t.text))
      throw new FormulaSyntaxError(`keyword '${t.text}' used as value`);
    if (t.kind === "ident") {
      const path = [t.text];
      while (this.isOp(".")) {
        this.next();
        const s = this.next();
        if (s.kind !== "ident" || KEYWORDS.has(s.text))
          throw new FormulaSyntaxError(`bad path segment '${s.text}'`);
        path.push(s.text);
      }
      if (this.isOp("(")) {
        if (path.length !== 1) throw new FormulaSyntaxError("only bare names are callable");
        this.next();
        const args: AstNode[] = [];
        if (!this.isOp(")")) {
          args.push(this.parseOr());
          while (this.isOp(",")) { this.next(); args.push(this.parseOr()); }
        }
        this.expectOp(")");
        return ["call", path[0], args];
      }
      return ["var", path];
    }
    if (t.kind === "op" && t.text === "(") {
      const node = this.parseOr();
      this.expectOp(")");
      return node;
    }
    throw new FormulaSyntaxError(`unexpected '${t.text}'`);
  }
}

export function parse(src: string): AstNode {
  if (typeof src !== "string" || !src.trim()) throw new FormulaSyntaxError("empty formula");
  return new Parser(tokenize(src)).parse();
}

function isNum(v: Value): v is number { return typeof v === "number"; }

function truthy(v: Value): boolean {
  if (v === null) return false;
  if (typeof v === "boolean") return v;
  if (typeof v === "number") return v !== 0;
  if (typeof v === "string") return v.length > 0;
  if (Array.isArray(v)) return v.length > 0;
  return Object.keys(v).length > 0;
}

function eq(a: Value, b: Value): boolean {
  if (a === null || b === null) return a === null && b === null;
  if (typeof a === "boolean" || typeof b === "boolean")
    return typeof a === "boolean" && typeof b === "boolean" && a === b;
  if (typeof a === "number" && typeof b === "number") return a === b;
  if (typeof a === "string" && typeof b === "string") return a === b;
  if (Array.isArray(a) && Array.isArray(b))
    return a.length === b.length && a.every((x, i) => eq(x, (b as Value[])[i]));
  if (typeof a === "object" && typeof b === "object" && a && b) {
    const ao = a as Record<string, Value>, bo = b as Record<string, Value>;
    const ka = Object.keys(ao), kb = Object.keys(bo);
    return ka.length === kb.length && ka.every((k) => k in bo && eq(ao[k], bo[k]));
  }
  return false;
}

function lookup(path: string[], env: Record<string, Value>): Value {
  if (!(path[0] in env)) throw new FormulaError(`unknown field '${path[0]}'`);
  let cur: Value = env[path[0]];
  for (const seg of path.slice(1)) {
    if (Array.isArray(cur)) {
      cur = cur.map((item) => {
        if (typeof item !== "object" || item === null || Array.isArray(item) || !(seg in item))
          throw new FormulaError(`unknown field '${seg}' in '${path[0]}'`);
        return (item as Record<string, Value>)[seg];
      });
    } else if (typeof cur === "object" && cur !== null && !Array.isArray(cur)) {
      if (!(seg in cur)) throw new FormulaError(`unknown field '${path.join(".")}'`);
      cur = (cur as Record<string, Value>)[seg];
    } else throw new FormulaError(`cannot access '${seg}' on non-record`);
  }
  return cur;
}

function arith(op: string, a: Value, b: Value): Value {
  if (isNum(a) && isNum(b)) {
    if (op === "+") return a + b;
    if (op === "-") return a - b;
    if (op === "*") return a * b;
    if (op === "/") return b === 0 ? null : a / b;
    if (op === "%") {
      if (!Number.isInteger(a) || !Number.isInteger(b)) throw new FormulaError(`operator ${op} needs integers`);
      return b === 0 ? null : a % b;
    }
  }
  if (op === "+" && typeof a === "string" && typeof b === "string") return a + b;
  throw new FormulaError(`operator ${op} needs numbers, got ${typeof a} and ${typeof b}`);
}

function numList(name: string, v: Value): number[] {
  if (!Array.isArray(v)) throw new FormulaError(`${name} needs a list`);
  for (const x of v) if (!isNum(x)) throw new FormulaError(`${name} needs numbers`);
  return v as number[];
}

export interface EvalCtx { now?: string }

function nowIso(ctx: EvalCtx): string {
  if (ctx.now) return ctx.now;
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}T${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}
function startOfMonth(ctx: EvalCtx): string {
  const m = /^(\d{4}-\d{2})/.exec(nowIso(ctx));
  return m ? `${m[1]}-01` : nowIso(ctx);
}

function callFn(name: string, args: AstNode[], env: Record<string, Value>, ctx: EvalCtx): Value {
  const lazy = (n: AstNode): Value => ev(n, env, ctx);
  if (name === "if") {
    if (args.length !== 3) throw new FormulaError("if needs 3 arguments");
    return truthy(lazy(args[0])) ? lazy(args[1]) : lazy(args[2]);
  }
  const vals = args.map(lazy);
  switch (name) {
    case "sum": {
      if (vals.length !== 1) throw new FormulaError("sum needs 1 argument");
      return numList("sum", vals[0]).reduce((s, x) => s + x, 0);
    }
    case "count": {
      if (vals.length !== 1) throw new FormulaError("count needs 1 argument");
      if (!Array.isArray(vals[0])) throw new FormulaError("count needs a list");
      return vals[0].length;
    }
    case "min": {
      if (vals.length !== 1) throw new FormulaError("min needs 1 argument");
      const xs = numList("min", vals[0]);
      return xs.length ? Math.min(...xs) : null;
    }
    case "max": {
      if (vals.length !== 1) throw new FormulaError("max needs 1 argument");
      const xs = numList("max", vals[0]);
      return xs.length ? Math.max(...xs) : null;
    }
    case "avg": {
      if (vals.length !== 1) throw new FormulaError("avg needs 1 argument");
      const xs = numList("avg", vals[0]);
      return xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null;
    }
    case "len": {
      if (vals.length !== 1) throw new FormulaError("len needs 1 argument");
      const v = vals[0];
      if (typeof v === "string" || Array.isArray(v)) return v.length;
      if (typeof v === "object" && v !== null) return Object.keys(v).length;
      throw new FormulaError("len needs a string, list or record");
    }
    case "str": {
      if (vals.length !== 1) throw new FormulaError("str needs 1 argument");
      const v = vals[0];
      if (v === null) return "";
      if (typeof v === "boolean") return v ? "true" : "false";
      return String(v);
    }
    case "int": {
      if (vals.length !== 1) throw new FormulaError("int needs 1 argument");
      const v = vals[0];
      if (typeof v === "boolean") throw new FormulaError(`cannot convert to int: ${JSON.stringify(v)}`);
      if (typeof v === "number") {
        if (!Number.isFinite(v)) throw new FormulaError(`cannot convert to int: ${JSON.stringify(v)}`);
        return Math.trunc(v);
      }
      if (typeof v === "string" && !/^\s*[+-]?\d+\s*$/.test(v)) throw new FormulaError(`cannot convert to int: ${JSON.stringify(v)}`);
      if (typeof v === "string") return parseInt(v, 10);
      throw new FormulaError(`cannot convert to int: ${JSON.stringify(v)}`);
    }
    case "float": {
      if (vals.length !== 1) throw new FormulaError("float needs 1 argument");
      const v = vals[0];
      if (typeof v === "boolean") throw new FormulaError(`cannot convert to float: ${JSON.stringify(v)}`);
      if (typeof v === "number") {
        if (!Number.isFinite(v)) throw new FormulaError(`cannot convert to float: ${JSON.stringify(v)}`);
        return v;
      }
      if (typeof v === "string") {
        if (!/^\s*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\s*$/.test(v)) throw new FormulaError(`cannot convert to float: ${JSON.stringify(v)}`);
        const n = Number(v.trim());
        if (!Number.isFinite(n)) throw new FormulaError(`cannot convert to float: ${JSON.stringify(v)}`);
        return n;
      }
      throw new FormulaError(`cannot convert to float: ${JSON.stringify(v)}`);
    }
    case "now": {
      if (vals.length) throw new FormulaError("now takes no arguments");
      return nowIso(ctx);
    }
    case "startOfMonth": {
      if (vals.length) throw new FormulaError("startOfMonth takes no arguments");
      return startOfMonth(ctx);
    }
    default: throw new FormulaError(`unknown function '${name}'`);
  }
}

function ev(node: AstNode, env: Record<string, Value>, ctx: EvalCtx): Value {
  const tag = node[0] as string;
  if (tag === "num" || tag === "str" || tag === "bool") return node[1] as Value;
  if (tag === "null") return null;
  if (tag === "var") return lookup(node[1] as string[], env);
  if (tag === "not") return !truthy(ev(node[1] as AstNode, env, ctx));
  if (tag === "unop") {
    const v = ev(node[2] as AstNode, env, ctx);
    if (node[1] === "-" && isNum(v)) return -v;
    throw new FormulaError("unary - needs a number");
  }
  if (tag === "binop") {
    const op = node[1] as string;
    if (op === "and") return truthy(ev(node[2] as AstNode, env, ctx)) && truthy(ev(node[3] as AstNode, env, ctx));
    if (op === "or") return truthy(ev(node[2] as AstNode, env, ctx)) || truthy(ev(node[3] as AstNode, env, ctx));
    const a = ev(node[2] as AstNode, env, ctx);
    const b = ev(node[3] as AstNode, env, ctx);
    if (op === "==") return eq(a, b);
    if (op === "!=") return !eq(a, b);
    if (["<", "<=", ">", ">="].includes(op)) {
      if (isNum(a) && isNum(b)) {
        return op === "<" ? a < b : op === "<=" ? a <= b : op === ">" ? a > b : a >= b;
      }
      if (typeof a === "string" && typeof b === "string") {
        return op === "<" ? a < b : op === "<=" ? a <= b : op === ">" ? a > b : a >= b;
      }
      throw new FormulaError(`operator ${op} needs numbers or strings`);
    }
    return arith(op, a, b);
  }
  if (tag === "call") return callFn(node[1] as string, node[2] as AstNode[], env, ctx);
  throw new FormulaError(`bad AST node '${tag}'`);
}

export function evaluate(
  src: string,
  record: Record<string, Value> = {},
  related: Record<string, Value> = {},
  ctx: EvalCtx = {},
): Value {
  const node = parse(src);
  const env: Record<string, Value> = { ...record };
  for (const k of Object.keys(related)) if (!(k in env)) env[k] = related[k];
  return ev(node, env, ctx);
}
