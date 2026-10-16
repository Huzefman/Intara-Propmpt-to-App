/** Automations executor tests (Phase 8, P8.2): triggers, guards, all steps. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AppSpec } from "../../spec/app-spec.ts";
import { MemoryAdapter } from "../adapters/memory.ts";
import { runAutomations } from "./executor.ts";

const dir = dirname(fileURLToPath(import.meta.url));
const repair = JSON.parse(readFileSync(join(dir, "../../spec/exemplars/repair-tracker.json"), "utf8")) as AppSpec;

async function seeded() {
  const db = new MemoryAdapter();
  await db.put("job", { id: "j1", customer: "c1", device: "Phone", status: "diagnosing", total: 100 });
  await db.put("customer", { id: "c1", name: "Anita", email: "a@x.co" });
  return db;
}

test("lifecycle trigger + guarded email defers without provider", async () => {
  const db = await seeded();
  const fx = await runAutomations(repair, db, {
    type: "lifecycle.transition", entity: "job", transition: "finish",
    record: { id: "j1", device: "Phone", customer: { email: "a@x.co" } },
  });
  // notify_ready: send_email (deferred, no provider) + notify owner
  assert.ok(fx.some((e) => e.kind === "deferred" && e.detail.includes("send_email")));
  assert.ok(fx.some((e) => e.kind === "notify"));
});

test("set_field evaluates zero-arg date functions, leaves literals alone", async () => {
  const db = await seeded();
  const spec = JSON.parse(JSON.stringify(repair)) as AppSpec;
  spec.automations.push({
    id: "stamp", trigger: { type: "record.updated", entity: "job" },
    steps: [
      { action: "set_field", params: { field: "closed_at", value: "today()" } },
      { action: "set_field", params: { field: "technician", value: "Jo" } },
    ],
  });
  await runAutomations(spec, db, { type: "record.updated", entity: "job", record: { id: "j1" } });
  const rec = await db.get("job", "j1");
  assert.match(String(rec?.["closed_at"]), /^\d{4}-\d{2}-\d{2}$/);
  assert.equal(rec?.["technician"], "Jo");
});

test("non-matching trigger and failing guard do nothing", async () => {
  const db = await seeded();
  assert.deepEqual(await runAutomations(repair, db, { type: "record.created", entity: "job", record: {} }), []);
  const fx = await runAutomations(repair, db, {
    type: "lifecycle.transition", entity: "job", transition: "nope", record: {},
  });
  assert.deepEqual(fx, []);
});

test("set_field / create_record / export_csv execute", async () => {
  const db = await seeded();
  const spec = JSON.parse(JSON.stringify(repair)) as AppSpec;
  spec.automations.push({
    id: "triage", trigger: { type: "record.created", entity: "job" },
    steps: [
      { action: "set_field", params: { field: "technician", value: "Jo" } },
      { action: "create_record", params: { entity: "note", values: { text: "new" } } },
      { action: "export_csv", params: {} },
    ],
  });
  const fx = await runAutomations(spec, db, { type: "record.created", entity: "job", record: { id: "j1" } });
  assert.equal((await db.get("job", "j1"))?.["technician"], "Jo");
  assert.ok(fx.some((e) => e.kind === "create_record"));
  const csv = fx.find((e) => e.kind === "export_csv");
  assert.ok(csv && String((csv.record as Record<string, unknown>)["csv"]).includes("device"));
});
