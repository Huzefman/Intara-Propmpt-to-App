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

// Mirror of server/gates/g1_lint.py BLOCKS (stability + required props).
const LINT_BLOCKS: Record<string, { stability: string; required_props: string[] }> = {
  "data.table": { stability: "stable", required_props: ["entity"] },
  "data.kanban": { stability: "stable", required_props: ["entity", "group_by"] },
  "metric.stat": { stability: "stable", required_props: ["entity"] },
  "filter.bar": { stability: "stable", required_props: ["entity"] },
  "record.detail": { stability: "stable", required_props: ["entity"] },
  "record.related_list": { stability: "stable", required_props: ["entity"] },
  "lifecycle.pipeline": { stability: "stable", required_props: ["entity"] },
  "metric.gauge": { stability: "experimental", required_props: ["entity"] },
  "form.record": { stability: "stable", required_props: ["entity"] },
  "chart.bar": { stability: "stable", required_props: ["entity"] },
  "calendar.month": { stability: "stable", required_props: ["entity"] },
  "activity.timeline": { stability: "stable", required_props: ["entity"] },
  "file.list": { stability: "stable", required_props: ["entity"] },
  "content.hero": { stability: "stable", required_props: [] },
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

test("every block has a fixture satisfying required props", () => {
  for (const [t, info] of Object.entries(LINT_BLOCKS)) {
    const fx = fixtures[t];
    assert.ok(fx, `fixture missing for ${t}`);
    for (const req of info.required_props)
      assert.ok(req in fx.props, `${t} fixture missing prop ${req}`);
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
});
