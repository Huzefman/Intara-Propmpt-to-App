/** Deterministic roles editing tests (Phase 8): patch correctness + guards. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AppSpec } from "../../spec/app-spec.ts";
import { addRole, removeRole, removeRule, setRule } from "./roles.ts";
import { EngineError } from "../engine/errors.ts";

const dir = dirname(fileURLToPath(import.meta.url));
const repair = JSON.parse(readFileSync(join(dir, "../../spec/exemplars/repair-tracker.json"), "utf8")) as AppSpec;

test("addRole builds spec + append patch", () => {
  const { spec, patch, summary } = addRole(repair, "auditor", "Auditor");
  assert.ok(spec.access.roles.some((r) => r.id === "auditor"));
  assert.deepEqual(patch, [{ op: "add", path: "/access/roles/-", value: { id: "auditor", label: "Auditor" } }]);
  assert.match(summary, /auditor/);
  assert.equal(repair.access.roles.length, 2, "input untouched");
  assert.throws(() => addRole(repair, "owner"), EngineError);
  assert.throws(() => addRole(repair, "Bad Name"), EngineError);
});

test("removeRole refuses roles in use, removes idle ones with rules", () => {
  assert.throws(() => removeRole(repair, "technician"), /used by page:board/);
  assert.throws(() => removeRole(repair, "ghost"), /does not exist/);
  const withIdle = addRole(repair, "temp").spec;
  const { spec, patch } = removeRole(withIdle, "temp");
  assert.ok(!spec.access.roles.some((r) => r.id === "temp"));
  assert.deepEqual(patch, [{ op: "remove", path: "/access/roles/2" }]);
  // with rules: descending index removals keep paths valid
  const withRule = setRule(withIdle, "temp", "job", ["read"]).spec;
  const r2 = removeRole(withRule, "temp");
  assert.ok(!r2.spec.access.rules.some((r) => r.role === "temp"));
  assert.ok(r2.patch.length >= 2);
});

test("setRule upserts by index, empty ops removes", () => {
  const { spec, patch } = setRule(repair, "technician", "job", ["read"]);
  const rule = spec.access.rules.find((r) => r.role === "technician" && r.entity === "job");
  assert.deepEqual(rule?.ops, ["read"]);
  assert.ok(patch[0].path.toString().startsWith("/access/rules/"));
  const added = setRule(repair, "owner", "part", ["read", "delete"]);
  assert.ok(added.spec.access.rules.some((r) => r.role === "owner" && r.entity === "part"));
  assert.deepEqual(added.patch, [{ op: "add", path: "/access/rules/-", value: { entity: "part", role: "owner", ops: ["read", "delete"] } }]);
  const dropped = removeRule(repair, "technician", "job");
  assert.ok(!dropped.spec.access.rules.some((r) => r.role === "technician" && r.entity === "job"));
  assert.throws(() => setRule(repair, "ghost", "job", ["read"]), EngineError);
  assert.throws(() => setRule(repair, "owner", "nope", ["read"]), EngineError);
  assert.throws(() => setRule(repair, "owner", "job", ["fly"]), EngineError);
  assert.throws(() => removeRule(repair, "owner", "part"), /no rule to remove/);
});
