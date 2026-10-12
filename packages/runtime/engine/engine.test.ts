/** Engine unit tests (Phase 6, P6.1): gold specs as fixtures, no network. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AppSpec } from "../../spec/app-spec.ts";
import {
  EngineError, allowedTransitions, applyDefaults, applyTransition, can,
  checkRefsExist, computeRecord, enforceOnDelete, validateRecord,
} from "./index.ts";
import type { Rec } from "./index.ts";

const dir = dirname(fileURLToPath(import.meta.url));
const repair = JSON.parse(readFileSync(join(dir, "../../spec/exemplars/repair-tracker.json"), "utf8")) as AppSpec;
const stock = JSON.parse(readFileSync(join(dir, "../../spec/exemplars/inventory.json"), "utf8")) as AppSpec;

function entity(spec: AppSpec, id: string) {
  const e = spec.model.entities.find((x) => x.id === id);
  assert.ok(e, `entity ${id}`);
  return e!;
}
function enums(spec: AppSpec) {
  return Object.fromEntries(spec.model.enums.map((e) => [e.id, e]));
}

test("validate: required, types, enum membership, computed skipped", () => {
  const item = entity(stock, "item");
  assert.deepEqual(validateRecord(item, { sku: "A", name: "x", qty: 1, price: 2 }, enums(stock)), []);
  assert.deepEqual(validateRecord(item, { name: "x", qty: 1, price: 2 }, enums(stock)),
    [{ field: "sku", message: "is required" }]);
  const bad = validateRecord(item, { sku: "A", name: "x", qty: "1", price: 2 }, enums(stock));
  assert.deepEqual(bad, [{ field: "qty", message: "must be an integer" }]);
  // computed stock_value absent from input: fine
  assert.deepEqual(validateRecord(item, { sku: "A", name: "x", qty: 1, price: 2 }, enums(stock)), []);
  // unknown keys ignored
  assert.deepEqual(validateRecord(item, { sku: "A", name: "x", qty: 1, price: 2, zzz: 1 }, enums(stock)), []);
});

test("validate: every type branch", () => {
  const mk = (fields: Array<Record<string, unknown>>) => ({
    id: "t", label: "T", fields: fields as never,
  });
  const e = (t: string, v: unknown, extra: Record<string, unknown> = {}) =>
    validateRecord(mk([{ id: "f", type: t, ...extra }]), { f: v });
  assert.deepEqual(e("bool", "yes"), [{ field: "f", message: "must be true/false" }]);
  assert.deepEqual(e("bool", true), []);
  assert.deepEqual(e("decimal", "x"), [{ field: "f", message: "must be a number" }]);
  assert.deepEqual(e("multi_enum", ["a", 1]), [{ field: "f", message: "must be a list of text" }]);
  assert.deepEqual(e("multi_enum", ["a"]), []);
  assert.deepEqual(e("multi_ref", "x"), [{ field: "f", message: "must be a list of record ids" }]);
  assert.deepEqual(e("ref", { id: 1 }), [{ field: "f", message: "must be a record id" }]);
  assert.deepEqual(e("json", { anything: [1] }), []);
  assert.deepEqual(e("date", 20240101), [{ field: "f", message: "must be text" }]);
  assert.deepEqual(e("weird", 1), [{ field: "f", message: "unknown field type 'weird'" }]);
  assert.deepEqual(e("int", true), [{ field: "f", message: "must be an integer" }]);
});

test("validate: enum membership", () => {
  const job = entity(repair, "job");
  const bad = validateRecord(job, { customer: "c", device: "d", problem: "p", status: "zzz" }, enums(repair));
  assert.equal(bad.length, 1);
  assert.match(bad[0].message, /must be one of/);
});

test("defaults: literals and now()", () => {
  const item = entity(stock, "item");
  assert.deepEqual(applyDefaults(item, { sku: "A" }),
    { sku: "A", qty: 0, reorder_at: 5 });
  const job = entity(repair, "job");
  const out = applyDefaults(job, { customer: "c" }, "2026-05-01T10:00:00") as Rec;
  assert.equal(out["received_at"], "2026-05-01T10:00:00");
  assert.equal(out["status"], "received");
  assert.equal(out["labour_cost"], 0);
});

test("computed: chained formulas and graceful failure", () => {
  const job = entity(repair, "job");
  const { record, errors } = computeRecord(job,
    { labour_cost: 500, parts_total: 2500 },
    { parts: [{ line_total: 2200 }, { line_total: 300 }] });
  assert.deepEqual(errors, []);
  // parts_total recomputed from related; total sees the fresh value
  assert.equal(record["parts_total"], 2500);
  assert.equal(record["total"], 3000);
  const bad = computeRecord(
    { ...job, fields: [...job.fields, { id: "x", type: "money" as const, computed: { formula: "nope + 1" } }] },
    { labour_cost: 1 }, { parts: [{ line_total: 1 }] });
  assert.equal(bad.record["x"], null);
  assert.equal(bad.errors.length, 1);
});

test("refs: existence checks", async () => {
  const get = async (ent: string, id: string | number): Promise<Rec | null> =>
    ent === "customer" && id === "c1" ? { id: "c1" } : null;
  assert.deepEqual(await checkRefsExist(repair, "job", { customer: "c1" }, get), []);
  const miss = await checkRefsExist(repair, "job", { customer: "zz" }, get);
  assert.equal(miss.length, 1);
  assert.match(miss[0].message, /does not exist/);
  const unknown = await checkRefsExist(repair, "nope", {}, get);
  assert.match(unknown[0].message, /unknown entity/);
  const badId = await checkRefsExist(repair, "part", { job: [{}], name: "x" }, get);
  assert.ok(badId.some((e) => e.message === "must be a record id"));
});

test("refs: onDelete restrict/cascade/set_null", async () => {
  const rows: Record<string, Rec[]> = {
    job: [{ id: "j1" }],
    part: [{ id: "p1", job: "j1" }],
  };
  const store = {
    list: async (e: string, f?: Record<string, unknown>) => {
      const rs = (rows[e] ?? []).filter((r) => !f || Object.entries(f).every(([k, v]) => r[k] === v));
      return { rows: rs.map((r) => ({ ...r })), total: rs.length };
    },
    get: async (e: string, id: string | number) =>
      (rows[e] ?? []).find((r) => r["id"] === id) ?? null,
    put: async (_e: string, rec: Rec) => {
      const i = rows["part"].findIndex((r) => r["id"] === rec["id"]);
      rows["part"][i] = { ...rec };
      return rec;
    },
    remove: async (e: string, id: string | number) => {
      rows[e] = (rows[e] ?? []).filter((r) => r["id"] !== id);
    },
  };
  // part.job is cascade, job.customer restrict (customer entity untouched here)
  const casc = await enforceOnDelete(repair, store, "job", "j1");
  assert.deepEqual(casc, { deleted: 1, nulled: 0 });
  assert.deepEqual(rows["part"], []);
  // restrict: customer j-row still referenced? add a job pointing at c1
  rows["job"] = [{ id: "j2", customer: "c1" }];
  await assert.rejects(enforceOnDelete(repair, store, "customer", "c1"), EngineError);
});

test("refs: set_null nullifies children", async () => {
  const spec = JSON.parse(JSON.stringify(repair)) as AppSpec;
  const part = spec.model.entities.find((e) => e.id === "part")!;
  part.fields.find((f) => f.id === "job")!.onDelete = "set_null";
  const rows: Record<string, Rec[]> = { part: [{ id: "p1", job: "j1" }] };
  const store = {
    list: async () => ({ rows: rows["part"].map((r) => ({ ...r })), total: 1 }),
    get: async () => ({ ...rows["part"][0] }),
    put: async (_e: string, rec: Rec) => { rows["part"][0] = { ...rec }; return rec; },
    remove: async () => {},
  };
  // list mock ignores filter; make job the only candidate by scoping spec
  const out = await enforceOnDelete(spec, store, "job", "j1");
  assert.deepEqual(out, { deleted: 0, nulled: 1 });
  assert.equal(rows["part"][0]["job"], null);
});

test("lifecycle: listing, roles, guards, transitions", () => {
  const rec = { status: "diagnosing", labour_cost: 0 };
  const all = allowedTransitions(repair, "job", rec);
  assert.deepEqual(all.map((t) => t.id).sort(), ["finish", "need_parts"]);
  const ownerOnly = allowedTransitions(repair, "job", { status: "ready" }, { role: "technician" });
  assert.deepEqual(ownerOnly, [], "handover is owner-only");
  const moved = applyTransition(repair, "job", rec, "finish", { role: "technician" });
  assert.equal(moved["status"], "ready");
  assert.equal(rec["status"], "diagnosing", "records are immutable");
  assert.throws(() => applyTransition(repair, "job", rec, "handover", { role: "technician" }), EngineError);
  assert.throws(() => applyTransition(repair, "job", rec, "nope", {}), EngineError);
  assert.throws(() => applyTransition(repair, "job", { status: "ready" }, "finish", {}), EngineError);
  assert.throws(() => applyTransition(repair, "part", {}, "finish", {}), EngineError);
});

test("lifecycle: guard formulas gate transitions", () => {
  const spec = JSON.parse(JSON.stringify(repair)) as AppSpec;
  const job = spec.model.entities.find((e) => e.id === "job")!;
  job.lifecycle!.transitions.find((t) => t.id === "finish")!.guard = "total > 1000";
  assert.deepEqual(allowedTransitions(spec, "job", { status: "diagnosing", total: 500 }).map((t) => t.id), ["need_parts"]);
  assert.deepEqual(allowedTransitions(spec, "job", { status: "diagnosing", total: 5000 }).map((t) => t.id).sort(), ["finish", "need_parts"]);
  assert.throws(() => applyTransition(spec, "job", { status: "diagnosing", total: 5 }, "finish", {}), EngineError);
});

test("lifecycle: broken guard fails closed", () => {
  const spec = JSON.parse(JSON.stringify(repair)) as AppSpec;
  const job = spec.model.entities.find((e) => e.id === "job")!;
  job.lifecycle!.transitions.find((t) => t.id === "finish")!.guard = "nope > 1";
  assert.deepEqual(allowedTransitions(spec, "job", { status: "diagnosing" }).map((t) => t.id), ["need_parts"]);
  assert.throws(() => applyTransition(spec, "job", { status: "diagnosing" }, "finish", {}), EngineError);
});

test("permissions: roles, ops, where-clauses", () => {
  assert.equal(can(repair, "owner", "delete", "job"), true);
  assert.equal(can(repair, "technician", "delete", "job"), false);
  assert.equal(can(repair, "technician", "update", "job"), true);
  assert.equal(can(repair, "ghost", "read", "job"), false);
  // where: technician == $user.name
  const mine = { technician: "Imran" };
  assert.equal(can(repair, "technician", "update", "job", mine, { name: "Imran" }), true);
  assert.equal(can(repair, "technician", "update", "job", mine, { name: "Jo" }), false);
  // owner wildcard has no where: always true
  assert.equal(can(repair, "owner", "read", "job", mine, { name: "Jo" }), true);
});

test("engine never touches network or LLM (static check)", () => {
  const files = ["errors.ts", "validate.ts", "defaults.ts", "computed.ts", "refs.ts", "lifecycle.ts", "permissions.ts", "index.ts"];
  for (const f of files) {
    const src = readFileSync(join(dir, f), "utf8");
    for (const banned of ["fetch(", "XMLHttpRequest", "services/llm", "GEMINI_", "OPENROUTER_"]) {
      assert.ok(!src.includes(banned), `${f} contains ${banned}`);
    }
  }
});

test("permissions: where fails closed on garbage", () => {
  const spec = JSON.parse(JSON.stringify(repair)) as AppSpec;
  const jobRule = spec.access.rules.find((r) => r.role === "technician")!;
  jobRule.where = "nonsense ==";
  assert.equal(can(spec, "technician", "update", "job", { technician: "x" }, {}), false);
  jobRule.where = "technician.name == 'x'";
  assert.equal(can(spec, "technician", "update", "job", { technician: "x" }, {}), false);
  jobRule.where = "technician != 'x' and status == 'a'";
  assert.equal(can(spec, "technician", "update", "job", { technician: "y", status: "a" }, {}), true);
});
