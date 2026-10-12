/**
 * G4 render smoke tests. Registers testing/tsx-loader.mjs FIRST (node can't
 * strip .tsx); g4.ts dynamically imports components/shell after registration.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { register } from "node:module";
import type { AppSpec } from "../../spec/app-spec.ts";

register("./tsx-loader.mjs", import.meta.url);

const { smokeBlocks, smokeShell } = await import("./g4.ts");

const dir = dirname(fileURLToPath(import.meta.url));
const goldDir = join(dir, "../../spec/exemplars");
const golds = readdirSync(goldDir).filter((f) => f.endsWith(".json")).sort();

test("G4 render smoke: blocks + shells", async (t) => {
  const fixtures = JSON.parse(readFileSync(join(dir, "../blocks/fixtures.json"), "utf8")).fixtures;
  await t.test("blocks", async () => {
    const res = await smokeBlocks(fixtures);
    assert.deepEqual(res.failures, [], JSON.stringify(res.failures.slice(0, 3)));
    assert.ok(res.checks >= 28, `only ${res.checks} checks`);
  });
  for (const file of golds) {
    const spec = JSON.parse(readFileSync(join(goldDir, file), "utf8")) as AppSpec;
    await t.test(`shell:${file}`, async () => {
      const res = await smokeShell(spec, file);
      assert.deepEqual(res.failures, [], JSON.stringify(res.failures.slice(0, 3)));
    });
  }
});
