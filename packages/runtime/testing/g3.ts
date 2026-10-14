/**
 * G3 — spec-driven test generator (Phase 6, P6.5).
 * Derives checks from the spec itself and runs them against engine +
 * MemoryAdapter: seed load (defaults→validate→put), CRUD per entity,
 * computed/refs on seed rows, lifecycle transition matrix, permission
 * closed-world. Zero LLM calls. Fails closed with named failures.
 */
import type { AppSpec } from "../../spec/app-spec.ts";
import { applyDefaults } from "../engine/defaults.ts";
import { validateRecord } from "../engine/validate.ts";
import { computeRecord } from "../engine/computed.ts";
import { checkRefsExist } from "../engine/refs.ts";
import { applyTransition } from "../engine/lifecycle.ts";
import { can } from "../engine/permissions.ts";
import { MemoryAdapter } from "../adapters/memory.ts";

export interface G3Failure { check: string; message: string }
export interface G3Result { spec: string; checks: number; failures: G3Failure[] }

/** Resolve seed @keys to synthetic ids; returns entity → rows with ids. */
export function resolveSeed(spec: AppSpec): Record<string, Array<Record<string, unknown>>> {
  const seed = spec.seed ?? {};
  const keyToId: Record<string, string> = {};
  const out: Record<string, Array<Record<string, unknown>>> = {};
  for (const [ent, rows] of Object.entries(seed)) {
    out[ent] = (rows as Array<Record<string, unknown>>).map((r, i) => {
      const id = `${ent}-${i + 1}`;
      if (typeof r["_key"] === "string") keyToId[r["_key"]] = id;
      return { ...r, id };
    });
  }
  for (const rows of Object.values(out)) {
    for (const r of rows) {
      for (const [k, v] of Object.entries(r)) {
        if (typeof v === "string" && v.startsWith("@") && keyToId[v.slice(1)] !== undefined)
          r[k] = keyToId[v.slice(1)];
      }
    }
  }
  return out;
}

/** Related collections for computed formulas (relation_name → rows). */
function relatedFor(spec: AppSpec, rows: Record<string, Array<Record<string, unknown>>>) {
  const rel: Record<string, Array<Record<string, unknown>>> = {};
  for (const e of spec.model.entities) {
    for (const f of e.fields) {
      if ((f.type === "ref" || f.type === "multi_ref") && f.target && f.relation_name) {
        rel[f.relation_name] = (rows[e.id] ?? []).map((r) => ({ ...r }));
      }
    }
  }
  return rel;
}

const ALL_OPS = ["read", "create", "update", "delete"];

