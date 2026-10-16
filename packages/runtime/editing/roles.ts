/**
 * Deterministic roles editing (Phase 8): pure functions that transform the
 * access slice AND build the equivalent RFC 6902 patch, so UI edits and
 * LLM chat-patches converge on the same versioning path. Guards refuse
 * unsafe edits with EngineError (role in use) instead of guessing.
 */
import type { AppSpec } from "../../spec/app-spec.ts";
import { EngineError } from "../engine/errors.ts";

export interface RolesEdit { spec: AppSpec; patch: Array<Record<string, unknown>>; summary: string }

function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x));
}

function roleIndex(spec: AppSpec, role: string): number {
  return spec.access.roles.findIndex((r) => r.id === role);
}

function usages(spec: AppSpec, role: string): string[] {
  const out: string[] = [];
  for (const p of spec.ui.pages) {
    if ((p.roles ?? []).includes(role)) out.push(`page:${p.id}`);
    for (const n of spec.ui.nav ?? []) {
      if (n.page && (n.roles ?? []).includes(role)) out.push(`nav:${n.page}`);
    }
  }
  for (const e of spec.model.entities) {
    for (const t of e.lifecycle?.transitions ?? []) {
      if ((t.roles ?? []).includes(role)) out.push(`transition:${e.id}.${t.id}`);
    }
  }
  return out;
}

export function addRole(spec: AppSpec, role: string, label?: string): RolesEdit {
  if (!/^[a-z][a-z0-9_]*$/.test(role)) throw new EngineError(`bad role id '${role}'`);
  if (roleIndex(spec, role) >= 0) throw new EngineError(`role '${role}' exists`);
  const next = clone(spec);
  next.access.roles.push({ id: role, label: label ?? role });
  return {
    spec: next,
    patch: [{ op: "add", path: "/access/roles/-", value: { id: role, label: label ?? role } }],
    summary: `Added role ${role}. Give it pages before it can do anything.`,
  };
}

export function removeRole(spec: AppSpec, role: string): RolesEdit {
  const idx = roleIndex(spec, role);
  if (idx < 0) throw new EngineError(`role '${role}' does not exist`);
  const used = usages(spec, role);
  if (used.length > 0)
    throw new EngineError(`role '${role}' is used by ${used.slice(0, 3).join(", ")}${used.length > 3 ? "…" : ""} — unassign first`);
  const next = clone(spec);
  next.access.roles.splice(idx, 1);
  // rule removals reference pre-splice indexes, descending so paths hold
  const patch: Array<Record<string, unknown>> = [{ op: "remove", path: `/access/roles/${idx}` }];
  const ruleIdx: number[] = [];
  next.access.rules.forEach((r, i) => { if (r.role === role) ruleIdx.push(i); });
  ruleIdx.sort((a, b) => b - a);
  for (const i of ruleIdx) {
    next.access.rules.splice(i, 1);
    patch.push({ op: "remove", path: `/access/rules/${i}` });
  }
  return { spec: next, patch, summary: `Removed role ${role} (and ${ruleIdx.length} rule(s)).` };
}

export function setRule(
  spec: AppSpec, role: string, entity: string, ops: string[],
): RolesEdit {
  if (roleIndex(spec, role) < 0) throw new EngineError(`role '${role}' does not exist`);
  const entIds = spec.model.entities.map((e) => e.id);
  if (entity !== "*" && !entIds.includes(entity))
    throw new EngineError(`entity '${entity}' does not exist`);
  const allowed = ["read", "create", "update", "delete"];
  for (const op of ops) {
    if (!allowed.includes(op)) throw new EngineError(`bad op '${op}'`);
  }
  const next = clone(spec);
  const idx = next.access.rules.findIndex((r) => r.role === role && r.entity === entity);
  let patch: Array<Record<string, unknown>>;
  if (ops.length === 0) {
    if (idx < 0) throw new EngineError(`no rule to remove for ${role} on ${entity}`);
    next.access.rules.splice(idx, 1);
    patch = [{ op: "remove", path: `/access/rules/${idx}` }];
    return { spec: next, patch, summary: `Removed ${role} access on ${entity}.` };
  }
  if (idx >= 0) {
    next.access.rules[idx] = { ...next.access.rules[idx], ops: ops as Array<"read" | "create" | "update" | "delete"> };
    patch = [{ op: "replace", path: `/access/rules/${idx}/ops`, value: ops }];
  } else {
    next.access.rules.push({ entity, role, ops: ops as Array<"read" | "create" | "update" | "delete"> });
    patch = [{ op: "add", path: "/access/rules/-", value: { entity, role, ops } }];
  }
  return { spec: next, patch, summary: `Set ${role} on ${entity} to [${ops.join(", ")}].` };
}

export function removeRule(spec: AppSpec, role: string, entity: string): RolesEdit {
  return setRule(spec, role, entity, []);
}
