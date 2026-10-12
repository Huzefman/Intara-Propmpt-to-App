/**
 * Permissions (Phase 6, P6.1): role × op × entity from access.rules.
 * `where` is a deliberately small subset (equality/inequality + `and` over
 * dotted paths, literals and $user.* bindings) — NOT the formula language,
 * so the formula grammar stays frozen and auditable.
 */
import type { AppSpec } from "../../spec/app-spec.ts";
import type { Rec } from "./errors.ts";

export interface UserCtx { name?: string; [k: string]: unknown }

type Atom =
  | { kind: "lit"; value: string | number | boolean | null }
  | { kind: "path"; parts: string[] };

interface Cond { left: Atom; op: "==" | "!="; right: Atom }

function tokenizeWhere(src: string): string[] {
  const out: string[] = [];
  const re = /\s*(\$user(?:\.[A-Za-z_][A-Za-z0-9_]*)+|[A-Za-z_][A-Za-z0-9_.]*|==|!=|'[^']*'|"[^"]*"|-?\d+(?:\.\d+)?|true|false|null)\s*/gy;
  let pos = 0;
  while (pos < src.length) {
    re.lastIndex = pos;
    const m = re.exec(src);
    if (!m || m.index !== pos) throw new Error(`bad where near '${src.slice(pos, pos + 12)}'`);
    out.push(m[1]);
    pos += m[0].length;
  }
  return out;
}

function atomOf(tok: string): Atom {
  if (tok === "true") return { kind: "lit", value: true };
  if (tok === "false") return { kind: "lit", value: false };
  if (tok === "null") return { kind: "lit", value: null };
  if ((tok.startsWith("'") && tok.endsWith("'")) || (tok.startsWith('"') && tok.endsWith('"')))
    return { kind: "lit", value: tok.slice(1, -1) };
  if (/^-?\d+(\.\d+)?$/.test(tok)) return { kind: "lit", value: Number(tok) };
  return { kind: "path", parts: tok.split(".") };
}

function parseWhere(src: string): Cond[] {
  const toks = tokenizeWhere(src);
  const conds: Cond[] = [];
  let i = 0;
  while (i < toks.length) {
    const left = atomOf(toks[i++]);
    const op = toks[i++];
    if (op !== "==" && op !== "!=") throw new Error(`bad operator '${op}' in where`);
    if (i >= toks.length) throw new Error("dangling where clause");
    const right = atomOf(toks[i++]);
    conds.push({ left, op, right });
    if (i < toks.length) {
      if (toks[i++] !== "and") throw new Error("where supports only `and`");
    }
  }
  if (!conds.length) throw new Error("empty where");
  return conds;
}

function resolve(atom: Atom, record: Rec, user: UserCtx): unknown {
  if (atom.kind === "lit") return atom.value;
  const [head, ...rest] = atom.parts;
  let cur: unknown = head === "$user" ? (user as Rec) : record;
  for (const seg of (head === "$user" ? rest : atom.parts)) {
    if (typeof cur !== "object" || cur === null) return undefined;
    cur = (cur as Rec)[seg];
  }
  return cur;
}

function wherePasses(where: string, record: Rec, user: UserCtx): boolean {
  let conds: Cond[];
  try {
    conds = parseWhere(where);
  } catch {
    return false; // unparsable where fails closed
  }
  return conds.every(({ left, op, right }) => {
    const a = resolve(left, record, user);
    const b = resolve(right, record, user);
    const eq = JSON.stringify(a) === JSON.stringify(b);
    return op === "==" ? eq : !eq;
  });
}

export function can(
  spec: AppSpec,
  role: string,
  op: string,
  entityId: string,
  record: Rec = {},
  user: UserCtx = {},
): boolean {
  const rules = (spec.access?.rules ?? []).filter(
    (r) => (r.entity === "*" || r.entity === entityId) && r.role === role && (r.ops as string[]).includes(op),
  );
  if (!rules.length) return false;
  return rules.some((r) => !r.where || wherePasses(r.where, record, user));
}