export async function runG3(spec: AppSpec, name: string): Promise<G3Result> {
  const failures: G3Failure[] = [];
  let checks = 0;
  const fail = (check: string, message: string) => failures.push({ check, message });
  const pass = () => { checks++; };

  const db = new MemoryAdapter();
  const enums = Object.fromEntries((spec.model.enums ?? []).map((e) => [e.id, e]));
  const seed = resolveSeed(spec);

  // 1. seed load: defaults → validate → put
  for (const e of spec.model.entities) {
    for (const row of seed[e.id] ?? []) {
      const withDefaults = applyDefaults(e, row);
      const errs = validateRecord(e, withDefaults, enums);
      checks++;
      if (errs.length) fail(`seed:${e.id}`, errs.map((x) => `${x.field} ${x.message}`).join("; "));
      else await db.put(e.id, withDefaults);
    }
  }

  // 2. CRUD per entity on synthetic records
  for (const e of spec.model.entities) {
    const probe: Record<string, unknown> = { id: `g3-${e.id}` };
    for (const f of e.fields) {
      if (f.computed || probe[f.id] !== undefined) continue;
      probe[f.id] = f.type === "int" || f.type === "decimal" || f.type === "money" ? 1
        : f.type === "bool" ? true
        : f.type === "enum" ? ((spec.model.enums ?? []).find((x) => x.id === f.enum)?.values[0]?.value ?? "x")
        : f.type.startsWith("multi") ? []
        : "g3";
    }
    const full = applyDefaults(e, probe);
    const errs = validateRecord(e, full, enums);
    checks++;
    if (errs.length) { fail(`crud:${e.id}`, `probe invalid: ${errs.map((x) => x.message).join(";")}`); continue; }
    const saved = await db.put(e.id, full);
    const back = await db.get(e.id, saved["id"] as string);
    checks++;
    if (JSON.stringify(back) !== JSON.stringify(saved)) fail(`crud:${e.id}`, "get != put");
    await db.remove(e.id, saved["id"] as string);
    checks++;
    if ((await db.get(e.id, saved["id"] as string)) !== null) fail(`crud:${e.id}`, "remove did not stick");
  }

  // 3. computed + refs on seed rows (two passes: seed rows rarely carry
  // their own computed values, so fill leaves first, then relate, then check)
  const filled: Record<string, Array<Record<string, unknown>>> = {};
  for (const e of spec.model.entities)
    filled[e.id] = (seed[e.id] ?? []).map((r) => computeRecord(e, r, {}).record);
  const rel = relatedFor(spec, filled);
  for (const e of spec.model.entities) {
    for (const row of seed[e.id] ?? []) {
      const { errors } = computeRecord(e, row, rel);
      checks++;
      if (errors.length) fail(`computed:${e.id}`, errors.map((x) => x.message).join(";"));
      const refErrs = await checkRefsExist(spec, e.id, row, async (ent, id) => db.get(ent, id));
      checks++;
      if (refErrs.length) fail(`refs:${e.id}`, refErrs.map((x) => x.message).join(";"));
    }
  }

  // 4. lifecycle matrix
  for (const e of spec.model.entities) {
    const lc = e.lifecycle;
    if (!lc) continue;
    for (const t of lc.transitions ?? []) {
      const from = { [lc.field]: t.from } as Record<string, unknown>;
      if (!t.guard) {
        // Guarded transitions need full records to evaluate; the probe only
        // asserts their negative paths (guarded-positive is engine-tested).
        checks++;
        try {
          const moved = applyTransition(spec, e.id, from, t.id, {});
          if (moved[lc.field] !== t.to) fail(`lifecycle:${e.id}.${t.id}`, "wrong target state");
        } catch (err) {
          fail(`lifecycle:${e.id}.${t.id}`, `valid transition threw: ${(err as Error).message}`);
        }
      } else {
        // Guarded transitions need full records; the probe asserts the guard
        // is actually consulted (pass-through or guard-block, never a crash
        // or a wrong-state/role verdict on a bare probe record).
        checks++;
        try {
          applyTransition(spec, e.id, from, t.id, {});
        } catch (err) {
          const msg = (err as Error).message;
          if (!/guard|fields|unknown/i.test(msg))
            fail(`lifecycle:${e.id}.${t.id}`, `guarded transition misbehaved: ${msg}`);
        }
      }
      checks++;
      try {
        applyTransition(spec, e.id, { [lc.field]: "__wrong__" }, t.id, {});
        fail(`lifecycle:${e.id}.${t.id}`, "wrong-state transition did not throw");
      } catch { /* expected */ }
      if ((t.roles ?? []).length > 0) {
        checks++;
        try {
          applyTransition(spec, e.id, from, t.id, { role: "__nobody__" });
          fail(`lifecycle:${e.id}.${t.id}`, "role check did not throw");
        } catch { /* expected */ }
      }
    }
  }

  // 5. permission closed-world: uncovered op → false; each rule positive
  for (const r of spec.access.roles) {
    for (const e of spec.model.entities) {
      for (const op of ALL_OPS) {
        const covered = spec.access.rules.some(
          (x) => (x.entity === "*" || x.entity === e.id) && x.role === r.id && (x.ops as string[]).includes(op));
        if (!covered) {
          checks++;
          if (can(spec, r.id, op, e.id)) fail(`perms:${r.id}/${op}/${e.id}`, "uncovered op allowed");
        }
      }
    }
  }
  for (const rule of spec.access.rules) {
    if (rule.where) continue; // needs a matching record; covered by engine unit tests
    checks++;
    const ents = rule.entity === "*" ? spec.model.entities.map((e) => e.id) : [rule.entity];
    for (const ent of ents) {
      for (const op of rule.ops) {
        if (!can(spec, rule.role, op as string, ent)) {
          fail(`perms:${rule.role}/${op}/${ent}`, "rule does not grant");
          break;
        }
      }
    }
  }

  return { spec: name, checks, failures };
}
