/**
 * Block registry tests (Phase 6, P6.4): all ~14 types registered, stability
 * matches the G1 catalog, every type has a fixture whose props satisfy the
 * linter's required-props. Rendering states are covered by construction
 * (resolveState/BlockShell shared); Playwright per-block runs in browser CI.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { BLOCKS, BLOCK_TYPES } from "./registry.ts";
import { displayPath, resolveState } from "./types.ts";
import { aggValue } from "./stats.ts";

const dir = dirname(fileURLToPath(import.meta.url));
const fixtures = JSON.parse(readFileSync(join(dir, "fixtures.json"), "utf8")).fixtures as Record<string, {
  props: Record<string, unknown>; rows?: Array<Record<string, unknown>>; record?: Record<string, unknown> | null;
}>;

// Mirror of server/gates/g1_lint.py BLOCKS (required + optional props).
const LINT_BLOCKS: Record<string, { stability: string; required: string[]; optional: string[] }> = {
  "data.table": { stability: "stable", required: ["entity"], optional: ["columns", "row_link", "create"] },
  "data.kanban": { stability: "stable", required: ["entity", "group_by"], optional: ["card", "drag_transitions"] },
  "metric.stat": { stability: "stable", required: ["entity", "items"], optional: [] },
  "filter.bar": { stability: "stable", required: ["entity"], optional: ["fields", "search"] },
  "record.detail": { stability: "stable", required: ["entity"], optional: ["sections"] },
  "record.related_list": { stability: "stable", required: ["entity", "via"], optional: ["columns", "row_link", "create"] },
  "lifecycle.pipeline": { stability: "stable", required: ["entity"], optional: [] },
  "metric.gauge": { stability: "experimental", required: ["entity"], optional: ["field", "max", "label"] },
  "form.record": { stability: "stable", required: ["entity"], optional: ["fields"] },
  "chart.bar": { stability: "stable", required: ["entity", "x"], optional: ["title", "y"] },
  "calendar.month": { stability: "stable", required: ["entity", "date_field"], optional: ["title", "row_link"] },
  "activity.timeline": { stability: "stable", required: ["entity", "date_field"], optional: ["title"] },
  "file.list": { stability: "stable", required: ["entity"], optional: ["field"] },
  "content.hero": { stability: "stable", required: [], optional: ["title", "subtitle", "cta"] },
};

test("registry covers all catalog types", () => {
  assert.equal(BLOCK_TYPES.length, 14);
  for (const t of Object.keys(LINT_BLOCKS)) {
    assert.ok(BLOCKS[t], `registry missing ${t}`);
    assert.equal(BLOCKS[t].stability, LINT_BLOCKS[t].stability, `${t} stability drift`);
  }
});

test("every type has a component mapping (static check, tsx is browser-only)", () => {
  const src = readFileSync(join(dir, "components.ts"), "utf8");
  for (const t of BLOCK_TYPES) {
    assert.ok(src.includes(`"${t}"`), `components.ts missing ${t}`);
  }
});

test("every block has a fixture satisfying required props and known keys", () => {
  for (const [t, info] of Object.entries(LINT_BLOCKS)) {
    const fx = fixtures[t];
    assert.ok(fx, `fixture missing for ${t}`);
    for (const req of info.required)
      assert.ok(req in fx.props, `${t} fixture missing prop ${req}`);
    for (const key of Object.keys(fx.props))
      assert.ok(info.required.includes(key) || info.optional.includes(key),
        `${t} fixture uses unknown prop ${key}`);
  }
});

test("state resolution covers empty/loading/error/ready", () => {
  assert.equal(resolveState(undefined, undefined, undefined, undefined), "loading");
  assert.equal(resolveState([], undefined, undefined, undefined), "empty");
  assert.equal(resolveState(undefined, null, undefined, undefined), "empty");
  assert.equal(resolveState([{ a: 1 }], undefined, undefined, undefined), "ready");
  assert.equal(resolveState(undefined, undefined, undefined, "x"), "error");
  assert.equal(resolveState(undefined, undefined, "ready", "x"), "ready", "explicit wins");
});

test("stat aggregation over rows", () => {
  const rows = [{ status: "ready", total: 10 }, { status: "delivered", total: 20 }];
  assert.equal(aggValue(rows, { label: "n", agg: "count", where: "status != 'delivered'" }), 1);
  assert.equal(aggValue(rows, { label: "s", agg: "sum", field: "total" }), 30);
  assert.equal(aggValue(rows, { label: "a", agg: "avg", field: "total" }), 15);
  assert.equal(aggValue([], { label: "z", agg: "sum", field: "total" }), 0);
  assert.equal(aggValue(rows, { label: "bad", agg: "count", where: "(((" }), 0, "bad where excludes all");
});

test("display paths for cards and cells", () => {
  const row = { name: "Mug", customer: { name: "Anita" }, done: true, qty: 3 };
  assert.equal(displayPath(row, "name"), "Mug");
  assert.equal(displayPath(row, "customer.name"), "Anita");
  assert.equal(displayPath(row, "customer.missing"), "—");
  assert.equal(displayPath(row, "missing"), "—");
  assert.equal(displayPath(row, "done"), "yes");
  assert.equal(displayPath(row, "qty"), "3");
  assert.equal(displayPath(row, "qty.x"), "—");
  assert.equal(displayPath({ customer: { name: "Anita", id: "c1" } }, "customer"), "Anita");
  assert.equal(displayPath({ customer: { id: "c1" } }, "customer"), "c1");
  assert.equal(displayPath({ tags: [{ name: "a" }, { title: "b" }] }, "tags"), "a, b");
  assert.equal(displayPath({ plant: { common_name: "Tomato", id: "p1" } }, "plant"), "Tomato");
  assert.equal(displayPath({ blob: {} }, "blob"), "—");
});
